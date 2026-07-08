"""jsonparser 단위 테스트 (표준 JSONPath). 표준 unittest 만 사용."""

import unittest

from jsonparser import (
    AmbiguousTypeError,
    Condition,
    JsonPathError,
    TypeClassifier,
    TypeProfile,
    UnknownTypeError,
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



# 타입별로 구조가 다른 두 JSON --------------------------------------------
A_JSON = {"user": {"id": "U1", "name": "Kim"}}
B_JSON = {"kind": "b", "data": {"user": {"uid": "U2", "fullName": "Lee"}}}


def _make_classifier():
    a = TypeProfile(
        name="a",
        detect=Validator().require("$.user.id"),
        fields={"user_id": "$.user.id", "name": "$.user.name"},
    )
    b = TypeProfile(
        name="b",
        detect=Validator().require("$.data.user.uid"),
        fields={"user_id": "$.data.user.uid", "name": "$.data.user.fullName"},
    )
    return TypeClassifier([a, b], type_field="$.kind")


class TestClassify(unittest.TestCase):
    def test_resolve_by_structure(self):
        clf = _make_classifier()
        self.assertEqual(clf.resolve(A_JSON).name, "a")

    def test_resolve_by_type_field_shortcut(self):
        # kind == "b" 이면 detect 없이도 b 로 채택.
        clf = _make_classifier()
        self.assertEqual(clf.resolve(B_JSON).name, "b")

    def test_type_field_falls_back_to_detect(self):
        # 타입 필드 값이 어느 name 과도 안 맞으면 detect 로 판별.
        clf = _make_classifier()
        data = {"kind": "bogus", "user": {"id": "U9", "name": "X"}}
        self.assertEqual(clf.resolve(data).name, "a")

    def test_normalized_output_is_unified(self):
        clf = _make_classifier()
        r1 = clf.classify(A_JSON)
        r2 = clf.classify(B_JSON)
        # 타입이 달라도 동일한 키 스키마.
        self.assertEqual(r1.type, "a")
        self.assertEqual(r1.data, {"user_id": "U1", "name": "Kim"})
        self.assertEqual(r2.type, "b")
        self.assertEqual(r2.data, {"user_id": "U2", "name": "Lee"})
        self.assertEqual(set(r1.data), set(r2.data))

    def test_unknown_type_raises(self):
        clf = _make_classifier()
        with self.assertRaises(UnknownTypeError):
            clf.classify({"something": "else"})

    def test_require_failure_raises(self):
        a = TypeProfile(
            name="a",
            detect=Validator().require("$.user.id"),
            fields={"user_id": "$.user.id"},
            require=Validator().require("$.user.age", "gte", 18),
        )
        clf = TypeClassifier([a])
        with self.assertRaises(ValueError):
            clf.classify({"user": {"id": "U1", "age": 10}})

    def test_register_chaining(self):
        clf = TypeClassifier()
        clf.register(TypeProfile(
            name="a",
            detect=Validator().require("$.user.id"),
            fields={"user_id": "$.user.id"},
        ))
        self.assertEqual(clf.classify(A_JSON).data, {"user_id": "U1"})

    def test_classify_accepts_json_string(self):
        # 입력을 파싱된 객체가 아니라 JSON 문자열로도 받는다.
        clf = _make_classifier()
        res = clf.classify('{"user": {"id": "U1", "name": "Kim"}}')
        self.assertEqual(res.type, "a")
        self.assertEqual(res.data, {"user_id": "U1", "name": "Kim"})


# 포함관계가 있는 타입들 (A ⊂ B, A ⊂ C) — 등록 순서 무관성 검증 --------------
def _nested_profiles():
    A = TypeProfile("A", detect=Validator().require("$.a"),
                    fields={"a": "$.a"})
    B = TypeProfile("B", detect=Validator().require("$.a").require("$.a.a"),
                    fields={"a": "$.a", "aa": "$.a.a"})
    C = TypeProfile("C", detect=Validator().require("$.a", "eq", "C").require("$.E"),
                    fields={"a": "$.a", "e": "$.E"})
    return A, B, C


class TestSpecificity(unittest.TestCase):
    DOC_A = {"a": 1}
    DOC_B = {"a": {"a": 2}}
    DOC_C = {"a": "C", "E": 99}

    def _check(self, clf):
        self.assertEqual(clf.resolve(self.DOC_A).name, "A")
        self.assertEqual(clf.resolve(self.DOC_B).name, "B")
        self.assertEqual(clf.resolve(self.DOC_C).name, "C")

    def test_order_independent_forward(self):
        A, B, C = _nested_profiles()
        self._check(TypeClassifier([A, B, C]))

    def test_order_independent_reverse(self):
        A, B, C = _nested_profiles()
        self._check(TypeClassifier([C, B, A]))

    def test_most_specific_wins_not_first(self):
        # A 를 먼저 등록해도 B 짜리 JSON 은 B 로 (조건이 더 많이 맞음).
        A, B, C = _nested_profiles()
        self.assertEqual(TypeClassifier([A, B]).resolve(self.DOC_B).name, "B")

    def test_ambiguous_raises(self):
        # 동일하게 구체적인(조건 1개씩) 두 타입이 같은 JSON 에 매칭.
        X = TypeProfile("X", detect=Validator().require("$.a"), fields={"a": "$.a"})
        Y = TypeProfile("Y", detect=Validator().require("$.b"), fields={"b": "$.b"})
        clf = TypeClassifier([X, Y])
        with self.assertRaises(AmbiguousTypeError):
            clf.resolve({"a": 1, "b": 2})


class TestJsonStringInput(unittest.TestCase):
    """모든 공개 함수가 JSON 문자열 입력을 받는지 검증."""

    RAW = '{"user": {"id": "U1", "age": 20}, "items": [{"sku": "A"}]}'

    def test_get_path_from_string(self):
        self.assertEqual(get_path(self.RAW, "$.user.id"), "U1")

    def test_get_all_from_string(self):
        self.assertEqual(get_all(self.RAW, "$.items[*].sku"), ["A"])

    def test_has_path_from_string(self):
        self.assertTrue(has_path(self.RAW, "$.user.age"))

    def test_validate_from_string(self):
        self.assertTrue(validate(self.RAW, [{"path": "$.user.age", "op": "gte", "value": 18}]))

    def test_extract_from_string(self):
        self.assertEqual(extract(self.RAW, {"id": "$.user.id"}), {"id": "U1"})

    def test_bytes_input(self):
        self.assertEqual(get_path(self.RAW.encode(), "$.user.id"), "U1")


if __name__ == "__main__":
    unittest.main(verbosity=2)
