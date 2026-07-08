# jsonparser

표준 **JSONPath** 기반 파이썬 JSON 파싱/검증/추출 유틸리티.
경로 처리는 [`jsonpath-ng`](https://github.com/h2non/jsonpath-ng) 확장 파서를 사용합니다.

## 세 가지 기능

1. **검증 (validate)** — 원하는 JSON 인지 확인. path 존재 여부, 값 비교, 정규식,
   타입 등 여러 조건을 `AND`/`OR` 로 조합해 판정.
2. **조회 (get_path)** — 특정 path 의 값을 스칼라/배열/struct 상관없이 조회.
   와일드카드·필터·재귀 하강으로 여러 값 한 번에 추출.
3. **추출 (extract)** — 여러 path 를 하나의 객체(dict)로 재구성.

## 설치

```bash
pip install -r requirements.txt   # jsonpath-ng
```

## JSONPath 문법 (표준)

| 예시 | 설명 |
|------|------|
| `$.user.name` | 키 접근 (`$` 는 생략 가능: `user.name`) |
| `$.items[0].sku` | 배열 인덱스 |
| `$.items[-1]` | 음수 인덱스(마지막) |
| `$.items[*].sku` | 배열 전체 → 리스트 반환 |
| `$.items[?(@.qty > 0)]` | 필터 |
| `$..name` | 재귀 하강(모든 깊이의 name) |
| `$.config.*` | dict 값 전체 |
| `$."weird.key"` | 키에 `.` 이 포함되면 따옴표 |

## 사용 예

```python
from jsonparser import get_path, validate, extract, Validator

data = {"user": {"id": "U1", "age": 20}, "items": [{"sku": "A", "qty": 1}]}

# 1) 조회
get_path(data, "$.user.id")               # "U1"      (스칼라)
get_path(data, "$.user")                  # {...}     (struct)
get_path(data, "$.items[*].sku")          # ["A"]     (배열/와일드카드)
get_path(data, "$.items[?(@.qty>0)].sku") # ["A"]     (필터)
get_path(data, "$.x.y", default="NA")     # "NA"      (없으면 default)

# 2) 검증
validate(data, [
    {"path": "$.user.id", "op": "exists"},
    {"path": "$.user.age", "op": "gte", "value": 18},
    {"path": "$.items[*].qty", "op": "gt", "value": 0, "match": "all"},
])                                        # True

# 체이닝 스타일
Validator().require("$.user.id").require("$.user.age", "gte", 18).is_valid(data)

# 3) 여러 path → 하나의 객체
extract(data, {
    "id":    "$.user.id",
    "skus":  "$.items[*].sku",
    "cur":   {"path": "$.user.currency", "default": "KRW"},
    "adult": {"path": "$.user.age", "transform": lambda x: x >= 18},
})
# {"id": "U1", "skus": ["A"], "cur": "KRW", "adult": True}
```

## 조회 반환값 규칙

- 매칭 없음 → `default`
- `[*]` · `..` · `[?...]` · 슬라이스 · 유니온 등 **여러 값**을 낼 수 있는 표현식 → 리스트
- 그 외 단일 경로 → 단일 값
- 항상 리스트가 필요하면 `get_all()` 사용

## 지원 연산자 (검증)

`exists`, `eq`, `ne`, `gt`, `gte`, `lt`, `lte`, `in`, `not_in`,
`contains`, `regex`, `type`, `truthy`

여러 값을 내는 path 에는 `match="all"`(모두 만족) 또는 `match="any"`(하나라도) 지정 가능.
필터(`[?(...)]`) 를 써서 조건을 path 안에 직접 표현할 수도 있습니다.

## 실행

```bash
python3 example.py            # 데모
python3 -m unittest -v        # 테스트 (38개)
```
