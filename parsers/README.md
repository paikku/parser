# parsers — 버전 인식 파일 파서 레이어

> **이 폴더만 보면 됩니다.** 파싱 코어(`../jsonparser.py`, 레퍼런스 `../LLM.md`)를
> *소비*하는 상위 레이어입니다. 의존은 **단방향**: `parsers/` → `jsonparser`.
> 코어는 이 폴더를 전혀 모릅니다. 코어 API가 궁금할 때만 `../LLM.md`를 여세요.

파일 종류/버전마다 **검증(어떤 파일인지 판별)** 과 **파싱(값 추출)** 이 달라지는 상황을
다룹니다. 새 버전을 추가해도 **기존 버전 코드는 절대 건드리지 않도록** 설계돼 있습니다.

## 구성

| 파일 | 역할 |
|------|------|
| `filt_data_struct.py` | `FiltDataStructV1` — 한 버전. detect(`build`) + 파싱(`normalize`) 을 통째로 소유 |
| `registry.py` | `PROFILES` 목록 + `CLASSIFIER` + `parse_file()` — **버전 등록/디스패치 지점** |
| `__init__.py` | 공개 API 재노출 (`parse_file`, `CLASSIFIER`, `PROFILES`, `FiltDataStructV1`) |
| `example_batch.py` | 폴더 배치 처리 예시 (추상화 없음) |

## 동작 모델

- 디스패치는 코어의 `TypeClassifier`가 담당한다. 등록된 프로필 중 **`detect` 가 통과하고
  가장 구체적인(= detect 조건 수가 가장 많은) 것** 을 등록 순서와 무관하게 선택한다.
  매칭 없음 → `UnknownTypeError`, 동점 → `AmbiguousTypeError`.
- **한 버전 = `TypeProfile` 서브클래스 하나.**
  - `build()` — 그 버전의 `detect`(구조 조건 `Validator`)를 만들어 프로필 인스턴스 생성.
    `name=` 문자열이 곧 **버전 식별자**이자 `parse_file` 이 돌려주는 `kind`.
  - `normalize(self, data)` — 그 버전의 파싱을 **자유롭게** 구현. 코어의
    `find_text`/`get_path`/`get_all`/`extract`/`Validator` 를 직접 쓴다.
    반환 스키마는 현재 `{"result": {...}, "xyz": {"x":[],"y":[],"z":[]}}`.
- **헬퍼/공통 베이스는 일부러 없다.** "버전마다 무엇이 바뀔지"(노드 위치·이름·배열 키·
  필드명·구조)를 미리 못박지 않기 위함. 구조가 통째로 달라지는 버전은 자기 `normalize()`
  안에서 평범한 파이썬으로 처리하면 된다. 두 버전 이상이 실제로 코드를 중복하기 시작하면
  그때 순수 함수로 뽑는다(YAGNI) — 가변 상태 객체로는 만들지 말 것.

## "버전 명시"는 어디에?

1. **버전 정의(이름)** — 각 프로필 `build()` 의 `name="FILT_DATA_STRUCT@v1"`.
2. **버전 등록(판별 대상)** — `registry.py` 의 `PROFILES` 리스트. **여기 없으면 클래스가
   있어도 시스템은 모른다.** ← 새 버전을 알리는 유일한 지점.
3. **(배치 예시에서) 저장할 버전 지정** — `example_batch.py` 의 `--only` / `DEFAULT_ALLOWED`.

## 새 버전 추가하기 (기존 것 안 망가지게)

1. **새 파일**을 만든다 (기존 버전 파일은 수정하지 않는다). 예: `parsers/filt_data_struct_v2.py`

   ```python
   from typing import Any
   from jsonparser import TypeProfile, Validator, find_text, get_path, get_all, extract

   class FiltDataStructV2(TypeProfile):
       @classmethod
       def build(cls) -> "FiltDataStructV2":
           # v1 조건 + 그 버전을 특정하는 '추가' 조건 → 조건 수가 늘어 v1 보다 구체적.
           detect = (Validator()
                     .require("$.data..detector")
                     .require("$.data..zzef")
                     .require("$.data..detector[*].wowScore"))   # v2 전용 구조 신호
           return cls(name="FILT_DATA_STRUCT@v2", detect=detect, fields={})

       def normalize(self, data: Any) -> dict:
           # 이 버전만의 파싱. 코어 함수를 자유롭게 사용.
           ...
           return {"result": ..., "xyz": ...}
   ```

2. `registry.py` 의 `PROFILES` 에 **한 줄** 추가:

   ```python
   from .filt_data_struct_v2 import FiltDataStructV2
   PROFILES = [
       FiltDataStructV1.build(),
       FiltDataStructV2.build(),   # ← 추가
   ]
   ```

3. `test_filt_parser.py` 에 그 버전용 샘플 문서 + assert 를 추가한다. (JSONPath 오타는
   조용히 빈 결과를 내므로, 실제 샘플 테스트가 유일한 정확성 방어선이다.)

## ⚠️ 기존 것을 깨뜨리는 함정 (반드시 확인)

- **specificity 동점 → `AmbiguousTypeError`.** 새 버전의 `detect` 는 겹치는 구버전보다
  조건이 **엄격히 더 많아야** 이긴다. "구조는 같고 이름만 다른" 경우가 대표적 함정 —
  구조 조건이 똑같으면 v1 과 동점이 된다. `deep_contains`(키 이름) 같은 **구별 조건**을
  하나 더 넣어 조건 수를 벌리고, 동시에 그 조건이 구버전 문서에서는 **거짓**이 되게 한다.
- **구버전 문서 가로채기 금지.** 새 detect 는 옛 문서에서 `False` 여야 한다. 그래야 옛
  문서가 계속 옛 버전으로 간다. (다중/재귀 경로 + `exists` 는 "매칭이 하나도 없으면 실패",
  `type`/`match="any"` 는 "하나라도 맞으면 통과" — 이 성질로 구버전을 배제한다.)
- **G1: 문자열 leaf 를 `Validator`/`deep_contains` 에 직접 넘기면 JSON 파싱 시도로 예외.**
  배열 원소 검증 전에는 항상 `isinstance(item, dict)` 가드를 먼저.
- **`deep_contains` 는 스펙을 즉시 검증(G2).** `value` 는 문자열이거나 `{"text": ...}`
  옵션 dict 여야 한다. `value` 를 빠뜨리면 데이터와 무관하게 `ValueError`.
- **다중 경로 반환은 리스트(G7).** `[*]`/`..` 에는 `get_all` 을 쓴다. 단일 스칼라를
  기대하고 `get_path` 를 쓰면 리스트가 와서 어긋난다.
- **`detect` 와 `normalize` 의 기준이 다를 수 있음.** 현재 v1 의 `detect` 는
  `$.data..detector/..zzef` 존재만 보고, `normalize` 는 키 이름에 `"FILT_DATA_STRUCT"` 를
  포함한 노드만 추출한다. 마커 없는 노드만 있는 문서는 detect 는 통과하되 결과가 빌 수 있다.
  새 버전에서 이 정합성이 중요하면 `detect` 에도 마커 조건(`deep_contains`)을 넣어라.
- **출력 스키마 변경은 소비자도 함께.** `normalize` 반환 형태(`{"result","xyz"}`)는
  `example_batch.py` 와 테스트가 의존한다. 바꾸려면 소비자도 같이 고친다.

## 사용

```python
from parsers import parse_file
kind, out = parse_file(data)                 # data: dict 또는 JSON 문자열/바이트
kind, out = parse_file(data, save_to="o.json")  # 결과를 파일로도 저장
```

배치 예시 (repo 루트에서):

```bash
python -m parsers.example_batch <input_dir> <output_dir>
python -m parsers.example_batch samples out --only FILT_DATA_STRUCT@v1
python -m parsers.example_batch samples out --only FILT_DATA_STRUCT@v1 FILT_DATA_STRUCT@v2  # 여러 개 지정 가능
```

## 테스트

```bash
python -m pytest test_filt_parser.py -q     # 이 레이어
python -m pytest test_jsonparser.py -q      # 코어 (이 레이어 변경은 코어에 영향 없어야 함)
```
