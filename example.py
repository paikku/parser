"""jsonparser 사용 예제 (표준 JSONPath)."""

import json

from jsonparser import (
    TypeClassifier,
    TypeProfile,
    UnknownTypeError,
    Validator,
    extract,
    get_path,
    has_path,
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


if __name__ == "__main__":
    main()
