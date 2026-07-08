# jsonparser

표준 **JSONPath** 기반 파이썬 JSON 파싱/검증/추출 유틸리티.
경로 처리는 [`jsonpath-ng`](https://github.com/h2non/jsonpath-ng) 확장 파서를 사용합니다.

## 주요 기능

1. **검증 (validate)** — 원하는 JSON 인지 확인. path 존재 여부, 값 비교, 정규식,
   타입 등 여러 조건을 `AND`/`OR` 로 조합해 판정.
2. **조회 (get_path)** — 특정 path 의 값을 스칼라/배열/struct 상관없이 조회.
   와일드카드·필터·재귀 하강으로 여러 값 한 번에 추출.
3. **추출 (extract)** — 여러 path 를 하나의 객체(dict)로 재구성.
4. **문자열 검색 (find_text · struct_contains_text · find_nodes_with_all)** —
   중첩 구조 안에서 부분문자열을 재귀 검색. 키·값 어디든, 위치(경로)까지.
   여러 문자열을 **동시에** 가진 노드도 찾는다.
5. **타입 분류 (TypeClassifier)** — 타입마다 경로가 다른 JSON 을 판별해
   통합 스키마로 정규화.

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
`contains`, `deep_contains`, `regex`, `type`, `truthy`

- `contains` — 최상위 멤버십(문자열은 부분문자열, dict 는 키 존재, list 는 원소 포함).
- `deep_contains` — **재귀 부분문자열** 검색. struct/배열 하위의 키 이름·문자열 값
  어디든 텍스트가 있으면 참. (아래 [문자열 검색](#문자열-검색-struct-안에서-텍스트-찾기) 참고)

여러 값을 내는 path 에는 `match="all"`(모두 만족) 또는 `match="any"`(하나라도) 지정 가능.
필터(`[?(...)]`) 를 써서 조건을 path 안에 직접 표현할 수도 있습니다.

## 문자열 검색 (struct 안에서 텍스트 찾기)

`$.data` 같은 struct 안에 특정 문자열이 있는지 확인하고 **어디에** 있는지까지
가져온다. 표준 JSONPath 필터(`=~`)와 달리 **키 이름과 값을 모두**, **부분문자열**로,
**깊이 무관**하게 검색하고 매칭 **위치(경로)** 를 돌려준다. (JSONPath `=~` 는 값만,
앞부분 고정(match)이라 부분문자열 아님, 키 검색 불가, 위치 정보 없음.)

```python
from jsonparser import is_struct, struct_contains_text, find_text, find_nodes_with_all

doc = {"data": {"title": "wow deal", "meta": {"wow_score": 9}, "tags": ["ok", "wowza"]}}

# 1) $.data 가 struct(dict) 인가?
is_struct(doc)                     # True   (기본 경로 $.data)
is_struct(doc, "$.data.title")     # False  (문자열이라 struct 아님)

# 2) struct 안에 'wow' 가 있는지 + 위치 가져오기 (기본: 대소문자 구분)
found, hits = struct_contains_text(doc, "wow")   # found == True
for m in hits:
    print(m.path, m.where, m.value)
# $.data.title           value  wow deal
# $.data.meta.wow_score  key    wow_score
# $.data.tags[1]         value  wowza

# 옵션: 대소문자 무시 / 키만 / 값만
struct_contains_text(doc, "WOW", ignore_case=True)   # 대문자도 매칭
struct_contains_text(doc, "wow", values=False)       # 키 이름만 검색
struct_contains_text(doc, "wow", keys=False)         # 문자열 값만 검색

# struct 가 아니면 항상 (False, [])
struct_contains_text({"data": "just wow"}, "wow")    # (False, [])

# 3) 임의의 중첩 구조를 직접 재귀 검색 (배열 인덱스 경로 포함)
find_text({"a": {"b": ["xwowx"]}}, "wow")
# [TextMatch(path='$.a.b[0]', where='value', value='xwowx')]
```

`TextMatch(path, where, value)` — `where` 는 `"key"`(키 이름 매칭) 또는
`"value"`(문자열 값 매칭). int/float/bool 같은 비문자열 스칼라는 검색 대상이
아니다(예: `42000` 은 `"42"` 로 안 잡힘).

### 검증 DSL 로: `deep_contains` 연산자

`validate`/`Validator` 안에서도 재귀 부분문자열 검색을 조건으로 쓸 수 있다.

```python
from jsonparser import validate, Validator

# $.data 가 struct 이면서 'wow' 를 포함하는가
(Validator()
 .require("$.data", "type", "dict")
 .require("$.data", "deep_contains", "wow")
 .is_valid(doc))                                       # True

# 옵션은 dict 로 전달 (text 필수, ignore_case/keys/values 선택)
validate(doc, [{"path": "$.data", "op": "deep_contains",
                "value": {"text": "WOW", "ignore_case": True}}])   # True
```

잘못된 조건(needle 누락·비문자열, 오타 난 옵션 키)은 데이터와 무관하게 즉시
`ValueError` 로 알린다(조용히 넘어가 버그를 숨기지 않음).

### 여러 문자열을 **동시에** 가진 노드 찾기

`find_nodes_with_all(data, *needles)` — 지정한 문자열이 **모두** 나타나는 노드를
`(path, node)` 리스트로 반환한다. 서로 다른 문자열이 같은 서브트리의 **다른
위치**에 있어도 공통 조상이 잡히고, 한 문자열 값 안에 모두 있으면 그 리프도 잡힌다.

```python
doc = {
    "a": {"title": "wow deal", "code": "vmv-1"},           # 둘 다(값)
    "b": {"title": "wow only"},                             # wow 만 → 제외
    "c": {"items": [{"t": "vmv"}, {"t": "say wow now"}]},   # 서브트리에 둘 다
    "d": "wow and vmv in one string",                       # 문자열 하나에 둘 다
    "e": {"vmvKey": {"note": "wow"}},                       # 키 + 값
}

# 'wow' 와 'vmv' 를 동시에 가진 노드 전부
[p for p, _ in find_nodes_with_all(doc, "wow", "vmv")]
# ['$.a', '$.c.items', '$.c', '$.d', '$.e', '$']

# 함께 담는 '최소' 노드만 (자손이 이미 만족하는 조상 $ · $.c 는 제외)
find_nodes_with_all(doc, "wow", "vmv", deepest_only=True)
# [('$.a', {...}), ('$.c.items', [...]),
#  ('$.d', 'wow and vmv in one string'), ('$.e', {...})]

find_nodes_with_all(doc, "wow", "vmv", ignore_case=True)   # 대소문자 무시
find_nodes_with_all(doc, "wow", "vmv", expr="$.c")         # 특정 서브트리로 한정
```

노드 하나가 여러 문자열을 다 가졌는지만 확인하려면 `find_text` 를 needle 마다 AND:

```python
node = {"title": "wow", "code": "vmv"}
all(find_text(node, s) for s in ("wow", "vmv"))           # True
```

> `validate` 는 문자열 입력을 JSON 으로 파싱하므로, **문자열 리프 노드** 를 직접
> 검사할 때는 `deep_contains` 대신 `find_text` 를 쓴다.

## 타입 분류 (타입마다 경로가 다를 때)

같은 계열의 JSON 이라도 구조/경로가 서로 다른 여러 타입인 경우, "JSON 분석 → 타입 판별 →
타입별 경로로 정규화" 를 라이브러리가 담당한다. 호출자는 타입 분기 코드를 쓰지 않고,
**타입이 뭐든 동일한 통합 스키마**를 돌려받는다.

```python
from jsonparser import TypeClassifier, TypeProfile, Validator, UnknownTypeError

clf = TypeClassifier(
    profiles=[
        TypeProfile(
            name="a",
            detect=Validator().require("$.user.id"),                 # 구조로 감지
            fields={"user_id": "$.user.id", "name": "$.user.name"},  # a 타입 경로
        ),
        TypeProfile(
            name="b",
            detect=Validator().require("$.data.user.uid"),
            fields={"user_id": "$.data.user.uid", "name": "$.data.user.fullName"},  # b 타입 경로
        ),
    ],
    type_field="$.kind",   # (선택) 값이 프로필 name 과 같으면 즉시 채택하는 지름길
)

clf.classify({"user": {"id": "U1", "name": "Kim"}})
# -> ClassifyResult(type="a", data={"user_id": "U1", "name": "Kim"})

clf.classify({"kind": "b", "data": {"user": {"uid": "U2", "fullName": "Lee"}}})
# -> ClassifyResult(type="b", data={"user_id": "U2", "name": "Lee"})

clf.classify('{"user": {"id": "U9", "name": "Park"}}')   # JSON 문자열 입력도 허용
clf.classify({"unknown": "shape"})                       # -> UnknownTypeError
```

구성 요소:

- **`TypeProfile`** — 타입 하나. `detect`(이 타입인지 판정하는 `Validator`),
  `fields`(타입별 논리명→JSONPath 매핑 = `extract` 매핑), `require`(선택, 이 타입 필수조건).
- **`TypeClassifier`** — 프로필 목록과 선택적 `type_field`.
  - `resolve(data)` : `type_field` 값이 프로필 `name` 과 맞으면 즉시 채택, 아니면
    `detect` 통과 프로필 중 **가장 구체적인(조건이 가장 많이 맞는) 것** 채택.
    **등록 순서 무관.** 매칭 없으면 `UnknownTypeError`, 동점이면 `AmbiguousTypeError`.
  - `classify(data)` : 판별 → `require` 검증 → 정규화 → `ClassifyResult(type, data)`.

### 타입을 점진적으로 늘려갈 때 (포함관계)

타입이 서로를 포함하는 형태로 계속 추가되는 경우 — 예를 들어
`A`(=`$.a` 존재) → `B`(=`$.a` + `$.a.a`) → `C`(=`$.a=='C'` + `$.E`) — 각 타입을
`TypeProfile` 로 선언만 하면 된다. `B`·`C` 는 `A` 의 조건을 포함하지만,
`resolve` 는 **가장 구체적인 타입**을 고르므로 등록 순서에 상관없이 올바르게 판별한다.

```python
clf = TypeClassifier([
    TypeProfile("A", detect=Validator().require("$.a"), fields={"a": "$.a"}),
    TypeProfile("B", detect=Validator().require("$.a").require("$.a.a"),
                fields={"a": "$.a", "aa": "$.a.a"}),
    TypeProfile("C", detect=Validator().require("$.a", "eq", "C").require("$.E"),
                fields={"a": "$.a", "e": "$.E"}),
])
clf.resolve({"a": 1}).name              # "A"
clf.resolve({"a": {"a": 2}}).name       # "B"  (A 도 매칭되지만 더 구체적인 B)
clf.resolve({"a": "C", "E": 9}).name    # "C"
```

새 타입은 목록 아무 위치에 추가하면 되고, 두 타입이 똑같이 구체적인데 동시에 매칭되면
`AmbiguousTypeError` 로 알려주므로 조건 설계 실수를 조기에 잡을 수 있다.

## 입력 형식

모든 공개 함수(`get_path`, `get_all`, `has_path`, `validate`, `extract`,
`struct_contains_text`, `find_nodes_with_all`,
`TypeClassifier.classify`/`resolve`)는 **파싱된 파이썬 객체**뿐 아니라
**JSON 문자열/바이트**도 그대로 받는다. 문자열이면 내부에서 한 번 파싱한다.

```python
get_path('{"user": {"id": "U1"}}', "$.user.id")   # "U1"
```

### 입력 불변 보장

전달한 파이썬 객체는 조회/검증 중에 **변형되지 않는다**. (`jsonpath-ng` 확장
파서가 dict 에 필터 `[?(...)]` 를 적용할 때 입력을 in-place 로 바꾸던 버그를
임포트 시점에 근본 패치한다.)

```python
doc = {"data": {"meta": {"wow_score": 9}}}
get_path(doc, "$.data..*[?(@ =~ '.*wow.*')]")
doc["data"]["meta"]        # {"wow_score": 9}  (그대로 — list 로 손상되지 않음)
```

## 실행

```bash
python3 example.py            # 데모
python3 -m unittest -v        # 테스트 (95개)
```
