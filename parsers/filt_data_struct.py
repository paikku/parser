"""FILT_DATA_STRUCT 계열 버전 인식 파서.

파싱 코어(`jsonparser.py`)를 소비하는 상위 레이어. 파일 종류/버전마다
- 검증(detect): 버전별 구조 조건을 담은 Validator
- 파싱(parse): 공통 로직은 베이스에, 버전별로 달라지는 부분만 오버라이드(template method)

로 표현한다. 새 버전 = 서브클래스 하나 + 레지스트리에 build() 한 줄.
"""

from typing import Any

from jsonparser import (
    TypeProfile, Validator, find_text, get_path, get_all, extract,
)


class FiltDataStructProfile(TypeProfile):
    """FILT_DATA_STRUCT v1 (버전 공통 베이스).

    버전마다 달라질 수 있는 부분은 클래스 속성으로 노출한다. 서브클래스는
    바뀐 속성(또는 필요하면 normalize 훅)만 오버라이드하면 된다.
    """

    # ---- 버전별로 달라질 수 있는 부분 (기본값 = v1) --------------------
    NAME = "FILT_DATA_STRUCT@v1"
    NODE_MARKER = "FILT_DATA_STRUCT"        # data 밑 노드 키 이름 substring
    DETECTOR_KEY = "$.name"                  # detector 원소 -> 결과 key
    DETECTOR_VAL = "$.wow"                   # detector 원소 -> 결과 value
    _DETECTOR_CHECK = Validator().require("$.name").require("$.wow")
    _ZZEF_CHECK = Validator().require("$.x").require("$.y").require("$.z")

    # ---- 검증(detect): 구조로 버전 추론 -------------------------------
    @classmethod
    def detect_validator(cls) -> Validator:
        # detector/zzef 가 (재귀적으로) 존재하면 v1 후보.
        return Validator().require("$.data..detector").require("$.data..zzef")

    @classmethod
    def build(cls) -> "FiltDataStructProfile":
        # TypeProfile(dataclass) __init__ 재사용. fields 는 normalize 를
        # 오버라이드하므로 사용하지 않음({}).
        return cls(name=cls.NAME, detect=cls.detect_validator(), fields={})

    # ---- 파싱(normalize): 버전 공통 흐름 ------------------------------
    def normalize(self, data: Any) -> dict[str, Any]:
        result: dict[str, Any] = {}                      # detector: name -> wow
        xyz: dict[str, list] = {"x": [], "y": [], "z": []}  # zzef: x/y/z

        # data 밑에서 키 이름에 NODE_MARKER 포함하는 노드
        for m in find_text(get_path(data, "$.data"), self.NODE_MARKER,
                           keys=True, values=False, base="$.data"):
            node = get_path(data, m.path)

            for item in get_all(node, "$.detector[*]"):
                # G1: 문자열 leaf 를 Validator 에 넘기면 JSON 파싱 시도로 예외 →
                # isinstance(dict) 가드를 먼저.
                if isinstance(item, dict) and self._DETECTOR_CHECK.is_valid(item):
                    row = extract(item, {"k": self.DETECTOR_KEY, "v": self.DETECTOR_VAL})
                    result[row["k"]] = row["v"]

            for s in get_all(node, "$.zzef[*]"):
                if isinstance(s, dict) and self._ZZEF_CHECK.is_valid(s):
                    row = extract(s, {"x": "$.x", "y": "$.y", "z": "$.z"})
                    xyz["x"].append(row["x"])
                    xyz["y"].append(row["y"])
                    xyz["z"].append(row["z"])

        return {"result": result, "xyz": xyz}


class FiltDataStructV2(FiltDataStructProfile):
    """FILT_DATA_STRUCT v2 — detector 값 키가 wow -> wowScore 로 바뀐 버전.

    바뀐 부분만 선언하면 나머지(zzef 처리, 노드 탐색 등)는 베이스를 그대로 재사용.
    """

    NAME = "FILT_DATA_STRUCT@v2"
    DETECTOR_VAL = "$.wowScore"
    _DETECTOR_CHECK = Validator().require("$.name").require("$.wowScore")

    @classmethod
    def detect_validator(cls) -> Validator:
        # v1 조건 + 추가 구조 조건(wowScore 존재). 조건 수가 늘어 specificity 가
        # 높아지므로, v1/v2 둘 다 매칭돼도 v2 가 우선 채택된다.
        return (Validator()
                .require("$.data..detector")
                .require("$.data..zzef")
                .require("$.data..detector[*].wowScore"))
