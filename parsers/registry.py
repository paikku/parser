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

PROFILES = [
    FiltDataStructV1.build(),
    # 새 버전: 새 파일에 서브클래스 만들고 여기에 .build() 한 줄 추가.
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
