# service/notion_sync_service.py
import re
import time
from typing import Optional, List, Dict, Any, Callable
from notion_client import Client

from utils.config import Config
from base.base_service import BaseService

class NotionSyncService(BaseService):
    """
    마크다운 텍스트를 Notion Block 객체로 변환하고,
    Notion API 통신을 통해 페이지 생성/검색/동기화를 전담하는 통합 서비스입니다.
    """

    def __init__(self, auth_token: Optional[str] = None, logger_callback: Optional[Callable[[str], None]] = None) -> None:
        # BaseService 초기화 시 콜백을 등록하여 내부에서 self._log()로 일괄 처리
        super().__init__(logger_callback=logger_callback)
        self._auth_token: Optional[str] = auth_token
        self._client: Optional[Client] = None

    # ==========================================
    # 1. 내부 API 통신 및 인증 엔진
    # ==========================================

    def _get_client(self) -> Client:
        """Notion Client 객체를 반환합니다 (Lazy Singleton)."""
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
        """데이터베이스 내에서 특정 제목을 포함하는 첫 번째 페이지의 ID를 검색합니다."""
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
        """새로운 노션 페이지를 생성하고 Page ID를 반환합니다."""
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
        """
        페이지 하단에 Notion Block 리스트를 추가합니다.
        Notion API의 1회 전송 한도(100개)를 방어하기 위해 100개 단위 청크로 분할 전송합니다.
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
        """볼드/이탤릭 마크다운 텍스트를 Notion Rich Text 규격 리스트로 파싱합니다."""
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
        """해당 라인이 마크다운 표 구분선인지 검증합니다."""
        if not line.startswith('|') or not line.endswith('|'):
            return False
        cells = [c.strip() for c in line.split('|')][1:-1]
        if not cells: 
            return False
        return all(re.match(r'^:?-+:?$', c) for c in cells)

    def _parse_markdown_table(self, table_lines: List[str]) -> Optional[Dict[str, Any]]:
        """마크다운 테이블을 Notion Table 블록 객체로 변환합니다."""
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
        """마크다운 텍스트를 Notion Block 객체 리스트로 일괄 변환합니다 (번호 매기기 리스트 지원 포함)."""
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
        """마크다운을 블록으로 변환하여 지정된 노션 페이지에 즉시 추가합니다."""
        blocks = self.create_markdown_blocks(markdown_text)
        self.append_blocks_to_page(page_id, blocks)