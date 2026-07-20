"""API 앱 조립 — 아이템별 라우터를 마운트만 한다.

새 아이템 추가 시 이 파일에 라우터 마운트 한 줄만 늘어난다.
로직은 각 items/<이름>/pipeline.py, HTTP 표면은 items/<이름>/router.py 소유.

실행:
    uvicorn api:app --reload
    DUMP_DATA_ROOT=/path/to/tdf폴더 uvicorn api:app   # dump 데이터 루트 지정
"""

from fastapi import FastAPI

from items.dump.router import router as dump_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="parser items API",
        description="아이템별 원본 파일 → 시각화 레코드 파싱 API",
    )
    app.include_router(dump_router)
    # 새 아이템: app.include_router(<item>_router) 한 줄 추가.
    return app


app = create_app()
