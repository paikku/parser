"""버전 인식 파일 파서 레이어 (파싱 코어 jsonparser.py 위에서 동작).

설계: 각 버전은 자기 detect + normalize 를 통째로 소유한다. 새 버전은 서브클래스 +
레지스트리 한 줄로 추가하며 기존 코드를 수정하지 않는다.

공개 API:
    parse_file(data, save_to=None) -> (kind, out)
    CLASSIFIER                      -> 등록된 프로필로 판별/정규화하는 TypeClassifier
    FiltDataStructV1                -> v1 프로필 (새 버전 작성 시 참고/상속)
"""

from .registry import CLASSIFIER, PROFILES, parse_file
from .filt_data_struct import FiltDataStructV1
from .scan_row_data_struct import ScanRowDataStructV1

__all__ = [
    "parse_file",
    "CLASSIFIER",
    "PROFILES",
    "FiltDataStructV1",
    "ScanRowDataStructV1",
]
