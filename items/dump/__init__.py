"""dump 아이템 — .tdf(ZIP) 안의 .dd 바이너리를 시각화 레코드로 만든다.

| 파일 | 역할 |
|------|------|
| `ddformat.py` | .dd TLV 바이너리 디코더 (decoder 저장소 dd_main.py의 검증된 파싱 코어 이식) |
| `extract.py` | 디코드 트리 → 시각화 데이터 추출. 버전 클래스(detect+extract, 정확히-1개-성립) + VERSIONS 등록 지점 |
| `pipeline.py` | .tdf → 디코드 → 버전 판별·추출 → `[{source, kind, value, xyz, warnings}]` |
| `router.py`  | FastAPI 라우터 — 위 파이프라인을 `/items/dump/*` 로 노출 |

.dd/.tdf 포맷 지식은 이 폴더 밖으로 새어나가지 않고, 디코더·추출·파이프라인은
stdlib 만 쓴다 (라우터만 fastapi) — 폴더째 다른 프로젝트로 이식 가능.
"""

from .ddformat import DecodeResult, decode_dd, detect_format, iter_tdf
from .extract import (
    VERSIONS,
    AmbiguousVersionError,
    ScanRowV1,
    UnknownVersionError,
    dispatch,
)
from .pipeline import DumpRecord, find_tdf_files, run_tdf, run_tree

__all__ = [
    "DecodeResult",
    "decode_dd",
    "detect_format",
    "iter_tdf",
    "VERSIONS",
    "ScanRowV1",
    "dispatch",
    "UnknownVersionError",
    "AmbiguousVersionError",
    "DumpRecord",
    "find_tdf_files",
    "run_tdf",
    "run_tree",
]
