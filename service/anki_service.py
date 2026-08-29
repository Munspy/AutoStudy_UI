"""Anki 플래시카드 생성 및 패키징 서비스 모듈.

이 모듈은 AutoStudy_UI 프로젝트의 전체 파이프라인 중 **Service(서비스) 계층**에 속합니다.
LLM(Gemini) 분석을 통해 추출된 학습 데이터(CSV 형태의 문자열)를 파싱하고, 
이를 바탕으로 Anki 애플리케이션에서 직접 학습할 수 있는 .apkg 패키지 파일을 
자동으로 빌드하는 핵심 비즈니스 로직을 담당합니다. 
비동기 Worker 스레드에서 백그라운드로 호출되어 메인 UI 차단 없이 대용량의 카드를 
안전하게 생성하고 로컬 스토리지에 저장하는 역할을 수행합니다.
"""
import hashlib
from pathlib import Path
from typing import Dict, List, Optional
import genanki
from base.base_service import BaseService

class AnkiGenerationService(BaseService):
    """LLM이 생성한 CSV 텍스트 데이터를 파싱하여 Anki 덱으로 패키징하는 서비스 클래스.

    단일 책임 원칙(SRP)에 따라, 오직 문자열 형태의 원시 데이터(Raw CSV Text)를 
    Basic, Cloze, MCQ 형식으로 분류하고 genanki 라이브러리를 통해 물리적인 
    .apkg 파일로 렌더링 및 저장하는 I/O 작업만을 전담합니다. 
    
    의존성: 
    - Controller 또는 Worker 계층으로부터 추출 완료된 LLM 결과물을 문자열 형태로 전달받아 실행됩니다.
    - 부모 클래스인 `BaseService`를 상속받아 공통 로깅(`_log`) 등의 인터페이스를 공유합니다.
    """

    # 안키 순정 기본(Default) 디자인 CSS 적용
    DEFAULT_ANKI_CSS = """
    .card {
        font-family: arial;
        font-size: 20px;
        text-align: center;
        color: black;
        background-color: white;
    }
    .cloze {
        font-weight: bold;
        color: blue;
    }
    .nightMode .cloze {
        color: lightblue;
    }
    ul, ol {
        text-align: left;
        display: inline-block;
    }
    """

    # ==========================================
    # 1. 내부 유틸리티 및 팩토리 메서드
    # ==========================================

    def _generate_anki_id(self, name: str) -> int:
        """문자열 기반의 고유 해시 ID를 생성합니다.

        Anki 덱(Deck)과 모델(Model)은 애플리케이션 내에서 충돌을 방지하기 위해 
        반드시 고유한 정수형 ID를 가져야 합니다. 자동화 파이프라인이 여러 번 실행되거나 
        덱 이름이 동일할 경우 매번 다른 ID가 부여되면 Anki로 임포트할 때 기존 덱이 
        업데이트되지 않고 중복 생성되는 문제가 발생할 수 있습니다. 
        이를 방지하고자 입력된 이름(문자열)을 SHA-256 해시로 변환한 후 정수형으로 캐스팅하여, 
        동일한 이름에는 항상 동일한 고유 ID(멱등성)가 부여되도록 설계된 방어 로직입니다.

        Args:
            name (str): 해시화하여 고유 ID를 생성할 대상 문자열 (예: 덱 이름, 모델 이름).

        Returns:
            int: 10^9 이하의 고정된 정수형 해시 ID.
        """
        return int(hashlib.sha256(name.encode('utf-8')).hexdigest(), 16) % (10**9)

    def _get_basic_model(self) -> genanki.Model:
        """Basic 및 MCQ(객관식) 카드를 생성하기 위한 Anki 모델 팩토리 메서드입니다.

        Anki의 모델(Model)은 카드의 앞면과 뒷면이 어떻게 화면에 렌더링될지(HTML/CSS)를 결정하는 
        설계도 역할을 합니다. 이 메서드는 자동화된 학습 자료 생성 과정에서 일반적인 문답형(Basic) 카드와 
        객관식(MCQ) 카드를 시각적으로 깔끔하게 보여주기 위한 기본 템플릿을 정의하고 반환합니다. 
        하드코딩된 ID(1607392319)를 사용하여 덱 업데이트 시 카드 구조가 깨지지 않도록 강제합니다.

        Args:
            없음

        Returns:
            genanki.Model: 'Front'와 'Back' 필드를 가지며 커스텀 CSS가 적용된 기본형 안키 모델 객체.
        """
        return genanki.Model(
            1607392319,
            '기본(Basic) - 생성형',
            fields=[{'name': 'Front'}, {'name': 'Back'}],
            templates=[{
                'name': 'Card 1',
                'qfmt': '{{Front}}',
                'afmt': '{{FrontSide}}<hr id=answer>{{Back}}'
            }],
            css=self.DEFAULT_ANKI_CSS
        )

    def _get_cloze_model(self) -> genanki.Model:
        """빈칸 뚫기(Cloze) 카드를 생성하기 위한 Anki 모델 팩토리 메서드입니다.

        빈칸 뚫기 카드는 일반 카드와 달리 Anki 내부적으로 {{c1::정답}}과 같은 특수한 
        마크다운 렌더링 처리가 필요합니다. 이 팩토리 메서드는 모델 타입을 `genanki.Model.CLOZE`로 
        명시하여 해당 카드가 빈칸 학습용임을 시스템에 알리고, 그에 맞는 전용 템플릿과 CSS를 입힌 
        모델 객체를 제공합니다. 마찬가지로 자동화 파이프라인의 멱등성을 위해 고정된 ID(1607392320)를 사용합니다.

        Args:
            없음

        Returns:
            genanki.Model: 'Text'와 'Back Extra' 필드를 가지며 빈칸 뚫기에 최적화된 안키 모델 객체.
        """
        return genanki.Model(
            1607392320,
            '빈칸 뚫기(Cloze) - 생성형',
            model_type=genanki.Model.CLOZE,
            fields=[{'name': 'Text'}, {'name': 'Back Extra'}],
            templates=[{
                'name': 'Cloze',
                'qfmt': '{{cloze:Text}}',
                'afmt': '{{cloze:Text}}<br><br>{{Back Extra}}'
            }],
            css=self.DEFAULT_ANKI_CSS
        )

    # ==========================================
    # 2. 파일 I/O 로직 (pathlib 적용)
    # ==========================================
    def _save_csv_files(self, target_dir: str, base_name: str, parsed_data: Dict[str, List[str]]):
        """분류된 Basic, MCQ, Cloze 텍스트 데이터를 개별 CSV 파일로 백업 저장합니다.

        자동화된 데이터 파이프라인에서 LLM이 생성한 결과물을 즉시 .apkg로 패키징하더라도, 
        사용자가 추후 내용을 직접 수정하거나 파이프라인 중간에 크래시가 발생했을 때 
        데이터가 유실되는 것을 막기 위한 필수적인 안전장치(I/O 백업)입니다. 
        `pathlib`을 사용하여 디렉토리가 존재하지 않을 경우 자동 생성하며, 
        다양한 언어가 포함될 수 있는 학습 자료 특성을 고려해 `utf-8-sig` 인코딩을 강제하여 
        엑셀(Excel) 등 외부 프로그램에서 열 때도 한글 깨짐이 없도록 견고하게 설계되었습니다.

        Args:
            target_dir (str): CSV 파일들이 저장될 최종 목적지 디렉토리 경로.
            base_name (str): 파일명의 접두사로 사용될 원본 문서의 기본 이름.
            parsed_data (Dict[str, List[str]]): 카드 타입(Basic, MCQ, Cloze)을 키(Key)로 하고, 
                파싱된 텍스트 라인들의 리스트를 값(Value)으로 갖는 딕셔너리.

        Returns:
            None: 반환값 없이 파일 시스템에 직접 기록하며, 예외 발생 시 에러를 로깅합니다.
        """
        try:
            target_path = Path(target_dir)
            target_path.mkdir(parents=True, exist_ok=True)
            
            for suffix, lines in parsed_data.items():
                if lines:
                    file_path = target_path / f"{base_name}_{suffix}.csv"
                    with open(file_path, "w", encoding="utf-8-sig") as f:
                        f.write('\n'.join(lines))
                    self._log(f"💾 [Anki 팀] {suffix} 백업 파일 저장 완료: {file_path.name}")
        except Exception as e:
            # 디버깅 강화: 어떤 파일 작업 중 실패했는지 상세 기록
            self._log(f"❌ [Anki 팀] CSV 백업 저장 중 오류 발생 ({base_name}_{suffix}): {str(e)}")

    def _package_anki_decks(self, decks: List[genanki.Deck], output_path: str) -> Optional[str]:
        """조립 완료된 Anki Deck 객체 리스트를 하나의 .apkg 파일로 압축 및 물리적 저장합니다.

        이 함수는 AnkiService의 최종 출력부로서, 메모리 상에 존재하는 논리적인 genanki.Deck 객체들을 
        실제 Anki 애플리케이션에서 더블 클릭으로 임포트할 수 있는 압축 패키지 형태(.apkg)로 직렬화합니다. 
        비동기 백그라운드 Worker가 처리 결과를 디스크에 안전하게 덤프(Dump)할 수 있도록 
        경로 확인 및 상위 디렉토리 생성(mkdir)을 보장하며, 파일 쓰기 권한 부족 등 
        OS 레벨의 예외 상황에서도 애플리케이션이 크래시되지 않도록 `try-except`로 캡슐화되어 있습니다.

        Args:
            decks (List[genanki.Deck]): 파일로 패키징할 Anki 덱 객체들의 리스트. 리스트가 비어있으면 패키징을 건너뜁니다.
            output_path (str): 생성될 .apkg 파일의 전체 절대 또는 상대 경로.

        Returns:
            Optional[str]: 패키징이 성공적으로 완료되면 저장된 파일의 경로(문자열)를 반환하고, 실패하거나 패키징할 덱이 없으면 None을 반환합니다.
        """
        if not decks:
            return None
        
        try:
            out_path = Path(output_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            genanki.Package(decks).write_to_file(str(out_path))
            return str(out_path)
        except Exception as e:
            self._log(f"❌ [Anki 팀] .apkg 패키징 중 오류 발생 (경로: {output_path}): {str(e)}")
            return None

    # ==========================================
    # 3. 데이터 파싱 로직 (강건성 강화)
    # ==========================================
    def _parse_anki_csv_text(self, raw_csv_text: str) -> Dict[str, List[str]]:
        """LLM으로부터 전달받은 원시 텍스트를 카드 유형별(Basic, MCQ, Cloze)로 분류하여 파싱합니다.

        LLM은 텍스트(예: "Basic | 문제 | 정답")를 한 덩어리의 긴 문자열로 반환합니다. 
        이 메서드는 이러한 비정형/반정형 문자열을 줄바꿈(`\n`) 기준으로 나누고, 
        문자열 앞단의 접두사(Prefix)를 분석하여 해당 라인이 어떤 학습 카드 유형에 속하는지 
        분기(Routing)하는 텍스트 전처리(Preprocessing) 핵심 로직입니다. 
        
        대용량 비동기 처리 시 LLM 응답 포맷이 미세하게 깨지거나 대소문자가 혼용되거나 
        불필요한 공백이 포함될 가능성에 대비하여, `lower()`, `replace()`, `strip()`을 
        조합해 접두사를 엄격하게 검증합니다. 특히 카드 내용물(문제나 정답) 자체에 
        구분자인 파이프(`|`)가 포함되어 분할이 꼬이는 치명적인 에러를 막기 위해, 
        접두사를 떼어낼 때 `split('|', 1)`을 사용하여 단 1회만 분할하도록 강건성(Robustness)을 높였습니다.

        Args:
            raw_csv_text (str): LLM이 생성하여 반환한 원시 CSV 포맷의 문자열 데이터.

        Returns:
            Dict[str, List[str]]: "Basic", "MCQ", "Cloze"를 키로 가지고 각각에 해당하는 
                텍스트 라인들의 리스트를 분류하여 담은 딕셔너리.
        """
        basic_lines, mcq_lines, cloze_lines = [], [], []
        
        for line in raw_csv_text.split('\n'):
            line = line.strip()
            if not line:
                continue
            
            clean_line = line.lower().replace(" ", "")
            
            # 텍스트에 포함된 | 로 인해 오작동하는 것을 방지하기 위해 1번만 분할
            if clean_line.startswith("basic|"):
                basic_lines.append(line.split('|', 1)[1].strip() if '|' in line else line)
            elif clean_line.startswith("mcq|"):
                mcq_lines.append(line.split('|', 1)[1].strip() if '|' in line else line)
            elif clean_line.startswith("cloze|"):
                cloze_lines.append(line.split('|', 1)[1].strip() if '|' in line else line)
            else:
                basic_lines.append(line)
                
        return {"Basic": basic_lines, "MCQ": mcq_lines, "Cloze": cloze_lines}

    # ==========================================
    # 4. 메인 실행 엔트리포인트 (패키징 전담)
    # ==========================================
    def build_apkg_from_csv(self, base_name: str, raw_csv_text: str, target_dir: str) -> Optional[str]:
        """LLM 텍스트 파싱부터 Anki 패키지 빌드까지의 전체 파이프라인을 실행하는 메인 엔트리포인트.

        이 메서드는 Controller(또는 TaskManager)에서 직접 호출되는 퍼블릭 API 역할을 합니다. 
        이전 단계(LLM Service)로부터 넘겨받은 원시 CSV 텍스트를 인풋으로 받아, 
        분류 파싱 -> CSV 백업 저장 -> 카드 타입별 안키 덱(Deck) 생성 -> 노트(Note) 조립 -> .apkg 최종 빌드의 
        순차적인 흐름을 오케스트레이션(Orchestration)합니다. 
        
        자동화 파이프라인 특성상 수백 개의 카드가 한 번에 생성될 수 있으므로, 
        형식에 맞지 않는 텍스트(예: 필드 부족)가 발견되더라도 전체 빌드 프로세스를 중단시키지 않고 
        해당 라인만 로깅 후 건너뛰는(Skip) 방어적 프로그래밍(Defensive Programming)이 적용되어 있습니다. 
        카드 본문에 `|` 기호가 들어가는 엣지 케이스까지 고려하여 최대 2번만 `split`하는 등, 
        비동기 작업 중 발생할 수 있는 데이터 오염(Data Corruption)을 최소화하는 데 집중한 파이프라인 결속부입니다.

        Args:
            base_name (str): 생성될 Anki 덱의 기본 이름 및 파일명 접두사.
            raw_csv_text (str): 파싱 및 변환의 원천 소스가 되는 LLM 생성 텍스트 문자열.
            target_dir (str): 결과물(.csv 및 .apkg)이 저장될 로컬 디렉토리 경로.

        Returns:
            Optional[str]: 최종 .apkg 파일이 성공적으로 생성되었을 경우 해당 파일의 경로를 반환하며, 
                           입력 데이터가 없거나 패키징 중 치명적 오류가 발생한 경우 None을 반환합니다.
        """
        if not raw_csv_text:
            self._log("⚠️ [Anki 팀] 입력된 CSV 데이터가 없습니다.")
            return None

        self._log("✨ [Anki 팀] 데이터 파싱 및 파일 빌드를 시작합니다.")
        
        parsed_data = self._parse_anki_csv_text(raw_csv_text)
        self._save_csv_files(target_dir, base_name, parsed_data)

        basic_model = self._get_basic_model()
        cloze_model = self._get_cloze_model()

        decks = []
        type_mapping = [
            (parsed_data["Basic"], basic_model, f"{base_name}::Basic"),
            (parsed_data["MCQ"], basic_model, f"{base_name}::MCQ"),
            (parsed_data["Cloze"], cloze_model, f"{base_name}::Cloze")
        ]

        for lines, model, deck_name in type_mapping:
            deck = genanki.Deck(self._generate_anki_id(deck_name), deck_name)
            
            for line in lines:
                try:
                    # 안전장치: 내용물(정답/해설)에 | 가 포함되어 있을 경우를 대비해 최대 2번(3등분)만 자름
                    parts = [p.strip() for p in line.split('|', 2)]
                    
                    if len(parts) == 3:
                        field1, field2, raw_tags = parts[0], parts[1], parts[2]
                    elif len(parts) == 2:
                        field1, field2 = parts[0], parts[1]
                        raw_tags = ""
                    else:
                        # 디버깅 강화: 파싱에 실패한 원문 일부를 로그에 남김
                        self._log(f"⚠️ [Anki 팀] 카드 형식 불일치로 건너뜀 (내용: {line[:30]}...)")
                        continue

                    tags = [t.replace('#', '') for t in raw_tags.split()] if raw_tags else []
                    deck.add_note(genanki.Note(model=model, fields=[field1, field2], tags=tags))
                
                except Exception as e:
                    # 디버깅 강화: 예외 발생 시 원문 전체와 에러 메시 기록
                    self._log(f"❌ [Anki 팀] 개별 카드 생성 중 오류. 원문: '{line}' | 에러: {str(e)}")
            
            if len(deck.notes) > 0:
                decks.append(deck)

        target_path = Path(target_dir)
        apkg_path = target_path / f"{base_name}_통합본.apkg"
        result_path = self._package_anki_decks(decks, str(apkg_path))
        
        if result_path:
            self._log(f"📦 [APKG 저장] {Path(result_path).name} 완료")
            
        return result_path