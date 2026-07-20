"""SCAN_ROW_DATA_STRUCT@v1 프로필 테스트.

JSONPath 오타는 조용히 빈 결과를 내므로, 실제 샘플 테스트가 유일한
정확성 방어선이다 (parsers/README 계약).
"""

import pytest

from jsonparser import UnknownTypeError
from parsers import parse_file


def scan_doc(marker="IFEU_SCAN_ROW_DATA_STRUCT_007"):
    return {"data": {marker: {
        "detector": [
            {"name": "det_a", "intensities": [10, 20, 30]},
            {"name": "det_b", "intensities": [1.5, 2.5, 3.5]},
            "not-a-dict",                       # G1: 문자열 leaf 는 가드로 스킵
            {"name": "no_intensities"},         # 조건 미달 스킵
        ],
        "ws_positions": [
            {"x": 0.1, "y": 0.0, "z": 5.0},
            {"x": 0.2, "y": 0.0, "z": 5.5},
            {"x": 0.3, "y": 0.0, "z": 6.0},
        ],
    }}}


def test_scan_row_v1_basic():
    kind, out = parse_file(scan_doc())
    assert kind == "SCAN_ROW_DATA_STRUCT@v1"
    # 시각화 계약: value = 채널별 배열, xyz = 좌표 배열, 길이 일치
    assert out["value"] == {"det_a": [10, 20, 30], "det_b": [1.5, 2.5, 3.5]}
    assert out["xyz"] == {"x": [0.1, 0.2, 0.3], "y": [0.0, 0.0, 0.0],
                          "z": [5.0, 5.5, 6.0]}
    assert out["warnings"] == []


def test_length_mismatch_warns_but_keeps_channel():
    doc = scan_doc()
    node = doc["data"]["IFEU_SCAN_ROW_DATA_STRUCT_007"]
    node["detector"].append({"name": "short", "intensities": [9]})
    kind, out = parse_file(doc)
    assert kind == "SCAN_ROW_DATA_STRUCT@v1"
    assert out["value"]["short"] == [9]           # 채널은 유지 (부분 성공)
    assert any("길이 불일치" in w and "short" in w for w in out["warnings"])


def test_non_list_intensities_dropped_with_warning():
    doc = scan_doc()
    node = doc["data"]["IFEU_SCAN_ROW_DATA_STRUCT_007"]
    node["detector"].append({"name": "scalar", "intensities": 42})
    _, out = parse_file(doc)
    assert "scalar" not in out["value"]
    assert any("scalar" in w for w in out["warnings"])


def test_marker_missing_is_unknown_not_empty():
    """detect 에 마커 조건이 있으므로, 구조만 같고 마커 없는 문서는
    '통과 후 빈 결과'가 아니라 UnknownTypeError 로 떨어진다."""
    doc = {"data": {"SOME_OTHER_NODE": {
        "detector": [{"name": "a", "intensities": [1]}],
        "ws_positions": [{"x": 1, "y": 2, "z": 3}],
    }}}
    with pytest.raises(UnknownTypeError):
        parse_file(doc)


def test_filt_v1_not_hijacked():
    """기존 FILT v1 문서는 여전히 FILT 로 간다 (가로채기 금지 계약)."""
    doc = {"data": {"FILT_DATA_STRUCT_001": {
        "detector": [{"name": "alpha", "wow": 100}],
        "zzef": [{"x": 1, "y": 2, "z": 3}],
    }}}
    kind, out = parse_file(doc)
    assert kind == "FILT_DATA_STRUCT@v1"
    assert out["result"] == {"alpha": 100}
