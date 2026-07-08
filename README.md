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

## 버전 인식 파싱 (버전마다 경로가 다를 때)

같은 종류의 JSON 이라도 버전에 따라 구조/경로가 다른 경우, "JSON 분석 → 버전 판별 →
버전별 경로로 정규화" 를 라이브러리가 담당한다. 호출자는 버전 분기 코드를 쓰지 않고,
**버전이 뭐든 동일한 통합 스키마**를 돌려받는다.

```python
from jsonparser import VersionedParser, VersionProfile, Validator, UnknownVersionError

parser = VersionedParser(
    profiles=[
        VersionProfile(
            name="v1",
            detect=Validator().require("$.user.id"),                 # 구조로 감지
            fields={"user_id": "$.user.id", "name": "$.user.name"},  # v1 경로
        ),
        VersionProfile(
            name="v2",
            detect=Validator().require("$.data.user.uid"),
            fields={"user_id": "$.data.user.uid", "name": "$.data.user.fullName"},  # v2 경로
        ),
    ],
    version_field="$.apiVersion",   # (선택) 값이 프로필 name 과 같으면 즉시 채택하는 지름길
)

parser.parse({"user": {"id": "U1", "name": "Kim"}})
# -> ParseResult(version="v1", data={"user_id": "U1", "name": "Kim"})

parser.parse({"apiVersion": "v2", "data": {"user": {"uid": "U2", "fullName": "Lee"}}})
# -> ParseResult(version="v2", data={"user_id": "U2", "name": "Lee"})

parser.parse({"unknown": "shape"})   # -> UnknownVersionError
```

구성 요소:

- **`VersionProfile`** — 버전 하나. `detect`(이 버전인지 판정하는 `Validator`),
  `fields`(버전별 논리명→JSONPath 매핑 = `extract` 매핑), `require`(선택, 이 버전 필수조건).
- **`VersionedParser`** — 프로필 목록과 선택적 `version_field`.
  - `resolve(data)` : `version_field` 값이 프로필 `name` 과 맞으면 즉시 채택, 아니면
    `detect` 통과 프로필 중 **가장 구체적인(조건이 가장 많이 맞는) 것** 채택.
    **등록 순서 무관.** 매칭 없으면 `UnknownVersionError`, 동점이면 `AmbiguousVersionError`.
  - `parse(data)` : 판별 → `require` 검증 → 정규화 → `ParseResult(version, data)`.

### 버전을 점진적으로 늘려갈 때 (포함관계)

버전이 서로를 포함하는 형태로 계속 추가되는 경우 — 예를 들어
`A`(=`$.a` 존재) → `B`(=`$.a` + `$.a.a`) → `C`(=`$.a=='C'` + `$.E`) — 각 버전을
`VersionProfile` 로 선언만 하면 된다. `B`·`C` 는 `A` 의 조건을 포함하지만,
`resolve` 는 **가장 구체적인 버전**을 고르므로 등록 순서에 상관없이 올바르게 판별한다.

```python
parser = VersionedParser([
    VersionProfile("A", detect=Validator().require("$.a"), fields={"a": "$.a"}),
    VersionProfile("B", detect=Validator().require("$.a").require("$.a.a"),
                   fields={"a": "$.a", "aa": "$.a.a"}),
    VersionProfile("C", detect=Validator().require("$.a", "eq", "C").require("$.E"),
                   fields={"a": "$.a", "e": "$.E"}),
])
parser.resolve({"a": 1}).name              # "A"
parser.resolve({"a": {"a": 2}}).name       # "B"  (A 도 매칭되지만 더 구체적인 B)
parser.resolve({"a": "C", "E": 9}).name    # "C"
```

새 버전은 목록 아무 위치에 추가하면 되고, 두 버전이 똑같이 구체적인데 동시에 매칭되면
`AmbiguousVersionError` 로 알려주므로 조건 설계 실수를 조기에 잡을 수 있다.

## 실행

```bash
python3 example.py            # 데모
python3 -m unittest -v        # 테스트 (49개)
```
