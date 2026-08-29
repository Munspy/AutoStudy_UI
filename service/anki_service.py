# service/anki_service.py
import hashlib
from pathlib import Path
from typing import Dict, List, Optional
import genanki
from base.base_service import BaseService

class AnkiGenerationService(BaseService):
    """
    LLM이 생성한 CSV 텍스트 데이터를 파싱하여 
    분류(Basic, Cloze, MCQ) 및 .apkg 파일 패키징 I/O를 전담하는 단일 책임 서비스입니다.
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
        """문자열 기반 고유 해시 ID 생성 (genanki Deck/Model 고유 식별자용)"""
        return int(hashlib.sha256(name.encode('utf-8')).hexdigest(), 16) % (10**9)

    def _get_basic_model(self) -> genanki.Model:
        """Basic 및 MCQ 카드용 팩토리 메서드"""
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
        """Cloze 카드용 팩토리 메서드"""
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
        """분류된 Basic, MCQ, Cloze 텍스트를 개별 CSV 파일로 백업 저장 (안전한 I/O)"""
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
        """조립된 Genanki Deck 리스트를 최종 .apkg 파일로 패키징 (안전한 I/O)"""
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
        """LLM 응답 텍스트를 Basic, MCQ, Cloze 라인으로 분류 파싱"""
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
        """
        LLM으로부터 전달받은 완성된 CSV 텍스트를 파싱하여 모델/노드를 생성하고,
        최종 .apkg 파일로 빌드합니다.
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
                    # 디버깅 강화: 예외 발생 시 원문 전체와 에러 메시지 기록
                    self._log(f"❌ [Anki 팀] 개별 카드 생성 중 오류. 원문: '{line}' | 에러: {str(e)}")
            
            if len(deck.notes) > 0:
                decks.append(deck)

        target_path = Path(target_dir)
        apkg_path = target_path / f"{base_name}_통합본.apkg"
        result_path = self._package_anki_decks(decks, str(apkg_path))
        
        if result_path:
            self._log(f"📦 [APKG 저장] {Path(result_path).name} 완료")
            
        return result_path