"""jsonparser 단위 테스트 (표준 JSONPath). 표준 unittest 만 사용."""

import unittest

from jsonparser import (
    Condition,
    JsonPathError,
    Validator,
    extract,
    get_all,
    get_path,
    has_path,
    validate,
)

DATA = {
    "user": {"id": "U1", "name": "Kim", "age": 20, "roles": ["admin", "user"]},
    "items": [
        {"sku": "A", "qty": 1, "tags": ["x"]},
        {"sku": "B", "qty": 3, "tags": ["y", "z"]},
    ],
    "flag": False,
    "empty": None,
    "config": {"a": 1, "b": 2},
    "weird.key": "dot",
}


class TestGetPath(unittest.TestCase):
    def test_scalar(self):
        self.assertEqual(get_path(DATA, "$.user.name"), "Kim")

    def test_leading_dollar_optional(self):
        self.assertEqual(get_path(DATA, "user.name"), "Kim")

    def test_struct(self):
        self.assertEqual(get_path(DATA, "$.user")["id"], "U1")

    def test_index(self):
        self.assertEqual(get_path(DATA, "$.items[0].sku"), "A")

    def test_negative_index(self):
        self.assertEqual(get_path(DATA, "$.items[-1].sku"), "B")

    def test_out_of_range(self):
        self.assertIsNone(get_path(DATA, "$.items[9].sku"))

    def test_wildcard_array(self):
        self.assertEqual(get_path(DATA, "$.items[*].sku"), ["A", "B"])

    def test_nested_wildcard(self):
        self.assertEqual(get_path(DATA, "$.items[*].tags[*]"), ["x", "y", "z"])

    def test_dict_wildcard(self):
        self.assertEqual(sorted(get_path(DATA, "$.config.*")), [1, 2])

    def test_recursive_descent(self):
        self.assertEqual(get_path(DATA, "$..sku"), ["A", "B"])

    def test_filter(self):
        # qty > 1 인 아이템 필터
        got = get_path(DATA, "$.items[?(@.qty > 1)].sku")
        self.assertEqual(got, ["B"])

    def test_default(self):
        self.assertEqual(get_path(DATA, "$.no.such", default="D"), "D")

    def test_none_value_is_returned_not_default(self):
        # 값이 실제 None 이면 default 로 대체되지 않아야 함 (경로는 존재).
        self.assertIsNone(get_path(DATA, "$.empty", default="D"))

    def test_dotted_key(self):
        self.assertEqual(get_path(DATA, '$."weird.key"'), "dot")

    def test_get_all_always_list(self):
        self.assertEqual(get_all(DATA, "$.user.name"), ["Kim"])
        self.assertEqual(get_all(DATA, "$.no.such"), [])

    def test_invalid_path_raises(self):
        with self.assertRaises(JsonPathError):
            get_path(DATA, "$.items[")


class TestHasPath(unittest.TestCase):
    def test_true(self):
        self.assertTrue(has_path(DATA, "$.user.roles[1]"))

    def test_false(self):
        self.assertFalse(has_path(DATA, "$.user.roles[5]"))

    def test_wildcard_true(self):
        self.assertTrue(has_path(DATA, "$.items[*].sku"))

    def test_none_value_path_exists(self):
        self.assertTrue(has_path(DATA, "$.empty"))


class TestValidate(unittest.TestCase):
    def test_exists_and(self):
        self.assertTrue(validate(DATA, [
            {"path": "$.user.id"},
            {"path": "$.items[0].sku", "op": "eq", "value": "A"},
        ]))

    def test_missing_fails(self):
        self.assertFalse(validate(DATA, [{"path": "$.user.email"}]))

    def test_exists_false(self):
        self.assertTrue(validate(DATA, [
            {"path": "$.user.email", "op": "exists", "value": False},
        ]))

    def test_comparisons(self):
        self.assertTrue(validate(DATA, [{"path": "$.user.age", "op": "gte", "value": 20}]))
        self.assertFalse(validate(DATA, [{"path": "$.user.age", "op": "gt", "value": 20}]))

    def test_in(self):
        self.assertTrue(validate(DATA, [
            {"path": "$.user.name", "op": "in", "value": ["Kim", "Lee"]},
        ]))

    def test_contains(self):
        self.assertTrue(validate(DATA, [
            {"path": "$.user.roles", "op": "contains", "value": "admin"},
        ]))

    def test_regex(self):
        self.assertTrue(validate(DATA, [
            {"path": "$.user.id", "op": "regex", "value": r"^U\d+$"},
        ]))

    def test_type(self):
        self.assertTrue(validate(DATA, [{"path": "$.user.age", "op": "type", "value": "int"}]))
        self.assertTrue(validate(DATA, [{"path": "$.empty", "op": "type", "value": "null"}]))

    def test_truthy_on_false_flag(self):
        self.assertTrue(validate(DATA, [{"path": "$.flag", "op": "truthy", "value": False}]))

    def test_wildcard_all(self):
        self.assertTrue(validate(DATA, [
            {"path": "$.items[*].qty", "op": "gt", "value": 0, "match": "all"},
        ]))
        self.assertFalse(validate(DATA, [
            {"path": "$.items[*].qty", "op": "gt", "value": 1, "match": "all"},
        ]))

    def test_wildcard_any(self):
        self.assertTrue(validate(DATA, [
            {"path": "$.items[*].qty", "op": "gt", "value": 2, "match": "any"},
        ]))

    def test_filter_exists(self):
        # 필터 자체로 조건 표현: qty>=3 인 아이템이 존재하는가
        self.assertTrue(validate(DATA, [
            {"path": "$.items[?(@.qty >= 3)]", "op": "exists"},
        ]))

    def test_or_logic(self):
        self.assertTrue(validate(DATA, [
            {"path": "$.user.age", "op": "eq", "value": 99},
            {"path": "$.user.age", "op": "eq", "value": 20},
        ], logic="or"))

    def test_unknown_operator_raises(self):
        with self.assertRaises(ValueError):
            Condition("$.user.id", op="bogus").check(DATA)

    def test_validator_chain_and_explain(self):
        v = Validator().require("$.user.id").require("$.user.age", "gte", 18)
        self.assertTrue(v.is_valid(DATA))
        report = v.explain(DATA)
        self.assertEqual(len(report), 2)
        self.assertTrue(all(r["passed"] for r in report))


class TestExtract(unittest.TestCase):
    def test_basic_projection(self):
        out = extract(DATA, {
            "id": "$.user.id",
            "skus": "$.items[*].sku",
        })
        self.assertEqual(out, {"id": "U1", "skus": ["A", "B"]})

    def test_default_and_transform(self):
        out = extract(DATA, {
            "currency": {"path": "$.user.currency", "default": "KRW"},
            "adult": {"path": "$.user.age", "transform": lambda x: x >= 18},
        })
        self.assertEqual(out, {"currency": "KRW", "adult": True})

    def test_global_default(self):
        out = extract(DATA, {"x": "$.no.path"}, default="NA")
        self.assertEqual(out, {"x": "NA"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
