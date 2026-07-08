"""parsers 패키지(버전 인식 파서) 테스트.

핵심 목적 두 가지:
1) v1 이 올바로 판별/파싱/저장되는가.
2) **구조가 통째로 다른 새 버전**을 v1 을 한 줄도 고치지 않고 추가할 수 있는가
   (= 확장성이 실제로 성립하는가).
"""

import pytest

from jsonparser import (
    TypeProfile, TypeClassifier, Validator, UnknownTypeError, load_file,
    find_text, get_path, get_all,
)
from parsers import parse_file, CLASSIFIER


# ---- 샘플 데이터 (v1) -----------------------------------------------------
def _v1_doc():
    return {
        "data": {
            "FILT_DATA_STRUCT_001": {
                "detector": [
                    {"name": "alpha", "wow": 100, "extra": "ignore"},
                    {"name": "beta", "wow": "hi"},
                    "not-a-struct",           # dict 아님 -> skip
                    {"noName": 1, "wow": 9},  # name 없음 -> skip
                    {"name": "gamma"},        # wow 없음 -> skip
                ],
                "zzef": [
                    {"x": 1, "y": 2, "z": 3},
                    {"x": 4, "y": 5, "z": 6},
                    {"x": 7, "y": 8},         # z 없음 -> skip
                ],
            },
            "OTHER": {  # FILT_DATA_STRUCT 아님 -> 무시
                "detector": [{"name": "nope", "wow": -1}],
                "zzef": [{"x": 9, "y": 9, "z": 9}],
            },
        }
    }


# ---- v1 판별 & 파싱 & 저장 ------------------------------------------------
def test_v1_dispatch_and_parse():
    kind, out = parse_file(_v1_doc())
    assert kind == "FILT_DATA_STRUCT@v1"
    assert out["result"] == {"alpha": 100, "beta": "hi"}
    assert out["xyz"] == {"x": [1, 4], "y": [2, 5], "z": [3, 6]}


def test_unknown_type_raises():
    with pytest.raises(UnknownTypeError):
        parse_file({"data": {"whatever": {"foo": 1}}})


def test_save_roundtrip(tmp_path):
    out_path = tmp_path / "parsed.json"
    kind, out = parse_file(_v1_doc(), save_to=str(out_path))
    reloaded = load_file(str(out_path))
    assert reloaded == {"kind": kind, **out}


# ==========================================================================
# 확장성 증명: 구조가 통째로 다른 새 버전(detector 가 배열이 아니라
# dict-of-objects {id: {name, wow}})을 v1 수정 없이 추가.
#   - 새 버전은 자기 normalize() 안에서 dict detector 를 직접 순회(자유 파싱).
#   - 이 클래스는 테스트 안에만 존재 → 프로덕션 코드를 전혀 건드리지 않음을 증명.
# ==========================================================================
class _FiltV2Nested(TypeProfile):
    @classmethod
    def build(cls):
        detect = (Validator()
                  .require("$.data..detector")
                  .require("$.data..zzef")
                  # detector 가 dict 인 문서만 (v1 문서의 list detector 는 걸러짐).
                  # 조건 3개 > v1 의 2개 → 겹쳐도 specificity 로 이 버전이 우선.
                  .require("$.data..detector", op="type", value="dict", match="any"))
        return cls(name="FILT_DATA_STRUCT@v2-nested", detect=detect, fields={})

    def normalize(self, data):
        zz = Validator().require("$.x").require("$.y").require("$.z")
        result, xyz = {}, {"x": [], "y": [], "z": []}
        for m in find_text(get_path(data, "$.data"), "FILT_DATA_STRUCT",
                           keys=True, values=False, base="$.data"):
            node = get_path(data, m.path)
            detector = get_path(node, "$.detector")     # bespoke: dict-of-objects
            if isinstance(detector, dict):
                for obj in detector.values():
                    if isinstance(obj, dict) and "name" in obj and "wow" in obj:
                        result[obj["name"]] = obj["wow"]
            for s in get_all(node, "$.zzef[*]"):        # zzef 는 그대로
                if isinstance(s, dict) and zz.is_valid(s):
                    xyz["x"].append(s["x"])
                    xyz["y"].append(s["y"])
                    xyz["z"].append(s["z"])
        return {"result": result, "xyz": xyz}


def _v2_nested_doc():
    return {
        "data": {
            "FILT_DATA_STRUCT_x": {
                "detector": {                      # 배열이 아니라 dict!
                    "id1": {"name": "alpha", "wow": 100},
                    "id2": {"name": "beta", "wow": "hi"},
                    "id3": {"noName": 1},          # name/wow 없음 -> skip
                },
                "zzef": [
                    {"x": 1, "y": 2, "z": 3},
                    {"x": 4, "y": 5, "z": 6},
                ],
            }
        }
    }


def _extended_classifier():
    # v1(프로덕션 그대로) + 새 구조 버전. 기존 코드는 손대지 않음.
    return TypeClassifier(profiles=list(CLASSIFIER.profiles) + [_FiltV2Nested.build()])


def test_new_structure_version_added_without_editing_v1():
    clf = _extended_classifier()

    # 새 구조 문서 → 새 버전으로 판별/파싱
    res = clf.classify(_v2_nested_doc())
    assert res.type == "FILT_DATA_STRUCT@v2-nested"
    assert res.data["result"] == {"alpha": 100, "beta": "hi"}
    assert res.data["xyz"] == {"x": [1, 4], "y": [2, 5], "z": [3, 6]}

    # 기존 v1 문서는 여전히 v1 으로 (새 버전이 훔쳐가지 않음)
    res_v1 = clf.classify(_v1_doc())
    assert res_v1.type == "FILT_DATA_STRUCT@v1"
    assert res_v1.data["result"] == {"alpha": 100, "beta": "hi"}
