# jsonparser

외부 의존성 없는(표준 라이브러리만) 파이썬 JSON 파싱/검증/추출 유틸리티.

## 세 가지 기능

1. **검증 (validate)** — 원하는 JSON 인지 확인. path 존재 여부, 값 비교, 정규식,
   타입 등 여러 조건을 `AND`/`OR` 로 조합해 판정.
2. **조회 (get_path)** — 특정 path 의 값을 스칼라/배열/struct 상관없이 조회.
   와일드카드로 여러 값 한 번에 추출.
3. **추출 (extract)** — 여러 path 를 하나의 객체(dict)로 재구성.

## Path 문법

| 예시 | 설명 |
|------|------|
| `user.name` | dict 키 접근 |
| `items[0].id` | 배열 인덱스 |
| `items[-1]` | 음수 인덱스(마지막) |
| `items[*].id` | 배열 전체 순회 → 리스트 반환 |
| `config.*` | dict 값 전체 순회 → 리스트 반환 |
| `a\.b` | 키에 포함된 `.` 은 백슬래시로 이스케이프 |

## 사용 예

```python
from jsonparser import get_path, validate, extract, Validator

data = {"user": {"id": "U1", "age": 20}, "items": [{"sku": "A", "qty": 1}]}

# 1) 조회
get_path(data, "user.id")             # "U1"           (스칼라)
get_path(data, "user")                # {...}          (struct)
get_path(data, "items[*].sku")        # ["A"]          (배열/와일드카드)
get_path(data, "x.y", default="NA")   # "NA"           (없으면 default)

# 2) 검증
validate(data, [
    {"path": "user.id", "op": "exists"},
    {"path": "user.age", "op": "gte", "value": 18},
    {"path": "items[*].qty", "op": "gt", "value": 0, "match": "all"},
])                                    # True

# 체이닝 스타일
Validator().require("user.id").require("user.age", "gte", 18).is_valid(data)

# 3) 여러 path → 하나의 객체
extract(data, {
    "id":    "user.id",
    "skus":  "items[*].sku",
    "cur":   {"path": "user.currency", "default": "KRW"},
    "adult": {"path": "user.age", "transform": lambda x: x >= 18},
})
# {"id": "U1", "skus": ["A"], "cur": "KRW", "adult": True}
```

## 지원 연산자 (검증)

`exists`, `eq`, `ne`, `gt`, `gte`, `lt`, `lte`, `in`, `not_in`,
`contains`, `regex`, `type`, `truthy`

와일드카드 path 에는 `match="all"`(모두 만족) 또는 `match="any"`(하나라도) 지정 가능.

## 실행

```bash
python3 example.py            # 데모
python3 -m unittest -v        # 테스트 (34개)
```
