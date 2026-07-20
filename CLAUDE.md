# Repository map (read this first, then open only what you need)

이 저장소는 **세 개의 독립 레이어**로 나뉩니다. 작업 대상에 해당하는 쪽만 읽으세요 —
다른 레이어 파일을 컨텍스트에 올릴 필요가 없습니다.

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

## 레이어 3 — 아이템 (원본 파일 → 시각화 레코드 + API)

- **코드+문서:** `items/` 폴더 (각 하위 폴더 `__init__.py` 독스트링이 그 아이템의 문서).
  앱 조립은 루트 `api.py`.
- **테스트:** `test_item_dump.py` (아이템별 `test_item_<이름>.py`)
- **한 아이템 = 한 폴더** (`items/<이름>/`). 그 아이템의 파일 포맷 지식(디코더),
  버전 판별·추출(`extract.py`), "원본 파일 → 레코드" 조립(`pipeline.py`),
  HTTP 표면(`router.py`)을 통째로 소유합니다. 아이템 폴더끼리는 서로 import 하지 않습니다.
- **아이템은 레이어 1·2 를 쓰지 않습니다** — 디코더·추출·파이프라인은 stdlib 만
  (라우터만 fastapi). 디코드 결과는 구조가 결정적인 dict 라 JSONPath 재귀 검색이
  불필요하고, 이 격리 덕에 아이템 폴더를 통째로 다른 프로젝트로 이식할 수 있습니다.
- 현재 아이템: **dump** — FTP dump 세트의 `.tdf`(ZIP) 안 `.dd` 바이너리(TLV)를
  디코드하고, `extract.py` 의 버전 클래스(detect + extract, 정확히-1개-성립)로
  시각화 레코드(`{source, kind, value, xyz, warnings}`)를 만듭니다. `.dd` 포맷
  지식은 `items/dump/` 밖으로 새어나가지 않습니다 (포맷 연구는 decoder 저장소).
- API 실행: `uvicorn api:app` (+ `DUMP_DATA_ROOT=<tdf 폴더>`).

## 작업별 라우팅

| 하려는 일 | 읽을 곳 | 건드릴 곳 |
|-----------|---------|-----------|
| 코어 함수 사용법/시맨틱 확인 | `LLM.md` | — |
| 코어 버그 수정/기능 추가 | `jsonparser.py`, `LLM.md` | `jsonparser.py`, `test_jsonparser.py`, (문서) `LLM.md`/`README.md` |
| **새 파일 버전 파서 추가** | `parsers/README.md` | `parsers/` 새 파일 + `parsers/registry.py` 한 줄, `test_filt_parser.py` |
| 폴더 배치 파싱 실행 | `parsers/README.md` | — (`python -m parsers.example_batch`) |
| **새 아이템 추가** | `items/__init__.py`, `items/dump/` (본보기) | `items/<이름>/` 새 폴더 + `api.py` 마운트 한 줄, `test_item_<이름>.py` |
| dump 버전(.dd 변형) 추가 | `items/dump/extract.py` | `extract.py` 새 클래스 + `VERSIONS` 한 줄, `test_item_dump.py` |
| dump 파이프라인/API 수정 | `items/dump/__init__.py` | `items/dump/`, `test_item_dump.py` |

## 불변 규칙

- 의존은 **한 방향만**: `parsers/` → `jsonparser`. 코어가 `parsers/` 를 import 하지 않게 유지.
- `items/` 는 레이어 1·2 와 **상호 무관**: jsonparser/parsers 를 import 하지 않고
  (stdlib + 라우터의 fastapi 만), 역방향도 금지. 아이템 폴더끼리도 import 금지.
- 새 파서 버전·새 dump 버전 모두 **기존 버전 코드를 수정하지 않고** 추가한다
  (parsers 계약: `parsers/README.md`, dump 계약: `items/dump/extract.py` 독스트링).
- 아이템 파일 포맷 지식은 그 아이템 폴더 안에만 둔다 (예: `.dd`/`.tdf` 는 `items/dump/` 만 안다).
- 테스트는 전 스위트 통과:
  `python -m pytest test_jsonparser.py test_filt_parser.py test_item_dump.py -q`.
