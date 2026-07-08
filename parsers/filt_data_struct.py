"""FILT_DATA_STRUCT v1.

설계 원칙: **"버전마다 무엇이 바뀔지"를 미리 못박지 않는다.**
각 버전은 자기 detect(검증)와 normalize(파싱)를 통째로 소유한다. 노드 위치/이름/
배열 키/필드명/구조가 통째로 바뀌어도, 그 버전의 normalize() 안에서 평범한 파이썬으로
처리하면 되므로 고정된 오버라이드 훅이 필요 없다.

새 버전 추가 = 새 파일에 TypeProfile 서브클래스 + registry.PROFILES 에 build() 한 줄.
**기존 버전 코드는 절대 수정하지 않는다.**
"""

from typing import Any

from jsonparser import TypeProfile, Validator, find_text, get_path, get_all, extract


class FiltDataStructV1(TypeProfile):
    """data 밑 마커 노드의 detector 배열 → {name: wow}, zzef 배열 → {x:[],y:[],z:[]}."""

    @classmethod
    def build(cls) -> "FiltDataStructV1":
        # 구조로 판별: detector/zzef 가 (재귀적으로) 존재하면 v1 후보.
        detect = Validator().require("$.data..detector").require("$.data..zzef")
        # fields 는 normalize 를 오버라이드하므로 사용하지 않음({}).
        return cls(name="FILT_DATA_STRUCT@v1", detect=detect, fields={})

    def normalize(self, data: Any) -> dict:
        det = Validator().require("$.name").require("$.wow")
        zz = Validator().require("$.x").require("$.y").require("$.z")
        result: dict = {}
        xyz: dict = {"x": [], "y": [], "z": []}

        # $.data 밑에서 키 이름에 "FILT_DATA_STRUCT" 를 포함하는 노드를 찾는다.
        for m in find_text(get_path(data, "$.data"), "FILT_DATA_STRUCT",
                           keys=True, values=False, base="$.data"):
            node = get_path(data, m.path)

            for item in get_all(node, "$.detector[*]"):
                # G1: 문자열 leaf 를 Validator 에 넘기면 파싱 시도로 예외 → dict 가드 먼저.
                if isinstance(item, dict) and det.is_valid(item):
                    row = extract(item, {"k": "$.name", "v": "$.wow"})
                    result[row["k"]] = row["v"]

            for s in get_all(node, "$.zzef[*]"):
                if isinstance(s, dict) and zz.is_valid(s):
                    row = extract(s, {"x": "$.x", "y": "$.y", "z": "$.z"})
                    xyz["x"].append(row["x"])
                    xyz["y"].append(row["y"])
                    xyz["z"].append(row["z"])

        return {"result": result, "xyz": xyz}
