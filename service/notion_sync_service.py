"""Notion API 연동 및 마크다운 변환 서비스 모듈.

이 모듈은 AutoStudy_UI 프로젝트의 전체 아키텍처 중 **Service(서비스) 계층**에 속합니다.
LLM(Gemini) 분석을 통해 도출된 핵심 요약본(단권화 노트 등) 형태의 마크다운 텍스트를 
Notion API가 인식할 수 있는 엄격한 Block 객체(JSON 구조)로 파싱하고, 지정된 데이터베이스에 
페이지를 생성하거나 동기화하는 핵심 비즈니스 로직을 담당합니다. 

학습 자료 자동화 파이프라인의 최종 종착지(Export) 중 하나로서, 백그라운드 Worker 스레드에서 
비동기적으로 호출되어 대용량 텍스트나 복잡한 표(Table) 데이터를 메인 UI의 차단(Freezing) 없이 
안전하게 사용자의 클라우드 워크스페이스에 적재하는 역할을 수행합니다.
"""
import re
import time
from typing import Optional, List, Dict, Any, Callable
from notion_client import Client

from utils.config import Config
from base.base_service import BaseService


class NotionSyncService(BaseService):
    """마크다운 텍스트를 Notion Block 객체로 변환하고 API 통신을 전담하는 통합 서비스 클래스.

    단일 책임 원칙(SRP)에 따라, 오직 마크다운 텍스트 파싱과 Notion 워크스페이스와의 
    네트워크 통신(페이지 생성, 검색, 블록 추가) 작업만을 전담합니다. 데이터의 원천(PDF 파싱, LLM 등)에 
    대해서는 알지 못하며 오직 텍스트 직렬화 및 클라우드 동기화에만 집중합니다.
    
    의존성:
    - 전역 환경설정인 `utils.config.Config`를 참조하여 'NOTION_TOKEN'을 획득합니다.
    - 외부 라이브러리인 `notion_client.Client`를 사용하여 공식 API 통신을 대리합니다.
    - 상위 Controller 또는 비동기 Worker로부터 LLM 요약 결과물(Markdown 문자열)을 주입받아 동작합니다.
    """

    def __init__(self, auth_token: Optional[str] = None, logger_callback: Optional[Callable[[str], None]] = None) -> None:
        """NotionSyncService 인스턴스를 초기화합니다.

        Args:
            auth_token (Optional[str], optional): 명시적으로 주입할 Notion API 토큰. 
                생략될 경우 Config에서 전역 토큰을 자동으로 가져옵니다. Defaults to None.
            logger_callback (Optional[Callable[[str], None]], optional): 비동기 처리 중 발생하는 
                로그를 UI로 전달하기 위한 콜백 함수. Defaults to None.
        """
        # BaseService 초기화 시 콜백을 등록하여 내부에서 self._log()로 일괄 처리
        super().__init__(logger_callback=logger_callback)
        self._auth_token: Optional[str] = auth_token
        self._client: Optional[Client] = None

    # ==========================================
    # 1. 내부 API 통신 및 인증 엔진
    # ==========================================

    def _get_client(self) -> Client:
        """Notion Client 객체를 지연 초기화(Lazy Singleton) 방식으로 반환합니다.
        
        파이프라인 초기화 시점부터 불필요한 네트워크 연결 객체를 생성하여 자원을 낭비하는 것을 막고, 
        실제 동기화 작업이 요청되는 런타임 시점에 클라이언트를 빌드하기 위해 고안되었습니다. 
        사용자가 환경 변수(.env)에 토큰을 기입하지 않고 파이프라인을 실행했을 때 
        사전에 에러를 캐치(Fail-fast)하여 명확한 안내를 제공합니다.

        Returns:
            Client: 인증이 완료된 notion_client.Client 인스턴스.

        Raises:
            ValueError: 'NOTION_TOKEN'이 명시되지 않았거나 Config에 존재하지 않을 경우 발생합니다.
        """
        if self._client is None:
            # [개선] config.py 업데이트에 따라 getattr 없이 명시적 속성으로 직접 안전하게 접근합니다.
            token = self._auth_token or Config.NOTION_TOKEN
            
            if not token:
                raise ValueError("❌ 'NOTION_TOKEN'이 설정되어 있지 않습니다.")
            self._client = Client(auth=token)
        return self._client

    def find_page_by_title(
        self, 
        database_id: str, 
        title_query: str, 
        title_property_name: str = "이름"
    ) -> Optional[str]:
        """데이터베이스 내에서 특정 제목을 포함하는 첫 번째 페이지의 ID를 검색합니다.
        
        자동화된 데이터 파이프라인(Watchdog 등)은 동일한 파일에 대해 여러 번 트리거될 수 있습니다. 
        이때 무작정 새로운 노션 페이지를 계속 생성하면 워크스페이스가 중복 데이터로 오염됩니다. 
        이를 방지하기 위해 데이터 삽입 전 페이지의 존재 여부를 쿼리하여, 동일한 제목(교시 이름 등)의 
        페이지가 존재하면 해당 페이지를 반환해 업데이트를 유도하는 '멱등성(Idempotency)' 보장의 핵심 로직입니다.

        Args:
            database_id (str): 페이지를 검색할 대상 노션 데이터베이스의 고유 식별자.
            title_query (str): 검색할 페이지의 제목 문자열.
            title_property_name (str, optional): 데이터베이스에 설정된 제목 속성(Property)의 이름. Defaults to "이름".

        Returns:
            Optional[str]: 검색 조건에 일치하는 첫 번째 페이지의 ID 문자열. 존재하지 않으면 None을 반환합니다.

        Raises:
            Exception: 데이터베이스 접근 권한이 없거나 네트워크 오류 등 API 통신 중 예외 발생 시.
        """
        client = self._get_client()
        try:
            response = client.databases.query(
                **{
                    "database_id": database_id,
                    "filter": {
                        "property": title_property_name,
                        "rich_text": {"contains": title_query}
                    }
                }
            )
            results = response.get("results", [])
            if results:
                return results[0]["id"]
            return None
        except Exception as e:
            self._log(f"❌ Notion 페이지 검색 실패: {str(e)}")
            raise Exception(f"Notion 페이지 검색 실패: {str(e)}")

    def create_notion_page(self, database_id: str, properties: Dict[str, Any]) -> str:
        """새로운 노션 페이지를 생성하고 Page ID를 반환합니다.
        
        새로운 학습 자료 파이프라인 결과물을 저장할 물리적 컨테이너(페이지)를 
        지정된 데이터베이스 하위에 생성합니다. 생성 시 데이터베이스 스키마에 맞춘 메타데이터(Properties)를 
        초기 주입하여, 이후 내용을 블록(Blocks)으로 덧붙일 수 있도록 기틀을 마련합니다.

        Args:
            database_id (str): 새 페이지가 소속될 부모 데이터베이스의 고유 식별자.
            properties (Dict[str, Any]): 페이지 생성 시 부여할 속성(제목, 태그, 생성일 등) 정보가 담긴 딕셔너리.

        Returns:
            str: 정상적으로 생성된 노션 페이지의 고유 ID 문자열.

        Raises:
            Exception: 스키마 불일치, API 권한 부족, 토큰 만료 등으로 페이지 생성이 거부될 경우.
        """
        client = self._get_client()
        try:
            created_page = client.pages.create(
                parent={"database_id": database_id}, 
                properties=properties
            )
            self._log(f"✨ Notion 페이지 생성 완료 (ID: {created_page['id']})")
            return created_page["id"]
        except Exception as e:
            self._log(f"❌ Notion 페이지 생성 실패: {str(e)}")
            raise Exception(f"Notion 페이지 생성 실패: {str(e)}")

    def append_blocks_to_page(self, page_id: str, children_blocks: List[Dict[str, Any]]) -> None:
        """페이지 하단에 Notion Block 리스트를 추가합니다.
        
        LLM이 생성한 대용량 마크다운 텍스트는 변환 후 수백~수천 개의 노션 블록 객체로 치환됩니다. 
        Notion API는 안정성 유지를 위해 1회 `append` 요청 시 최대 100개의 블록 전송 제한(Hard Limit)과 
        초당 호출 횟수(Rate Limit) 제한을 엄격하게 걸고 있습니다. 
        
        이 메서드는 전체 블록 리스트를 100개 단위 청크(Chunk)로 슬라이싱하고, 
        루프마다 `time.sleep(0.3)` 딜레이를 주어 속도를 조절하는 방어적 큐잉(Queuing) 로직을 포함합니다. 
        이를 통해 대용량 동기화 작업 중 `HTTP 429 Too Many Requests` 나 `HTTP 400 Bad Request` 
        에러로 파이프라인이 붕괴되는 것을 완벽히 방지합니다.

        Args:
            page_id (str): 블록들을 추가할 대상 노션 페이지의 고유 ID.
            children_blocks (List[Dict[str, Any]]): 노션 API 규격에 맞게 파싱 완료된 블록 객체들의 리스트.

        Returns:
            None

        Raises:
            Exception: 잘못된 블록 구조(Malformed JSON) 등 통신 거부 사유 발생 시.
        """
        client = self._get_client()
        chunk_size = 100
        try:
            total_blocks = len(children_blocks)
            for i in range(0, total_blocks, chunk_size):
                chunk = children_blocks[i:i + chunk_size]
                client.blocks.children.append(block_id=page_id, children=chunk)
                self._log(f"📤 Notion 블록 전송 중... ({min(i + chunk_size, total_blocks)}/{total_blocks})")
                time.sleep(0.3)  # 초당 호출 제한(Rate Limit) 방어
            self._log("✅ 모든 Notion 블록 추가 완료")
        except Exception as e:
            self._log(f"❌ Notion 블록 추가 실패: {str(e)}")
            raise Exception(f"Notion 블록 추가 실패: {str(e)}")

    # ==========================================
    # 2. 마크다운 -> Notion Block 파싱 엔진
    # ==========================================

    def _convert_text_to_rich_text(self, text: str) -> List[Dict[str, Any]]:
        """볼드/이탤릭 마크다운 텍스트를 Notion Rich Text 규격 리스트로 파싱합니다.
        
        노션의 본문 텍스트는 단순 문자열이 아니라 속성(굵게, 기울임 등)을 지닌 `rich_text` 객체 배열로 구성됩니다. 
        이 함수는 정규표현식을 사용해 LLM 응답 텍스트에 포함된 볼드(`**`), 이탤릭(`*`), 볼드+이탤릭(`***`) 등의 
        마크다운 기호를 해체하고, 이를 노션의 `annotations` JSON 구조로 정확하게 맵핑합니다. 
        
        또한, 단일 `rich_text` 요소의 내용이 2000자를 초과하면 Notion API에서 전송을 거부하므로, 
        2000자 단위로 텍스트를 강제 분할(Chunking)하여 배열에 이어붙이는 안전장치가 
        비동기 대용량 텍스트 파싱을 위해 견고하게 내장되어 있습니다.

        Args:
            text (str): 마크다운 문법이 포함된 원본 단일 문자열.

        Returns:
            List[Dict[str, Any]]: 노션 API 규격을 준수하는 Rich Text JSON 객체들의 리스트.
        """
        parts = re.split(r'(\*\*\*.*?\*\*\*|\*\*.*?\*\*|\*.*?\*)', text)
        rich_text_list = []
        
        for part in parts:
            if not part: 
                continue
                
            is_bold = False
            is_italic = False
            content = part
            
            if part.startswith("***") and part.endswith("***") and len(part) >= 6:
                is_bold, is_italic = True, True
                content = part[3:-3]
            elif part.startswith("**") and part.endswith("**") and len(part) >= 4:
                is_bold = True
                content = part[2:-2]
            elif part.startswith("*") and part.endswith("*") and len(part) >= 2:
                is_italic = True
                content = part[1:-1]
                
            if not content:
                continue
                
            # Notion Rich Text 단일 요소 제한(2000자) 대응
            for j in range(0, len(content), 2000):
                chunk = content[j:j+2000]
                rt_obj = {
                    "type": "text",
                    "text": {"content": chunk}
                }
                
                annotations = {}
                if is_bold: annotations["bold"] = True
                if is_italic: annotations["italic"] = True
                if annotations: rt_obj["annotations"] = annotations
                
                rich_text_list.append(rt_obj)
                
        return rich_text_list

    def _is_separator_line(self, line: str) -> bool:
        """해당 라인이 마크다운 표(Table) 구분선인지 검증합니다.
        
        마크다운 표를 파싱하기 위해서는 해당 줄이 테이블의 헤더와 본문을 분리하는 
        구분선(예: `|---|---|` 또는 `|:---:|:---:|`) 역할을 하는지 판단해야 합니다. 
        정규식을 통해 칸(Cell) 안의 문자열이 순수 하이픈(`-`)과 콜론(`:`)으로만 
        이루어져 있는지 검사하여 테이블 파싱 엔진의 오작동을 방지합니다.

        Args:
            line (str): 검사할 대상 문자열 라인.

        Returns:
            bool: 테이블 구분선 형식을 띄고 있으면 True, 아니면 False.
        """
        if not line.startswith('|') or not line.endswith('|'):
            return False
        cells = [c.strip() for c in line.split('|')][1:-1]
        if not cells: 
            return False
        return all(re.match(r'^:?-+:?$', c) for c in cells)

    def _parse_markdown_table(self, table_lines: List[str]) -> Optional[Dict[str, Any]]:
        """마크다운 형태의 테이블 문자열 배열을 Notion Table 블록 객체로 변환합니다.
        
        Gemini LLM이 도출하는 '감별 진단 비교표' 등 복잡한 의학 데이터를 노션 테이블로 완벽히 복원하기 위해 설계되었습니다. 
        Notion의 Table 블록은 `table` 루트 객체 하위에 `table_row` 객체들이 배열로 묶이고, 
        그 안의 각 `cells` 배열에 다시 `rich_text` 배열이 들어가는 매우 깊은(Nested) 트리 구조를 갖습니다. 
        
        이 메서드는 제공받은 마크다운 테이블 라인들을 순회하며 헤더를 제외한 데이터 행(Row)을 추출하고, 
        열(Column) 수가 부족해 테이블 형태가 찌그러지는 현상을 막기 위해 빈 문자열 셀을 삽입(Padding)하여 
        `table_width`를 균일하게 맞추는 정교한 파싱 작업을 수행합니다.

        Args:
            table_lines (List[str]): 테이블을 구성하는 여러 줄의 마크다운 문자열 리스트.

        Returns:
            Optional[Dict[str, Any]]: 노션 API 규격에 맞는 최상위 Table Block JSON 객체. 유효한 데이터가 없으면 None 반환.
        """
        has_header = False
        parsed_rows = []
        
        for line in table_lines:
            if self._is_separator_line(line):
                has_header = True
                continue
            cells = [cell.strip() for cell in line.split('|')][1:-1]
            if cells: 
                parsed_rows.append(cells)
            
        if not parsed_rows: 
            return None
            
        table_width = max(len(row) for row in parsed_rows)
        children_rows = []
        
        for row in parsed_rows:
            while len(row) < table_width:
                row.append("")
                
            cells_json = [self._convert_text_to_rich_text(cell) for cell in row]
            children_rows.append({
                "object": "block",
                "type": "table_row",
                "table_row": {"cells": cells_json}
            })
            
        return {
            "object": "block",
            "type": "table",
            "table": {
                "table_width": table_width,
                "has_column_header": has_header,
                "has_row_header": False,
                "children": children_rows
            }
        }

    def create_markdown_blocks(self, text: str) -> List[Dict[str, Any]]:
        """마크다운 텍스트를 Notion Block 객체 리스트로 일괄 변환합니다.
        
        이 서비스의 핵심 컴파일러 엔진(Compiler Engine) 역할을 수행합니다. 
        LLM이 출력한 순수 마크다운 문자열을 줄(Line) 단위로 읽어 들이며, 각 라인의 접두사를 분석해 
        제목(Heading 1~3), 불릿 리스트(Bulleted), 번호 리스트(Numbered), 구분선(Divider), 일반 단락(Paragraph), 
        그리고 복합 테이블(Table) 등의 적합한 노션 블록 타입으로 스위칭(Routing)하여 변환합니다. 
        전체 파이프라인에서 '비정형 데이터'를 클라우드 DB가 인식 가능한 '정형 데이터 구조'로 
        탈바꿈시키는 가장 중추적인 변환 로직입니다.

        Args:
            text (str): 다수의 마크다운 문법이 혼재된 긴 원본 문자열 텍스트.

        Returns:
            List[Dict[str, Any]]: 노션 API 전송에 즉시 사용할 수 있도록 파싱 및 구조화된 블록 JSON 객체 리스트.
        """
        blocks = []
        lines = [line.strip() for line in text.split('\n')]
        i = 0
        
        while i < len(lines):
            line = lines[i]
            
            if not line:
                blocks.append({"object": "block", "type": "paragraph", "paragraph": {"rich_text": []}})
                i += 1
                continue
                
            if line == "---":
                blocks.append({"object": "block", "type": "divider", "divider": {}})
                i += 1
                continue

            is_table = False
            header_index = -1
            
            if line.startswith('|'):
                if i + 1 < len(lines) and self._is_separator_line(lines[i+1]):
                    is_table = True
                    header_index = i
                elif i + 2 < len(lines) and self._is_separator_line(lines[i+2]) and lines[i+1].startswith('|'):
                    is_table = True
                    header_index = i + 1
                    title_content = line.lstrip('|').strip()
                    blocks.append({
                        "object": "block", "type": "paragraph",
                        "paragraph": {"rich_text": self._convert_text_to_rich_text(title_content)}
                    })
            
            if is_table:
                table_lines = [lines[header_index], lines[header_index+1]]
                idx = header_index + 2
                while idx < len(lines) and lines[idx].startswith('|') and not self._is_separator_line(lines[idx]):
                    table_lines.append(lines[idx])
                    idx += 1
                    
                table_block = self._parse_markdown_table(table_lines)
                if table_block: 
                    blocks.append(table_block)
                i = idx  
                continue

            block_type = "paragraph"
            content = line

            if line.startswith("### "):
                block_type, content = "heading_3", line[4:]
            elif line.startswith("## "):
                block_type, content = "heading_2", line[3:]
            elif line.startswith("# "):
                block_type, content = "heading_1", line[2:]
            elif line.startswith("* ") or line.startswith("- "):
                block_type, content = "bulleted_list_item", line[2:]
            elif re.match(r'^\d+\.\s+', line):
                # 숫자 번호 매기기 리스트(1., 2. 등) 지원 추가
                block_type = "numbered_list_item"
                content = re.sub(r'^\d+\.\s+', '', line)

            blocks.append({
                "object": "block",
                "type": block_type,
                block_type: {"rich_text": self._convert_text_to_rich_text(content)}
            })
            i += 1
                
        return blocks

    # ==========================================
    # 3. 통합 동기화 파이프라인
    # ==========================================

    def sync_markdown_to_page(self, page_id: str, markdown_text: str) -> None:
        """마크다운을 블록으로 일괄 변환하여 지정된 노션 페이지에 즉시 추가(Sync)합니다.
        
        Service나 Controller에서 외부 API로 직접 노출되는 퍼블릭 엔드포인트 메서드입니다. 
        `create_markdown_blocks`를 호출해 텍스트를 메모리 상에서 완벽한 블록 객체들로 컴파일한 뒤, 
        `append_blocks_to_page`를 호출하여 청크 단위 딜레이를 주며 클라우드에 밀어넣는 
        일련의 과정(Orchestration)을 하나로 묶어 제공합니다.

        Args:
            page_id (str): 데이터가 삽입될 노션 페이지의 고유 식별자.
            markdown_text (str): 페이지에 기록될 LLM 결과물 기반의 마크다운 포맷 문자열.

        Returns:
            None
        """
        blocks = self.create_markdown_blocks(markdown_text)
        self.append_blocks_to_page(page_id, blocks)