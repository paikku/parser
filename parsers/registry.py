"""파서 레지스트리 + 디스패처.

등록된 (타입,버전) 프로필 중 가장 구체적인 것을 라이브러리 TypeClassifier 가
자동 선택(등록 순서 무관)한다. 새 버전은 프로필 서브클래스를 만들고 아래
PROFILES 목록에 build() 한 줄만 추가하면 된다.
"""

import json
from typing import Any, Optional

from jsonparser import TypeClassifier

from .filt_data_struct import FiltDataStructProfile, FiltDataStructV2

# 등록된 파일 종류/버전. 새 버전 = 여기에 .build() 한 줄 추가.
PROFILES = [
    FiltDataStructProfile.build(),
    FiltDataStructV2.build(),
]

# 명시적 type_field 마커는 없고 구조로 추론하므로 type_field 미사용.
CLASSIFIER = TypeClassifier(profiles=PROFILES)


def parse_file(data: Any, save_to: Optional[str] = None):
    """data 를 판별 → 검증(require) → 파싱(normalize)하고, save_to 가 주어지면 저장.

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
