import pdfplumber
import re
import pandas as pd 
import os

PDF_PATH       = r"C:\Users\82103\OneDrive - UNIST\바탕 화면\2022_산업위생관리기사_2회.pdf"
ANSWER_KEY_CSV = r"C:\Users\82103\OneDrive - UNIST\바탕 화면\answer_key.csv"
OUTPUT_CSV     = "final_questions_with_key.csv"


def load_answer_key(csv_path):
    """
    answer_key.csv를 읽어서 {문제번호(int): 정답(int)} 딕셔너리로 반환
    만약 answer_key.csv가 없거나 파싱 오류가 있으면 빈 딕셔너리를 반환
    """
    if not os.path.exists(csv_path):
        print(f"[WARN] '{csv_path}' 파일이 없습니다. correct_answer 칼럼이 비어 있게 됩니다.")
        return {}

    try:
        df_key = pd.read_csv(csv_path, dtype={"question_no": int, "correct_answer": int})
        key_map = {int(row.question_no): int(row.correct_answer) for row in df_key.itertuples()}
        return key_map
    except Exception as e:
        print(f"[ERROR] 정답 Key 로딩 중 오류: {e}")
        return {}


def extract_from_two_columns(pdf_path):
    """
    pdfplumber를 이용해 PDF를 페이지별 / 좌우칼럼(두 개)으로 나누어 텍스트 추출.
    각 칼럼(왼쪽/오른쪽)에서 문제 번호, 지문, 선택지(①~④)를 파싱하여 리스트로 반환.
    """
    results = []   # [(문제번호(int), 전체텍스트(str)), ...]

    with pdfplumber.open(pdf_path) as pdf:
        for page_idx, page in enumerate(pdf.pages, start=1):
            w, h = page.width, page.height

            # 좌우 두 개 영역으로 나눈 뒤, 각각 텍스트 뽑기
            left_bbox  = (0,           0, w/2, h)
            right_bbox = (w/2 + 1e-3,  0, w,   h)  # w/2 바로 아래를 +마이크로 단위로 찢기

            left_region_text  = page.crop(bbox=left_bbox).extract_text()  or ""
            right_region_text = page.crop(bbox=right_bbox).extract_text() or ""

            for region_text in (left_region_text, right_region_text):
                if not region_text or region_text.strip() == "":
                    continue

                # PDF 페이지 안에 있는 텍스트 전체를 이어붙인 뒤, 정규표현식으로 "숫자. 내용" 점검
                # 문제 번호 패턴: “^\s*(\d{1,3})\.\s” (문자열 맨앞 또는 줄바꿈 직후에 1~3자리 숫자 + 점 + 공백)
                # ※ PDF 내부에서 “1.중량물…”처럼 점 뒤에 공백이 없는 경우도 있으므로 \.\s? 로 수정할 수 있지만,
                #    일단 점 뒤에 최소 공백 한 칸이 있다고 가정했습니다. 없는 경우는 수동 확인 요망.
                pattern = re.compile(r'(?m)^\s*(\d{1,3})\.\s')

                parts = pattern.split(region_text)
                # split 결과 예시: ["미리텍스트...", "7", " 온도 25℃ ...", "8", " 산업위생전문가 ...", ...]
                # 짝수 인덱스(1,3,5,…)는 번호, 짝수+1 인덱스(2,4,6,…)는 해당 번호의 지문+선택지

                # parts[0]는 첫 번째 문제 번호 이전의 불필요 문자열(예: 페이지 헤더). 무시
                for idx in range(1, len(parts), 2):
                    raw_qnum = parts[idx].strip()
                    raw_text = parts[idx + 1].strip()
                    try:
                        qnum_int = int(raw_qnum)
                    except:
                        # 번호 변환이 안 되면 무시
                        continue
                    results.append((qnum_int, raw_text))

    return results  # [(7, "...①선택지①...②선택지②..."), (8, "..."), ...]


def parse_question_chunk(qnum, chunk):
    """
    하나의 문제 청크(지문+선택지 묶음)에서,
    - question_text
    - option_1, option_2, option_3, option_4
    를 뽑아내려고 시도한다. 실패하면 note에 오류를 남김.
    """
    record = {
        "question_no":    qnum,
        "question_text":  "",
        "option_1":       "",
        "option_2":       "",
        "option_3":       "",
        "option_4":       "",
        "note":           ""
    }

    text = chunk.replace("\n", " ").strip()

    # "①"~"④" 기호를 찾아서 인덱스를 구한다.
    # 유니코드: ①(\u2460), ②(\u2461), ③(\u2462), ④(\u2463)
    symbols = list(re.finditer(r"[①②③④]", text))
    if len(symbols) < 4:
        # 옵션 기호가 4개 미만이면(즉, 이미지나 표로 들어가 있는 경우 추출 못 함)
        record["note"] = "이미지로 인해 텍스트 추출 불가"
        return record

    # 기호 4개가 발견된 경우 → 지문과 4개의 선택지로 분리 시도
    try:
        # ① 기호가 등장하기 전까지가 question_text
        first_sym_pos = symbols[0].start()
        record["question_text"] = text[:first_sym_pos].strip()

        # 4개의 옵션 텍스트 뽑기
        opts = []
        for i in range(4):
            start = symbols[i].start() + 1  # 기호 바로 뒤부터 시작
            end = symbols[i+1].start() if i < 3 else len(text)
            opts.append(text[start:end].strip())

        record["option_1"] = opts[0]
        record["option_2"] = opts[1]
        record["option_3"] = opts[2]
        record["option_4"] = opts[3]

    except Exception as e:
        record["note"] = "옵션 텍스트 파싱 오류"
    return record


if __name__ == "__main__":
    # 0) 파일 존재 여부 확인
    if not os.path.exists(PDF_PATH):
        print(f"[ERROR] PDF 파일이 '{PDF_PATH}' 경로에 없습니다. 경로를 확인하세요.")
        exit(1)

    # 1) 답안 키 파일 로드
    answer_key_map = load_answer_key(ANSWER_KEY_CSV)

    # 2) PDF에서 좌우칼럼별로 “문제 번호 → (지문+선택지)” 묶음 추출
    raw_chunks = extract_from_two_columns(PDF_PATH)
    print(f"추출된 원본 청크 개수: {len(raw_chunks)}")

    # 3) 문제 번호별로 중복 없이 정리 (사전형으로 보관했다가, 최종적으로 sorted 처리)
    tmp_dict = {}
    for qnum, chunk in raw_chunks:
        # 만약 같은 번호가 두 번 이상 추출되었다면, 덮어쓰거나 건너뛰기(if you prefer)
        if qnum in tmp_dict:
            # 이미 존재하면 나중에 한 번만 덮어씀
            pass
        tmp_dict[qnum] = chunk

    # 4) 1번 ~ 100번 순서대로 record 리스트 구성
    final_records = []
    for i in range(1, 101):
        if i not in tmp_dict:
            # PDF에서 아예 못 뽑아 온 문제
            final_records.append({
                "question_no":    i,
                "question_text":  "",
                "option_1":       "",
                "option_2":       "",
                "option_3":       "",
                "option_4":       "",
                "correct_answer": "",
                "note":           "이미지로 인해 텍스트 추출 불가"
            })
            continue

        # 실제 청크가 있으면 파싱 시도
        chunk = tmp_dict[i]
        rec = parse_question_chunk(i, chunk)

        # 정답 키가 있으면 correct_answer 칼럼 채움
        rec["correct_answer"] = answer_key_map.get(i, "")

        final_records.append(rec)

    # 5) pandas DataFrame으로 변환 후 CSV로 저장
    df = pd.DataFrame(final_records, columns=[
        "question_no", "question_text",
        "option_1", "option_2", "option_3", "option_4",
        "correct_answer", "note"
    ])
    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
    print(f"완료: '{OUTPUT_CSV}' 파일을 생성했습니다. 총 {len(df)}개 행.")