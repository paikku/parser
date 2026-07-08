"""jsonparser 사용 예제."""

from jsonparser import Validator, extract, get_path, has_path, validate

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
    # ── 기능 2: 조회 (스칼라 / struct / 배열 / 와일드카드) ──────────────
    print("== 조회 ==")
    print("status      :", get_path(sample, "order.status"))            # 스칼라
    print("customer    :", get_path(sample, "order.customer"))          # struct
    print("first item  :", get_path(sample, "order.items[0].name"))     # 인덱스
    print("last item   :", get_path(sample, "order.items[-1].name"))    # 음수 인덱스
    print("all skus    :", get_path(sample, "order.items[*].sku"))      # 와일드카드 -> 리스트
    print("all tags    :", get_path(sample, "order.items[*].tags[*]"))  # 중첩 와일드카드
    print("missing     :", get_path(sample, "order.no.such", default="<없음>"))

    # ── 기능 1: 검증 ─────────────────────────────────────────────────
    print("\n== 검증 ==")
    # (A) 딕셔너리 조건 리스트로 즉시 검증
    ok = validate(sample, [
        {"path": "order.id", "op": "exists"},
        {"path": "order.status", "op": "in", "value": ["paid", "shipped"]},
        {"path": "order.customer.age", "op": "gte", "value": 18},
        {"path": "order.items[*].qty", "op": "gt", "value": 0, "match": "all"},
    ])
    print("주문 유효 :", ok)

    # (B) Validator 체이닝
    v = (Validator()
         .require("order.amount", "gte", 10000)
         .require("order.customer.vip", "eq", True)
         .require("meta.source", "regex", r"^(web|app)$"))
    print("VIP 조건 :", v.is_valid(sample))
    for row in v.explain(sample):
        print("   ", row["path"], row["op"], "->", row["passed"], "(actual:", row["actual"], ")")

    # (C) OR 로직
    any_ok = validate(sample, [
        {"path": "order.status", "op": "eq", "value": "refunded"},
        {"path": "order.status", "op": "eq", "value": "paid"},
    ], logic="or")
    print("OR 검증  :", any_ok)

    # ── 기능 3: 여러 path -> 하나의 객체 ────────────────────────────
    print("\n== 추출 ==")
    projected = extract(sample, {
        "order_id":  "order.id",
        "buyer":     "order.customer.id",
        "total":     "order.amount",
        "skus":      "order.items[*].sku",
        "names":     {"path": "order.items[*].name"},
        "currency":  {"path": "order.currency", "default": "KRW"},
        "big_order": {"path": "order.amount", "transform": lambda x: x >= 40000},
    })
    import json
    print(json.dumps(projected, ensure_ascii=False, indent=2))

    print("\nhas_path(order.customer.vip):", has_path(sample, "order.customer.vip"))


if __name__ == "__main__":
    main()
