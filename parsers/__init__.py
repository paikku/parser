"""버전 인식 파일 파서 레이어 (파싱 코어 jsonparser.py 위에서 동작).

공개 API:
    parse_file(data, save_to=None) -> (kind, out)
    CLASSIFIER                      -> 등록된 프로필로 판별/정규화하는 TypeClassifier
    프로필 클래스들 (새 버전/종류 추가 시 상속)
"""

from .registry import CLASSIFIER, PROFILES, parse_file
from .filt_data_struct import FiltDataStructProfile, FiltDataStructV2

__all__ = [
    "parse_file",
    "CLASSIFIER",
    "PROFILES",
    "FiltDataStructProfile",
    "FiltDataStructV2",
]
