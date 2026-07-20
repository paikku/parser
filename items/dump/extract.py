"""dump 추출 — 디코드된 .dd 트리(dict)에서 시각화 데이터를 뽑는 순수 파이썬.

**의도적으로 jsonparser/parsers 를 쓰지 않는다.** .dd 디코드 결과는 구조가
결정적인 dict 라 재귀 JSONPath 검색이 필요 없고, stdlib 만 쓰면 이 폴더를
통째로 다른 프로젝트(예: ftpmodule fleet/processing)로 이식할 수 있다.

버전 계약 (ftpmodule catalog 와 같은 패턴):
    한 버전 = 클래스 하나. `name`(전역 유일) + `detect(tree)->bool`
    + `extract(tree)->{"value","xyz","warnings"}`. 아래 VERSIONS 에 등록.
    판별은 "정확히 1개 성립" — 0개 UnknownVersionError, 2개+ AmbiguousVersionError.
    새 버전 = 새 클래스 + VERSIONS 한 줄. **기존 버전 코드는 수정하지 않는다.**

출력 계약 (시각화 입력과 일치):
    value = {채널이름: [값...]}     # detector 이름별 채널
    xyz   = {"x": [...], "y": [...], "z": [...]}
    warnings = [...]               # 부분 성공 기본 — 문제는 경고로만
    `value[k][i]` 가 좌표 `(x[i], z[i])` 의 측정값 (세 배열 길이 일치).
"""

from __future__ import annotations

from typing import Any, Iterator


class UnknownVersionError(ValueError):
    """어떤 등록 버전의 detect 도 성립하지 않음."""


class AmbiguousVersionError(ValueError):
    """둘 이상의 버전 detect 가 동시에 성립 — 버전 정의가 겹친다는 신호."""


def _iter_marker_nodes(obj: Any, marker: str) -> Iterator[dict]:
    """키 이름에 marker 를 포함하는 dict 노드를 재귀로 순회 (깊이 우선)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str) and marker in k and isinstance(v, dict):
                yield v
            yield from _iter_marker_nodes(v, marker)
    elif isinstance(obj, list):
        for v in obj:
            yield from _iter_marker_nodes(v, marker)


class ScanRowV1:
    """SCAN_ROW_DATA_STRUCT v1 — 마커 노드의 detector/ws_positions 추출.

    detector[]  : {"name": 채널이름, "intensities": [값...]} 의 배열
    ws_positions: {"x","y","z"} struct 의 배열 (측정점 좌표)
    """

    name = "SCAN_ROW_DATA_STRUCT@v1"
    marker = "SCAN_ROW_DATA_STRUCT"

    @classmethod
    def detect(cls, tree: dict) -> bool:
        # 마커 노드가 있고 그 안에 detector·ws_positions 배열이 모두 있어야 성립.
        for node in _iter_marker_nodes(tree, cls.marker):
            if (isinstance(node.get("detector"), list)
                    and isinstance(node.get("ws_positions"), list)):
                return True
        return False

    @classmethod
    def extract(cls, tree: dict) -> dict:
        value: dict[str, list] = {}
        xyz: dict[str, list] = {"x": [], "y": [], "z": []}
        warnings: list[str] = []

        for node in _iter_marker_nodes(tree, cls.marker):
            for item in node.get("detector") or []:
                if not isinstance(item, dict):
                    continue                      # 문자열 등 이형 원소 스킵
                name = item.get("name")
                intensities = item.get("intensities")
                if name is None or intensities is None:
                    continue                      # 조건 미달 스킵
                if not isinstance(intensities, list):
                    warnings.append(f"채널 제외 [{name}]: intensities 가 배열이 아님")
                    continue
                if name in value:
                    warnings.append(f"채널 이름 중복 [{name}]: 마지막 것으로 덮어씀")
                value[name] = intensities

            for s in node.get("ws_positions") or []:
                if isinstance(s, dict) and all(k in s for k in ("x", "y", "z")):
                    xyz["x"].append(s["x"])
                    xyz["y"].append(s["y"])
                    xyz["z"].append(s["z"])

        # 길이 정합 — 시각화는 len(value[k]) == len(x) == len(z) 를 기대한다
        # (불일치 시 min 으로 clip). 채널은 버리지 않고 경고만 (부분 성공).
        n_pos = len(xyz["x"])
        for k, arr in value.items():
            if len(arr) != n_pos:
                warnings.append(f"길이 불일치 [{k}]: 값 {len(arr)}개 vs 좌표 {n_pos}개")

        return {"value": value, "xyz": xyz, "warnings": warnings}


# ── 버전 등록 지점 — 새 버전은 클래스 추가 후 여기 한 줄 ─────────────────
VERSIONS = [
    ScanRowV1,
]


def dispatch(tree: dict) -> tuple[str, dict]:
    """트리의 버전을 판별(정확히 1개 성립)해 (버전이름, 추출결과) 반환."""
    matches = [v for v in VERSIONS if v.detect(tree)]
    if not matches:
        raise UnknownVersionError("등록된 버전과 매칭 없음")
    if len(matches) > 1:
        raise AmbiguousVersionError(
            "버전 판별 모호: " + ", ".join(v.name for v in matches))
    version = matches[0]
    return version.name, version.extract(tree)
