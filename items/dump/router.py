"""dump 아이템 API 라우터 — pipeline 을 `/items/dump/*` 로 노출.

얇은 HTTP 어댑터: 경로 검증·직렬화만 하고 로직은 전부 pipeline 에 위임한다.

| 메서드·경로 | 동작 |
|---|---|
| GET  /items/dump/tdfs | 데이터 루트에서 발견한 .tdf 목록 |
| GET  /items/dump/records | 전체(또는 ?tdf= 지정) 파싱 → 레코드/스킵 리포트 |
| POST /items/dump/parse | .tdf 바이트 업로드(octet-stream) → 즉석 파싱 리포트 |

응답 레코드는 시각화 입력 계약(`source`/`value`/`xyz`)과 필드 단위로 일치한다.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request

from .pipeline import find_tdf_files, run_tdf, run_tree

# 데이터 루트: .tdf 들이 놓이는 폴더 (예: ftp dump 수신 폴더).
# 환경변수 DUMP_DATA_ROOT 로 지정, 기본값은 실행 위치의 ./data.
DATA_ROOT_ENV = "DUMP_DATA_ROOT"

router = APIRouter(prefix="/items/dump", tags=["dump"])


def _data_root() -> Path:
    return Path(os.environ.get(DATA_ROOT_ENV, "data")).resolve()


def _resolve_tdf(rel: str) -> Path:
    """데이터 루트 밖으로 나가는 경로(../ 등)를 차단하고 실존 확인."""
    root = _data_root()
    candidate = (root / rel).resolve()
    if root not in candidate.parents and candidate != root:
        raise HTTPException(status_code=400, detail=f"데이터 루트 밖 경로: {rel}")
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail=f"TDF 파일 없음: {rel}")
    return candidate


@router.get("/tdfs")
def list_tdfs() -> dict:
    """데이터 루트 아래의 .tdf 목록 (루트 기준 상대경로)."""
    root = _data_root()
    if not root.is_dir():
        raise HTTPException(status_code=404, detail=f"데이터 루트 없음: {root}")
    return {
        "root": str(root),
        "tdfs": [str(p.relative_to(root)) for p in find_tdf_files(root)],
    }


@router.get("/records")
def get_records(
    tdf: str | None = Query(default=None, description="특정 .tdf 상대경로 (생략 시 전체)"),
    dd: str | None = Query(default=None, description=".dd 이름 부분일치 필터"),
) -> dict:
    """데이터 루트의 .tdf 를 파싱해 시각화 레코드 리포트 반환."""
    if tdf is not None:
        report = run_tdf(_resolve_tdf(tdf), dd_filter=dd)
        return {"reports": [report.as_dict()]}
    root = _data_root()
    if not root.is_dir():
        raise HTTPException(status_code=404, detail=f"데이터 루트 없음: {root}")
    return {"reports": [r.as_dict() for r in run_tree(root, dd_filter=dd)]}


@router.post("/parse")
async def parse_uploaded(request: Request,
                         dd: str | None = Query(default=None)) -> dict:
    """업로드된 .tdf 바이트(application/octet-stream)를 즉석 파싱.

    multipart 의존성을 피하려고 요청 본문 = tdf 바이트 그대로 받는다.
    (zipfile 이 파일 경로를 요구하므로 임시파일을 경유한다.)
    """
    raw = await request.body()
    if not raw:
        raise HTTPException(status_code=400, detail="요청 본문이 비어 있음 (.tdf 바이트 필요)")
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".tdf", delete=False) as tmp:
            tmp.write(raw)
            tmp_path = Path(tmp.name)
        try:
            report = run_tdf(tmp_path, dd_filter=dd)
        except ValueError as e:                    # ZIP 아님 등
            raise HTTPException(status_code=422, detail=str(e))
        result = report.as_dict()
        result["tdf"] = "(uploaded)"
        return {"reports": [result]}
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
