"""파서 레지스트리 + 디스패처.

등록된 프로필 중 detect 가 통과하고 가장 구체적인(조건 수가 가장 많은) 것을
라이브러리 TypeClassifier 가 등록 순서 무관하게 자동 선택한다.

새 버전/종류 = 프로필 서브클래스를 만들고 아래 PROFILES 에 build() 한 줄만 추가.
이 파일은 "디스패치 접착제"라서 버전을 추가할 때 유일하게 손대는 기존 파일이지만,
버전 로직 자체는 담지 않는다.
"""

import json
from typing import Any, Optional

from jsonparser import TypeClassifier

from .filt_data_struct import FiltDataStructV1

# ── 새 버전 추가 예시 (FILT_DATA_STRUCT@v2) ─────────────────────────────────
# v2 는 detector 원소의 값 키가 wow -> wowScore 로 바뀐 버전이라고 하자.
# (1) 새 파일 parsers/filt_data_struct_v2.py 에 아래 클래스를 만든다. v1 은 그대로 둔다.
#
#     from typing import Any
#     from jsonparser import TypeProfile, Validator, find_text, get_path, get_all, extract
#
#     class FiltDataStructV2(TypeProfile):
#         @classmethod
#         def build(cls) -> "FiltDataStructV2":
#             # v1 조건 + v2 전용 신호(wowScore). 조건 3개 > v1 의 2개 → 더 구체적이라
#             # 겹치는 문서에서 v2 가 이긴다. wowScore 없는 v1 문서에선 이 조건이 거짓이라
#             # v1 을 가로채지 않는다.
#             detect = (Validator()
#                       .require("$.data..detector")
#                       .require("$.data..zzef")
#                       .require("$.data..detector[*].wowScore"))
#             return cls(name="FILT_DATA_STRUCT@v2", detect=detect, fields={})
#
#         def normalize(self, data: Any) -> dict:
#             det = Validator().require("$.name").require("$.wowScore")   # v2: wow -> wowScore
#             zz = Validator().require("$.x").require("$.y").require("$.z")
#             result, xyz = {}, {"x": [], "y": [], "z": []}
#             for m in find_text(get_path(data, "$.data"), "FILT_DATA_STRUCT",
#                                keys=True, values=False, base="$.data"):
#                 node = get_path(data, m.path)
#                 for item in get_all(node, "$.detector[*]"):
#                     if isinstance(item, dict) and det.is_valid(item):
#                         row = extract(item, {"k": "$.name", "v": "$.wowScore"})
#                         result[row["k"]] = row["v"]
#                 for s in get_all(node, "$.zzef[*]"):
#                     if isinstance(s, dict) and zz.is_valid(s):
#                         row = extract(s, {"x": "$.x", "y": "$.y", "z": "$.z"})
#                         xyz["x"].append(row["x"])
#                         xyz["y"].append(row["y"])
#                         xyz["z"].append(row["z"])
#             return {"result": result, "xyz": xyz}
#
# (2) 여기서 import 하고 PROFILES 에 한 줄 추가한다:
#
#     from .filt_data_struct_v2 import FiltDataStructV2
#     PROFILES = [FiltDataStructV1.build(), FiltDataStructV2.build()]
# ────────────────────────────────────────────────────────────────────────────

PROFILES = [
    FiltDataStructV1.build(),
    # 새 버전: 위 예시처럼 새 파일에 서브클래스를 만들고 여기에 .build() 한 줄 추가.
]

# 명시적 type_field 마커 없이 구조로 추론하므로 type_field 미사용.
CLASSIFIER = TypeClassifier(profiles=PROFILES)


def parse_file(data: Any, save_to: Optional[str] = None):
    """data 를 판별 → (require 검증) → normalize 하고, save_to 가 주어지면 저장.

    Returns
    -------
    (kind, out) : 선택된 프로필 name 과 통합 파싱 결과 dict.

    Raises
    ------
    UnknownTypeError / AmbiguousTypeError : 매칭 실패/모호.
    """
    res = CLASSIFIER.classify(data)   # ClassifyResult(type, data)
    if save_to is not None:
        with open(save_to, "w", encoding="utf-8") as f:
            json.dump({"kind": res.type, **res.data}, f,
                      ensure_ascii=False, indent=2)
    return res.type, res.data
