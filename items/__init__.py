"""아이템별 입력 어댑터 + 파이프라인 레이어.

한 아이템 = 한 하위 폴더 (`items/<이름>/`). 각 폴더는 그 아이템의
파일 포맷 지식(디코더)과 "원본 파일 → 시각화 레코드" 조립(pipeline),
API 라우터(router)를 통째로 소유한다. 다른 아이템/레이어는 서로 모른다.

의존 방향(단방향):
    items/<이름>/ → parsers → jsonparser
아이템 폴더끼리는 import 하지 않는다. 새 아이템 = 새 폴더 + (필요시)
parsers/ 프로필 + registry 한 줄 + api.py 라우터 마운트 한 줄.

현재 아이템:
    dump — FTP dump 세트의 .tdf(ZIP) 안 .dd 바이너리 → 스캔 레코드
"""
