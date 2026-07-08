"""parsers 패키지(버전 인식 파서) 테스트."""

import pytest

from jsonparser import UnknownTypeError, load_file
from parsers import parse_file, CLASSIFIER


# ---- 샘플 데이터 ----------------------------------------------------------
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


def _v2_doc():
    # v2: detector 값 키가 wow -> wowScore
    return {
        "data": {
            "FILT_DATA_STRUCT_042": {
                "detector": [
                    {"name": "alpha", "wowScore": 100},
                    {"name": "beta", "wowScore": "hi"},
                    {"name": "gamma", "wow": 5},  # v2 스키마엔 wowScore 필요 -> skip
                ],
                "zzef": [
                    {"x": 1, "y": 2, "z": 3},
                    {"x": 4, "y": 5, "z": 6},
                ],
            }
        }
    }


# ---- 디스패치 & 파싱 ------------------------------------------------------
def test_v1_dispatch_and_parse():
    kind, out = parse_file(_v1_doc())
    assert kind == "FILT_DATA_STRUCT@v1"
    assert out["result"] == {"alpha": 100, "beta": "hi"}
    assert out["xyz"] == {"x": [1, 4], "y": [2, 5], "z": [3, 6]}


def test_v2_dispatch_and_parse():
    kind, out = parse_file(_v2_doc())
    # wowScore 존재 -> 조건 수가 더 많은 v2 가 우선 채택
    assert kind == "FILT_DATA_STRUCT@v2"
    assert out["result"] == {"alpha": 100, "beta": "hi"}
    assert out["xyz"] == {"x": [1, 4], "y": [2, 5], "z": [3, 6]}


def test_v2_beats_v1_by_specificity():
    # v2 문서는 v1 조건(detector/zzef)도 만족하지만, specificity 로 v2 가 이김
    assert CLASSIFIER.resolve(_v2_doc()).name == "FILT_DATA_STRUCT@v2"


def test_unknown_type_raises():
    with pytest.raises(UnknownTypeError):
        parse_file({"data": {"whatever": {"foo": 1}}})


# ---- 저장 round-trip ------------------------------------------------------
def test_save_roundtrip(tmp_path):
    out_path = tmp_path / "parsed.json"
    kind, out = parse_file(_v1_doc(), save_to=str(out_path))
    reloaded = load_file(str(out_path))
    assert reloaded == {"kind": kind, **out}
