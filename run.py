"""PyCharm에서 우클릭 → Run 으로 폴더 배치 파싱을 실행하는 진입점.

INPUT_DIR / OUTPUT_DIR 만 바꿔서 쓰면 된다.
(CLI 로도 동일 실행: python -m parsers.example_batch samples out)
"""

from pathlib import Path

from parsers.example_batch import run, DEFAULT_ALLOWED

HERE = Path(__file__).resolve().parent

INPUT_DIR = HERE / "samples"      # 입력 JSON 폴더 (여기만 바꾸면 됨)
OUTPUT_DIR = HERE / "out"         # 결과 저장 폴더
ALLOWED = DEFAULT_ALLOWED         # 저장할 버전. 특정 버전만: {"FILT_DATA_STRUCT@v1"}

if __name__ == "__main__":
    run(str(INPUT_DIR), str(OUTPUT_DIR), ALLOWED)
