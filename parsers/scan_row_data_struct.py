"""SCAN_ROW_DATA_STRUCT v1 — dump 아이템의 스캔 행 데이터.

.dd 디코드 결과(dict)를 `{"data": tree}` 로 감싼 문서에서, 키 이름에
"SCAN_ROW_DATA_STRUCT" 마커를 포함하는 노드의
  - `detector` 배열  → 채널별 값 배열  `value = {검출기이름: intensities[]}`
  - `ws_positions` 배열 → 측정점 좌표   `xyz = {x: [], y: [], z: []}`
를 추출한다. 시각화 계약: `value[k][i]` 가 좌표 `(x[i], z[i])` 의 측정값
(세 배열 길이 일치, y 는 시각화가 무시하지만 정보 보존 차원에서 유지).

설계 원칙: 각 버전은 자기 detect(검증)와 normalize(파싱)를 통째로 소유한다.
새 버전 추가 = 새 파일에 TypeProfile 서브클래스 + registry.PROFILES 에
build() 한 줄. **기존 버전 코드는 절대 수정하지 않는다.**
"""

from typing import Any

from jsonparser import TypeProfile, Validator, find_text, get_path, get_all, extract

_MARKER = "SCAN_ROW_DATA_STRUCT"


class ScanRowDataStructV1(TypeProfile):
    """마커 노드의 detector[].intensities → value 채널, ws_positions → xyz."""

    @classmethod
    def build(cls) -> "ScanRowDataStructV1":
        # 구조 + 마커로 판별. detect 에 마커(deep_contains, 키 이름만)를 넣어
        # normalize 의 find_text 기준과 일치시킨다 — "detect 는 통과하는데
        # 결과가 텅 빈" 함정(parsers/README ⚠) 차단. 조건 3개 > FILT v1 의
        # 2개이므로 겹치는 문서에서도 동점(Ambiguous)이 나지 않는다.
        detect = (Validator()
                  .require("$.data..detector")
                  .require("$.data..ws_positions")
                  .require("$.data", "deep_contains",
                           {"text": _MARKER, "values": False}))
        # fields 는 normalize 를 오버라이드하므로 사용하지 않음({}).
        return cls(name="SCAN_ROW_DATA_STRUCT@v1", detect=detect, fields={})

    def normalize(self, data: Any) -> dict:
        det = Validator().require("$.name").require("$.intensities")
        pos = Validator().require("$.x").require("$.y").require("$.z")
        value: dict = {}
        xyz: dict = {"x": [], "y": [], "z": []}
        warnings: list[str] = []

        # $.data 밑에서 키 이름에 마커를 포함하는 노드를 찾는다.
        for m in find_text(get_path(data, "$.data"), _MARKER,
                           keys=True, values=False, base="$.data"):
            node = get_path(data, m.path)

            for item in get_all(node, "$.detector[*]"):
                # G1: 문자열 leaf 를 Validator 에 넘기면 파싱 시도로 예외 → dict 가드 먼저.
                if isinstance(item, dict) and det.is_valid(item):
                    row = extract(item, {"k": "$.name", "v": "$.intensities"})
                    if not isinstance(row["v"], list):
                        warnings.append(
                            f"채널 제외 [{row['k']}]: intensities 가 배열이 아님")
                        continue
                    if row["k"] in value:
                        warnings.append(
                            f"채널 이름 중복 [{row['k']}]: 마지막 것으로 덮어씀")
                    value[row["k"]] = row["v"]

            for s in get_all(node, "$.ws_positions[*]"):
                if isinstance(s, dict) and pos.is_valid(s):
                    row = extract(s, {"x": "$.x", "y": "$.y", "z": "$.z"})
                    xyz["x"].append(row["x"])
                    xyz["y"].append(row["y"])
                    xyz["z"].append(row["z"])

        # 길이 정합 검사 — 시각화는 len(value[k]) == len(x) == len(z) 를
        # 기대한다(불일치 시 min 으로 clip). 채널은 버리지 않고 경고만 남겨
        # 부분 성공을 유지한다.
        n_pos = len(xyz["x"])
        for k, arr in value.items():
            if len(arr) != n_pos:
                warnings.append(
                    f"길이 불일치 [{k}]: 값 {len(arr)}개 vs 좌표 {n_pos}개")

        return {"value": value, "xyz": xyz, "warnings": warnings}
