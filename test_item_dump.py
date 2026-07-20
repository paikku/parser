"""dump 아이템 테스트 — ddformat 디코더 · extract 추출 · pipeline · API.

실서버/실코퍼스 없이 돈다: 합성 `.dd` 바이트(스펙 규칙대로 인코딩 + 정식
체크섬)와 합성 `.tdf`(ZIP) 픽스처가 전체 경로를 구동한다.
"""

import struct
import zipfile
from pathlib import Path

import pytest

from items.dump.ddformat import (
    MAGIC, TRAILER_LEN, DecodeResult, decode_dd, detect_format,
    dd_trailer_ok, iter_tdf, trailer_checksum,
)
from items.dump.extract import (
    AmbiguousVersionError, UnknownVersionError, dispatch,
)
from items.dump.pipeline import find_tdf_files, run_tdf, run_tree

# ── 합성 .dd 인코더 (DD_FORMAT_SPEC 규칙) ───────────────────────────────


def _cstr(s: str) -> bytes:
    return s.encode() + b"\x00"


def f_str(name: str, val: str) -> bytes:      # 문자열 필드
    return b"\x09" + _cstr(name) + b"\x09" + _cstr(val)


def f_f64(name: str, v: float) -> bytes:      # float64 필드
    return b"\x09" + _cstr(name) + b"\x08" + struct.pack(">d", v)


def f_i8(name: str, v: int) -> bytes:         # int8 값 캐리어(0x04) 필드
    return b"\x09" + _cstr(name) + b"\x04" + struct.pack(">b", v)


def f_struct(name: str, body: bytes) -> bytes:
    return b"\x09" + _cstr(name) + b"\x0b" + body + b"\x00"


def f_array(name: str, body: bytes) -> bytes:
    return b"\x09" + _cstr(name) + b"\x0a" + body + b"\x00"


def elem_struct(body: bytes) -> bytes:        # 배열의 무명 struct 원소
    return b"\x0b" + body + b"\x00"


def elem_f64(v: float) -> bytes:
    return b"\x08" + struct.pack(">d", v)


def make_dd(body: bytes) -> bytes:
    """MAGIC + 최상위 STRUCT(멤버들) + END + 정식 체크섬 트레일러"""
    payload = MAGIC + b"\x0b" + body + b"\x00"
    h = 0
    for b in payload:
        h = (h * 17 + b) & 0xFFFFFFFF
    return payload + h.to_bytes(TRAILER_LEN, "big")


def machine_config_dd() -> bytes:
    """스펙 §1.4 예제 상당: 설정 struct (스캔 데이터 아님 → 파이프라인 스킵 대상)"""
    inner = (f_f64("lens_magnification", 0.25)
             + f_str("if_sim_mode", "SIM_DISABLED")
             + f_str("hw_timestamp_transmission", "TRUE"))
    return make_dd(f_struct("IFEUCM_machine_configuration_struct", inner))


def scan_row_dd() -> bytes:
    """스캔 행 데이터: detector 2채널 + ws_positions 3점"""
    det_a = elem_struct(f_str("name", "det_a")
                        + f_array("intensities",
                                  elem_f64(10.0) + elem_f64(20.0) + elem_f64(30.0)))
    det_b = elem_struct(f_str("name", "det_b")
                        + f_array("intensities",
                                  elem_f64(1.5) + elem_f64(2.5) + elem_f64(3.5)))
    positions = b"".join(
        elem_struct(f_f64("x", x) + f_f64("y", 0.0) + f_f64("z", z))
        for x, z in [(0.1, 5.0), (0.2, 5.5), (0.3, 6.0)]
    )
    inner = (f_array("detector", det_a + det_b)
             + f_array("ws_positions", positions))
    return make_dd(f_struct("IFEU_SCAN_ROW_DATA_STRUCT", inner))


# ── ddformat: 디코더 ────────────────────────────────────────────────────


def test_decode_machine_config_roundtrip():
    res = decode_dd(machine_config_dd(), name="cfg.dd")
    assert isinstance(res, DecodeResult)
    assert res.format == "binary" and res.magic_ok
    assert res.trailer_ok is True and res.boundary_ok
    assert res.ok and res.warnings == []
    assert res.tree == {"IFEUCM_machine_configuration_struct": {
        "lens_magnification": 0.25,
        "if_sim_mode": "SIM_DISABLED",
        "hw_timestamp_transmission": "TRUE",
    }}


def test_decode_scan_row_roundtrip():
    res = decode_dd(scan_row_dd(), name="scan.dd")
    assert res.ok
    node = res.tree["IFEU_SCAN_ROW_DATA_STRUCT"]
    assert node["detector"][0] == {"name": "det_a", "intensities": [10.0, 20.0, 30.0]}
    assert node["ws_positions"][1] == {"x": 0.2, "y": 0.0, "z": 5.5}


def test_array_zero_markers_and_int8_values():
    """0x02/0x03 = payload 없는 0 마커, 0x04 = 실제 int8 값 (스펙 §1.5-2)"""
    body = f_array("position_nrs",
                   b"\x02\x02\x03"                       # 0, 0, 0
                   + b"\x04\x02" + b"\x04\x03")           # 2, 3
    res = decode_dd(make_dd(body))
    assert res.ok
    assert res.tree["position_nrs"] == [0, 0, 0, 2, 3]


def test_array_bare_strings_and_named_container():
    """0x09 원소 이형: bare 문자열 vs 이름있는 컨테이너 (스펙 §1.5-1)"""
    bare = f_array("valid_values", b"\x09" + _cstr("TRUE") + b"\x09" + _cstr("FALSE"))
    named = f_array("dmap", b"\x09" + _cstr("abc") + b"\x0b" + f_i8("v", 7) + b"\x00")
    res = decode_dd(make_dd(bare + named))
    assert res.ok
    assert res.tree["valid_values"] == ["TRUE", "FALSE"]
    assert res.tree["dmap"] == [{"abc": {"v": 7}}]


def test_checksum_mismatch_is_warning_not_fatal():
    raw = bytearray(machine_config_dd())
    raw[-1] ^= 0xFF                                       # 트레일러 파손
    res = decode_dd(bytes(raw))
    assert res.trailer_ok is False and not res.ok
    assert any("체크섬" in w for w in res.warnings)
    assert res.tree["IFEUCM_machine_configuration_struct"]  # 구조는 파싱됨


def test_trailer_checksum_helpers():
    raw = scan_row_dd()
    assert dd_trailer_ok(raw)
    assert trailer_checksum(raw) == int.from_bytes(raw[-TRAILER_LEN:], "big")


def test_text_format_detected_and_skipped():
    text = b"{\n  IFX_STRUCT = {\n    logn_id = 2,\n  }\n}\n"
    assert detect_format(text) == "text"
    res = decode_dd(text, name="note.dd")
    assert res.tree == {} and not res.ok


# ── extract: 순수 파이썬 추출 (jsonparser 미사용) ───────────────────────


def scan_tree(marker="IFEU_SCAN_ROW_DATA_STRUCT_007"):
    """디코드 결과 상당의 트리 픽스처"""
    return {marker: {
        "detector": [
            {"name": "det_a", "intensities": [10, 20, 30]},
            {"name": "det_b", "intensities": [1.5, 2.5, 3.5]},
            "not-a-dict",                       # 이형 원소는 스킵
            {"name": "no_intensities"},         # 조건 미달 스킵
        ],
        "ws_positions": [
            {"x": 0.1, "y": 0.0, "z": 5.0},
            {"x": 0.2, "y": 0.0, "z": 5.5},
            {"x": 0.3, "y": 0.0, "z": 6.0},
        ],
    }}


def test_dispatch_scan_row_basic():
    kind, out = dispatch(scan_tree())
    assert kind == "SCAN_ROW_DATA_STRUCT@v1"
    # 시각화 계약: value = 채널별 배열, xyz = 좌표 배열, 길이 일치
    assert out["value"] == {"det_a": [10, 20, 30], "det_b": [1.5, 2.5, 3.5]}
    assert out["xyz"] == {"x": [0.1, 0.2, 0.3], "y": [0.0, 0.0, 0.0],
                          "z": [5.0, 5.5, 6.0]}
    assert out["warnings"] == []


def test_dispatch_finds_nested_marker_node():
    """마커 노드가 중첩 깊이에 있어도 재귀 워킹으로 찾는다."""
    kind, out = dispatch({"outer": {"wrap": scan_tree()}})
    assert kind == "SCAN_ROW_DATA_STRUCT@v1"
    assert out["value"]["det_a"] == [10, 20, 30]


def test_length_mismatch_warns_but_keeps_channel():
    tree = scan_tree()
    tree["IFEU_SCAN_ROW_DATA_STRUCT_007"]["detector"].append(
        {"name": "short", "intensities": [9]})
    _, out = dispatch(tree)
    assert out["value"]["short"] == [9]           # 채널은 유지 (부분 성공)
    assert any("길이 불일치" in w and "short" in w for w in out["warnings"])


def test_non_list_intensities_dropped_with_warning():
    tree = scan_tree()
    tree["IFEU_SCAN_ROW_DATA_STRUCT_007"]["detector"].append(
        {"name": "scalar", "intensities": 42})
    _, out = dispatch(tree)
    assert "scalar" not in out["value"]
    assert any("scalar" in w for w in out["warnings"])


def test_marker_missing_is_unknown():
    """구조는 같아도 마커 키가 없으면 매칭 없음 — 조용한 빈 결과 금지."""
    tree = scan_tree(marker="SOME_OTHER_NODE")
    with pytest.raises(UnknownVersionError):
        dispatch(tree)


def test_ambiguous_version_raises():
    """detect 가 겹치는 버전 정의는 명시적 오류로 드러난다 (정확히-1개-성립)."""
    from items.dump import extract as ex

    class FakeV2:
        name = "FAKE@v2"
        detect = staticmethod(lambda tree: True)
        extract = staticmethod(lambda tree: {})

    ex.VERSIONS.append(FakeV2)
    try:
        with pytest.raises(AmbiguousVersionError):
            dispatch(scan_tree())
    finally:
        ex.VERSIONS.remove(FakeV2)


# ── .tdf 픽스처 + pipeline ──────────────────────────────────────────────


@pytest.fixture
def tdf_dir(tmp_path: Path) -> Path:
    tdf = tmp_path / "server1.tdf"
    with zipfile.ZipFile(tdf, "w") as zf:
        zf.writestr("scan_001.dd", scan_row_dd())
        zf.writestr("machine_cfg.dd", machine_config_dd())   # 매칭 없음 → 스킵
        zf.writestr("memo.dd", b"just a text memo\n")        # 텍스트 → 스킵
        zf.writestr("readme.txt", b"not dd")                 # .dd 아님 → 무시
    (tmp_path / "broken.tdf").write_bytes(b"NOT A ZIP")      # ZIP 아님 → 격리
    return tmp_path


def test_iter_tdf_filters_dd_members(tdf_dir: Path):
    names = [n for n, _ in iter_tdf(tdf_dir / "server1.tdf")]
    assert names == ["scan_001.dd", "machine_cfg.dd", "memo.dd"]
    only = [n for n, _ in iter_tdf(tdf_dir / "server1.tdf", dd_filter="scan")]
    assert only == ["scan_001.dd"]


def test_iter_tdf_rejects_non_zip(tdf_dir: Path):
    with pytest.raises(ValueError):
        list(iter_tdf(tdf_dir / "broken.tdf"))


def test_run_tdf_records_and_skips(tdf_dir: Path):
    report = run_tdf(tdf_dir / "server1.tdf")
    assert report.tdf == "server1.tdf"
    assert len(report.records) == 1
    rec = report.records[0]
    # 시각화 계약: source / value / xyz
    assert rec.source == "server1.tdf::scan_001.dd"
    assert rec.kind == "SCAN_ROW_DATA_STRUCT@v1"
    assert rec.value == {"det_a": [10.0, 20.0, 30.0], "det_b": [1.5, 2.5, 3.5]}
    assert rec.xyz["x"] == [0.1, 0.2, 0.3]
    assert rec.xyz["z"] == [5.0, 5.5, 6.0]
    assert rec.warnings == []
    # 스캔 아닌 .dd 는 사유와 함께 스킵
    skipped_dds = {s["dd"] for s in report.skipped}
    assert skipped_dds == {"machine_cfg.dd", "memo.dd"}


def test_run_tree_isolates_broken_tdf(tdf_dir: Path):
    reports = {r.tdf: r for r in run_tree(tdf_dir)}
    assert len(reports["server1.tdf"].records) == 1        # 정상 파일은 성공
    assert reports["broken.tdf"].records == []             # 깨진 파일은 격리
    assert "TDF 열기 실패" in reports["broken.tdf"].skipped[0]["reason"]


def test_find_tdf_files(tdf_dir: Path):
    found = find_tdf_files(tdf_dir)
    assert [p.name for p in found] == ["broken.tdf", "server1.tdf"]
    assert find_tdf_files(tdf_dir / "server1.tdf") == [tdf_dir / "server1.tdf"]


# ── API ────────────────────────────────────────────────────────────────


@pytest.fixture
def client(tdf_dir: Path, monkeypatch):
    from fastapi.testclient import TestClient
    from api import app
    monkeypatch.setenv("DUMP_DATA_ROOT", str(tdf_dir))
    return TestClient(app)


def test_api_list_tdfs(client):
    body = client.get("/items/dump/tdfs").json()
    assert body["tdfs"] == ["broken.tdf", "server1.tdf"]


def test_api_records_single_tdf(client):
    resp = client.get("/items/dump/records", params={"tdf": "server1.tdf"})
    assert resp.status_code == 200
    report = resp.json()["reports"][0]
    rec = report["records"][0]
    assert rec["source"] == "server1.tdf::scan_001.dd"
    assert rec["value"]["det_a"] == [10.0, 20.0, 30.0]
    assert rec["xyz"]["z"] == [5.0, 5.5, 6.0]


def test_api_records_whole_root(client):
    body = client.get("/items/dump/records").json()
    assert {r["tdf"] for r in body["reports"]} == {"server1.tdf", "broken.tdf"}


def test_api_rejects_path_traversal(client):
    resp = client.get("/items/dump/records", params={"tdf": "../outside.tdf"})
    assert resp.status_code in (400, 404)


def test_api_upload_parse(client, tdf_dir: Path):
    raw = (tdf_dir / "server1.tdf").read_bytes()
    resp = client.post("/items/dump/parse", content=raw,
                       headers={"Content-Type": "application/octet-stream"})
    assert resp.status_code == 200
    report = resp.json()["reports"][0]
    assert len(report["records"]) == 1
    assert report["records"][0]["kind"] == "SCAN_ROW_DATA_STRUCT@v1"


def test_api_upload_rejects_non_zip(client):
    resp = client.post("/items/dump/parse", content=b"NOT A ZIP")
    assert resp.status_code == 422
