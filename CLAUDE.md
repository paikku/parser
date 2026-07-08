# Repository map (read this first, then open only what you need)

이 저장소는 **두 개의 독립 레이어**로 나뉩니다. 작업 대상에 해당하는 쪽만 읽으세요 —
반대쪽 파일을 컨텍스트에 올릴 필요가 없습니다.

## 레이어 1 — 파싱 코어 (범용 JSON 유틸리티)

- **코드:** `jsonparser.py` (단일 파일, stdlib + `jsonpath-ng`)
- **문서:** `LLM.md` (전체 API·연산자·시맨틱·함정의 기계용 레퍼런스), `README.md` (사람용)
- **테스트:** `test_jsonparser.py`
- get/validate/extract/text-search/classify 다섯 기능. **`parsers/` 를 전혀 모릅니다.**
- 코어 API 질문(함수 시그니처, 연산자, JSONPath 시맨틱)은 **`LLM.md` 만** 읽으면 답이 나옵니다.
  `jsonparser.py` 전체를 grep 하지 마세요.

## 레이어 2 — 앱 파서 (버전 인식 파일 파서)

- **코드+문서:** `parsers/` 폴더. 시작점은 **`parsers/README.md`**.
- **테스트:** `test_filt_parser.py`
- 파일 종류/버전을 판별해 값을 추출하는 상위 레이어. 코어를 `from jsonparser import ...`
  로 **단방향** 소비합니다.
- 파서 추가/수정 작업은 **`parsers/` 와 `test_filt_parser.py` 안에서 끝납니다.**
  `jsonparser.py` 는 건드리지 않습니다.

## 작업별 라우팅

| 하려는 일 | 읽을 곳 | 건드릴 곳 |
|-----------|---------|-----------|
| 코어 함수 사용법/시맨틱 확인 | `LLM.md` | — |
| 코어 버그 수정/기능 추가 | `jsonparser.py`, `LLM.md` | `jsonparser.py`, `test_jsonparser.py`, (문서) `LLM.md`/`README.md` |
| **새 파일 버전 파서 추가** | `parsers/README.md` | `parsers/` 새 파일 + `parsers/registry.py` 한 줄, `test_filt_parser.py` |
| 폴더 배치 파싱 실행 | `parsers/README.md` | — (`python -m parsers.example_batch`) |

## 불변 규칙

- 의존은 **한 방향만**: `parsers/` → `jsonparser`. 코어가 `parsers/` 를 import 하지 않게 유지.
- 새 파서 버전은 **기존 버전 코드를 수정하지 않고** 추가한다 (자세한 계약은 `parsers/README.md`).
- 테스트는 두 스위트 모두 통과: `python -m pytest test_jsonparser.py test_filt_parser.py -q`.
