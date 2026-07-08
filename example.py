"""jsonparser 사용 예제 (표준 JSONPath)."""

import json

from jsonparser import (
    TypeClassifier,
    TypeProfile,
    UnknownTypeError,
    Validator,
    extract,
    find_text,
    get_path,
    has_path,
    is_struct,
    struct_contains_text,
    validate,
)

sample = {
    "order": {
        "id": "ORD-1001",
        "status": "paid",
        "amount": 42000,
        "customer": {"id": "U-77", "age": 31, "vip": True},
        "items": [
            {"sku": "A1", "name": "키보드", "qty": 1, "tags": ["electronics"]},
            {"sku": "B2", "name": "마우스", "qty": 2, "tags": ["electronics", "sale"]},
        ],
    },
    "meta": {"source": "web", "version": 3},
}


def main() -> None:
    # ── 기능 2: 조회 (스칼라 / struct / 배열 / 와일드카드 / 필터) ────────
    print("== 조회 ==")
    print("status      :", get_path(sample, "$.order.status"))              # 스칼라
    print("customer    :", get_path(sample, "$.order.customer"))            # struct
    print("first item  :", get_path(sample, "$.order.items[0].name"))       # 인덱스
    print("last item   :", get_path(sample, "$.order.items[-1].name"))      # 음수 인덱스
    print("all skus    :", get_path(sample, "$.order.items[*].sku"))        # 와일드카드 -> 리스트
    print("all tags    :", get_path(sample, "$.order.items[*].tags[*]"))    # 중첩 와일드카드
    print("qty>1 sku   :", get_path(sample, "$.order.items[?(@.qty > 1)].sku"))  # 필터
    print("any name    :", get_path(sample, "$..name"))                     # 재귀 하강
    print("missing     :", get_path(sample, "$.order.no.such", default="<없음>"))

    # ── 기능 1: 검증 ─────────────────────────────────────────────────
    print("\n== 검증 ==")
    # (A) 딕셔너리 조건 리스트로 즉시 검증
    ok = validate(sample, [
        {"path": "$.order.id", "op": "exists"},
        {"path": "$.order.status", "op": "in", "value": ["paid", "shipped"]},
        {"path": "$.order.customer.age", "op": "gte", "value": 18},
        {"path": "$.order.items[*].qty", "op": "gt", "value": 0, "match": "all"},
    ])
    print("주문 유효 :", ok)

    # (B) Validator 체이닝
    v = (Validator()
         .require("$.order.amount", "gte", 10000)
         .require("$.order.customer.vip", "eq", True)
         .require("$.meta.source", "regex", r"^(web|app)$"))
    print("VIP 조건 :", v.is_valid(sample))
    for row in v.explain(sample):
        print("   ", row["path"], row["op"], "->", row["passed"], "(actual:", row["actual"], ")")

    # (C) JSONPath 필터 자체를 조건으로: sale 태그가 붙은 아이템이 있는가
    print("sale 존재:", validate(sample, [
        {"path": "$.order.items[?(@.tags[*] == 'sale')]", "op": "exists"},
    ]))

    # (D) OR 로직
    any_ok = validate(sample, [
        {"path": "$.order.status", "op": "eq", "value": "refunded"},
        {"path": "$.order.status", "op": "eq", "value": "paid"},
    ], logic="or")
    print("OR 검증  :", any_ok)

    # (E) deep_contains: struct 하위(키+값) 어디든 부분문자열이 있는가.
    #     - contains 는 최상위 멤버십만; deep_contains 는 깊이 무관 + 키 이름까지.
    print("마우스 포함:", validate(sample, [
        {"path": "$.order", "op": "deep_contains", "value": "마우스"},
    ]))
    print("sku 키 존재(대소문자 무시):", validate(sample, [
        {"path": "$.order", "op": "deep_contains",
         "value": {"text": "SKU", "ignore_case": True}},
    ]))
    # 값 위치까지 알고 싶으면 struct_contains_text (동일 코어 재사용)
    found, hits = struct_contains_text(sample, "electronics", expr="$.order")
    print("electronics 위치:", found, [(m.path, m.where) for m in hits])

    # ── 기능 3: 여러 path -> 하나의 객체 ────────────────────────────
    print("\n== 추출 ==")
    projected = extract(sample, {
        "order_id":  "$.order.id",
        "buyer":     "$.order.customer.id",
        "total":     "$.order.amount",
        "skus":      "$.order.items[*].sku",
        "names":     {"path": "$.order.items[*].name"},
        "currency":  {"path": "$.order.currency", "default": "KRW"},
        "big_order": {"path": "$.order.amount", "transform": lambda x: x >= 40000},
    })
    print(json.dumps(projected, ensure_ascii=False, indent=2))

    print("\nhas_path($.order.customer.vip):", has_path(sample, "$.order.customer.vip"))

    # ── 기능 4: 버전 인식 파싱 (버전마다 경로가 다른 경우) ───────────────
    print("\n== 타입 분류 ==")
    # 타입 a 와 b 는 user 정보를 담는 위치/키가 서로 다르다.
    a_json = {"user": {"id": "U1", "name": "Kim"}}
    b_json = {"kind": "b", "data": {"user": {"uid": "U2", "fullName": "Lee"}}}

    clf = TypeClassifier(
        profiles=[
            TypeProfile(
                name="a",
                detect=Validator().require("$.user.id"),          # 구조로 감지
                fields={"user_id": "$.user.id", "name": "$.user.name"},
            ),
            TypeProfile(
                name="b",
                detect=Validator().require("$.data.user.uid"),
                fields={"user_id": "$.data.user.uid", "name": "$.data.user.fullName"},
            ),
        ],
        type_field="$.kind",   # 있으면 값으로 바로 타입 채택
    )

    for name, doc in [("a_json", a_json), ("b_json", b_json)]:
        res = clf.classify(doc)
        # 타입이 뭐든 res.data 는 항상 {user_id, name} 통합 스키마.
        print(f"{name}: type={res.type} data={res.data}")

    # 입력을 JSON 문자열로 그대로 받아도 된다.
    res = clf.classify('{"user": {"id": "U9", "name": "Park"}}')
    print("from json str:", res.type, res.data)

    try:
        clf.classify({"unknown": "shape"})
    except UnknownTypeError as exc:
        print("unknown  :", exc)

    # ── 기능 5: 포함관계 타입, 등록 순서 무관 (가장 구체적인 것 우선) ─────
    print("\n== 포함관계 타입 (순서 무관) ==")
    # A: a 만 / B: a + a.a / C: a=='C' 이면서 E 존재.  B·C 는 A 를 포함한다.
    nested = TypeClassifier([
        TypeProfile("A", detect=Validator().require("$.a"),
                    fields={"a": "$.a"}),
        TypeProfile("B", detect=Validator().require("$.a").require("$.a.a"),
                    fields={"a": "$.a", "aa": "$.a.a"}),
        TypeProfile("C", detect=Validator().require("$.a", "eq", "C").require("$.E"),
                    fields={"a": "$.a", "e": "$.E"}),
    ])
    for label, doc in [("a만", {"a": 1}),
                       ("a+a.a", {"a": {"a": 2}}),
                       ("a=='C'+E", {"a": "C", "E": 99})]:
        print(f"  {label:12s} -> {nested.resolve(doc).name}")  # A 먼저 등록됐어도 B/C 로

    # ── 기능 6: struct 안 문자열(부분문자열) 검색 ─────────────────────────
    # "$.data 가 struct 이면 그 안에 'wow' 가 있는지 확인하고 위치까지 가져오기"
    print("\n== 문자열 검색 (struct 안 'wow') ==")
    wow_doc = {
        "type": "event",
        "data": {
            "title": "WOW such deal",              # 값(대문자 WOW)
            "meta": {"wow_score": 9, "note": "meh"},  # 키(wow_score)
            "tags": ["new", "wowza", "hot"],        # 배열 값(wowza)
            "count": 3,
            "flag": True,
        },
    }

    # (1) $.data 가 struct(dict) 인가?
    print("is_struct($.data)     :", is_struct(wow_doc))              # True
    print("is_struct(문자열 data) :", is_struct({"data": "wow"}))      # False

    # (2) struct 면 'wow' 포함 확인 + 위치 가져오기 (기본: 대소문자 구분)
    found, hits = struct_contains_text(wow_doc, "wow")
    print("contains 'wow'        :", found)
    for m in hits:
        print(f"   {m.path:28s} [{m.where:5s}] -> {m.value!r}")

    # (3) 대소문자 무시하면 값 'WOW such deal' 까지 매칭
    _, ci = struct_contains_text(wow_doc, "wow", ignore_case=True)
    print("ignore_case 매칭 수    :", len(ci), "->", [m.value for m in ci])

    # (4) 키만 / 값만 좁혀서 검색
    _, keys_only = struct_contains_text(wow_doc, "wow", values=False)  # 키 이름만
    _, vals_only = struct_contains_text(wow_doc, "wow", keys=False)    # 값만
    print("키 이름만 매칭         :", [m.value for m in keys_only])
    print("값만 매칭             :", [m.value for m in vals_only])

    # (5) struct 가 아니면 무조건 (False, [])
    print("data 가 문자열        :", struct_contains_text({"data": "just wow"}, "wow"))
    print("data 없음            :", struct_contains_text({"x": 1}, "wow"))

    # (6) 검증 DSL 한 줄로: struct 이면서 'wow' 포함 (deep_contains 연산자)
    v = (Validator()
         .require("$.data", "type", "dict")
         .require("$.data", "deep_contains", "wow"))
    print("검증(struct+wow)      :", v.is_valid(wow_doc))

    # (7) deep_contains 옵션 dict (대소문자 무시 / 값만 검색)
    print("deep_contains WOW(ci) :", validate(wow_doc, [
        {"path": "$.data", "op": "deep_contains",
         "value": {"text": "WOW", "ignore_case": True}}]))

    # (8) find_text 단독: 임의 중첩 구조 재귀 검색 (배열 인덱스 경로 포함)
    blob = {"a": {"b": ["xwowx", {"c": "no"}]}, "wowKey": 1}
    print("find_text 중첩 검색    :",
          [(m.path, m.where) for m in find_text(blob, "wow")])

    # (9) JSON 문자열/바이트 입력도 그대로 허용
    print("from json str         :", struct_contains_text(json.dumps(wow_doc), "wow")[0])

    # (10) 다른 경로에도 적용 (expr 지정) — 위 order 샘플에서 'electronics' 찾기
    found, hits = struct_contains_text(sample, "electron", expr="$.order")
    print("order 안 'electron'    :", found, [m.path for m in hits])


if __name__ == "__main__":
    main()
