"""`.dd` 태그 기반 바이너리(TLV) 디코더 — dump 아이템 전용.

decoder 저장소 `dd_main.py` 의 **검증된 파싱 코어만** 이식한 것이다
(실코퍼스 1255개 전수에서 경계 완주·체크섬 일치·구조 유일해 확인,
DD_FORMAT_SPEC.md 참조). CLI·진단(`--diagnose`)·발굴 리포트 등 분석
도구는 이식하지 않는다 — 포맷 연구는 decoder 저장소에서 한다.

포맷 요약 (DD_FORMAT_SPEC.md):
    MAGIC(4B: 17 FA AE 4E) + 최상위 STRUCT(0x0B) 멤버들 + END(0x00)
    + 트레일러 4B(base-17 롤링 해시 체크섬, big-endian).
    필드 = Type(1B) Name(NUL종료) SubType(1B) Value(가변).
    `.tdf` 는 ZIP 아카이브이며 안에 다수의 `.dd` 가 들어있다.

공개 표면:
    decode_dd(raw, name="") -> DecodeResult   # 바이트 → 중첩 dict + 경고
    detect_format(raw) -> 'binary' | 'text'
    iter_tdf(path, dd_filter=None) -> (멤버이름, bytes) 제너레이터

이 모듈은 stdlib 만 쓴다 — jsonparser 도 parsers 도 모른다.
"""

from __future__ import annotations

import re
import struct
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

MAGIC = bytes([0x17, 0xFA, 0xAE, 0x4E])

# ── 타입 태그 (TLV) ──────────────────────────────────────────────────
TAG_END     = 0x00  # 블록 종료 (컨테이너 닫기)
TAG_INT8_A  = 0x01  # 8비트 정수 (1B)
TAG_INT8_B  = 0x02  # 8비트 정수 (1B) — 실측: 0값 표기 전용
TAG_UINT8   = 0x03  # 8비트 부호없는 정수 (1B) — 실측: 0값 표기 전용
TAG_INT8_C  = 0x04  # 8비트 정수 (1B) — 실제 int8 값 캐리어
TAG_ENUM    = 0x05  # 열거형 (2B)
TAG_BOOL    = 0x06  # 고정 4바이트 값 (이름은 유물 — 실측상 32비트 정수)
TAG_FLOAT32 = 0x07  # 32비트 실수 (4B)
TAG_FLOAT64 = 0x08  # 64비트 실수 (8B)
TAG_STRING  = 0x09  # 문자열 (NUL 종료)
TAG_ARRAY   = 0x0A  # 배열 (가변, END 로 닫힘)
TAG_STRUCT  = 0x0B  # 중첩 구조체 (가변, END 로 닫힘)

# 스칼라 타입 → (struct 포맷, 바이트수). big-endian(>) 기준.
SCALAR_FMT = {
    TAG_INT8_A:  ('>b', 1),
    TAG_INT8_B:  ('>b', 1),
    TAG_UINT8:   ('>B', 1),
    TAG_INT8_C:  ('>b', 1),
    TAG_ENUM:    ('>h', 2),
    TAG_FLOAT32: ('>f', 4),
    TAG_FLOAT64: ('>d', 8),
}

# 키 앵커 패턴: 0x09 + '유효한 식별자' + 0x00
#   식별자를 ASCII 영숫자/._- 로 제한 → double 데이터 안의 우연한 0x09 가
#   매칭되지 않으므로 도미노 오정렬이 없다. {0,63} → 단일 글자 키도 허용.
KEY_ANCHOR = re.compile(rb'\x09([A-Za-z_][A-Za-z0-9_.\-]{0,63})\x00')

# 트레일러(체크섬) 크기: 파일 끝 고정 4바이트
TRAILER_LEN = 4


def _read_cstr(raw: bytes, i: int) -> tuple[str, int]:
    """NUL 종료 문자열 읽기 → (문자열, NUL 다음 인덱스)"""
    j = raw.find(0, i)
    if j == -1:
        j = len(raw)
    return raw[i:j].decode('utf-8', errors='replace'), j + 1


class TLVParser:
    """공식 스펙 기반 재귀 TLV 파서 (dd_main.py 이식, 동작 동일).

    필드 = Type(1B) Name(NUL문자열) SubType(1B) Value.
    ARRAY/STRUCT 는 END(0x00) 로 닫힌다. Value 는 SubType 에 따라 재귀.
    """

    def __init__(self, raw: bytes):
        self.raw = raw
        self.i = 0
        self.n = len(raw)
        self.unknown: list[tuple[int, int]] = []    # (tag, offset) 미지 타입
        self.anomalies: list[tuple[int, str, str]] = []  # 디싱크 신호 (진단용)
        # 파일 끝 4바이트 트레일러(체크섬) 제외
        self.end = self.n - TRAILER_LEN if self.n > TRAILER_LEN else self.n
        self.trailer = raw[self.end:] if self.end < self.n else b''
        if raw[:4] == MAGIC:
            self.i = 4

    def parse(self) -> dict:
        """최상위 = STRUCT 로 가정하고 멤버들을 읽는다."""
        if self.i < self.end and self.raw[self.i] == TAG_STRUCT:
            self.i += 1
        return self._read_members()

    def _read_members(self) -> dict:
        """END(0x00) 또는 끝까지 'Name + SubType + Value' 멤버를 읽어 dict 반환."""
        obj: dict = {}
        while self.i < self.end:
            t = self.raw[self.i]
            if t == TAG_END:            # 블록 종료
                self.i += 1
                break
            if t == TAG_STRING:         # 정상 필드: 이름부터
                self.i += 1
                name, self.i = _read_cstr(self.raw, self.i)
                if self.i >= self.end:
                    obj[name] = None
                    break
                subtype = self.raw[self.i]
                self.i += 1
                obj[name] = self._read_value(subtype)
            else:
                # 이름 없이 값이 오는 경우는 배열에서만 정상 → 여기선 미지
                self.unknown.append((t, self.i))
                self.i += 1
        return obj

    def _read_value(self, subtype: int) -> Any:
        raw = self.raw
        fmt = SCALAR_FMT.get(subtype)
        if fmt:
            f, size = fmt
            # 실측: 0값 필드는 payload 가 통째로 생략되고 서브타입 태그 바로
            # 뒤에 다음 필드 이름(0x09+식별자+NUL)이 이어질 수 있다. 이때
            # 고정폭 payload 를 소비하면 다음 필드 이름을 삼켜 디싱크 →
            # 다음 필드 앵커가 보이면 0(생략)으로 보고 소비하지 않는다.
            if KEY_ANCHOR.match(raw, self.i):
                return 0
            # 같은 생략이 컨테이너 '마지막' 멤버에서도 일어난다 — 이때는
            # 형제 앵커가 아니라 END(0x00)가 곧바로 온다. 0 표기 전용 태그
            # (0x01/0x02/0x03)에 한해서만 적용. ⚠ 0x04(int8_c)는 실제 값
            # 캐리어라 포함하면 명시적 '04 00' 을 END 로 오인해 컨테이너를
            # 조기 폐쇄한다 (dd_main.py 2026-07 정정 유지).
            if (subtype in (TAG_INT8_A, TAG_INT8_B, TAG_UINT8)
                    and self.i < self.end and raw[self.i] == TAG_END):
                return 0
            if self.i + size <= self.n:
                v = struct.unpack(f, raw[self.i:self.i + size])[0]
                self.i += size
                return v
            self.i = self.n
            return None
        if subtype == TAG_BOOL:
            # 0x06 은 고정 4바이트 값 (실측: logical_scan_id=129366 등 비영
            # 정수가 온다 — "TRUE"/"FALSE" 는 실제로는 STRING 태그로 기록됨).
            if KEY_ANCHOR.match(raw, self.i):
                return False
            if self.i + 4 <= self.n:
                v = struct.unpack('>i', raw[self.i:self.i + 4])[0]
                self.i += 4
                return v
            self.i = self.n
            return None
        if subtype == TAG_STRING:
            s, self.i = _read_cstr(raw, self.i)
            return s
        if subtype == TAG_STRUCT:
            return self._read_members()
        if subtype == TAG_ARRAY:
            return self._read_array()
        if subtype == TAG_END:
            return None
        # 미지 subtype
        self.unknown.append((subtype, self.i))
        return f'<?0x{subtype:02x}>'

    def _read_array(self) -> list:
        """배열: END(0x00) 까지 'SubType + Value' 원소들을 읽는다.

        스펙 §1.5~1.6 실측 규칙:
          - 0x09 원소는 이형: 이름 NUL 직후가 컨테이너(0a/0b)면 {이름: 컨테이너},
            아니면 bare 문자열 값.
          - 0x02/0x03 은 배열의 payload 없는 0 마커 (진짜 int8 값은 0x04).
          - 그 외 스칼라는 자기 태그 폭으로 값을 싣는다.
          - 실배열은 카테고리(수치/문자열/컨테이너)를 섞지 않는다 → 교차는
            디싱크 신호로 anomalies 에 기록 (파싱 동작엔 영향 없음).
        """
        arr: list = []
        cats: list[tuple[int, str | None]] = []   # (offset, category) 진단용
        while self.i < self.end:
            elem_off = self.i
            t = self.raw[self.i]
            if t == TAG_END:
                self.i += 1
                break
            if t == TAG_STRING:
                self.i += 1
                s, self.i = _read_cstr(self.raw, self.i)
                nxt = self.raw[self.i] if self.i < self.end else None
                if nxt in (TAG_ARRAY, TAG_STRUCT):
                    self.i += 1
                    arr.append({s: self._read_value(nxt)})
                    cats.append((elem_off, 'container'))
                else:
                    arr.append(s)
                    cats.append((elem_off, 'string'))
                continue
            if t in (TAG_INT8_B, TAG_UINT8):
                # payload 없는 0 마커
                self.i += 1
                arr.append(0)
                cats.append((elem_off, 'numeric'))
                continue
            self.i += 1
            if t in SCALAR_FMT:
                f, size = SCALAR_FMT[t]
                if self.i + size <= self.n:
                    arr.append(struct.unpack(f, self.raw[self.i:self.i + size])[0])
                    self.i += size
                else:
                    self.i = self.n
                    arr.append(None)
                cats.append((elem_off, 'numeric'))
                continue
            if t == TAG_BOOL:
                if self.i + 4 <= self.n:
                    arr.append(struct.unpack('>i', self.raw[self.i:self.i + 4])[0])
                    self.i += 4
                else:
                    self.i = self.n
                    arr.append(None)
                cats.append((elem_off, 'numeric'))
                continue
            arr.append(self._read_value(t))
            cats.append((elem_off, 'container' if t in (TAG_ARRAY, TAG_STRUCT) else None))
        # 카테고리 교차 관측 — 첫 교차만 기록
        est = None
        for off, c in cats:
            if c is None:
                continue
            if est is None:
                est = c
            elif c != est:
                self.anomalies.append((off, 'array_category_cross', f'{est}→{c}'))
                break
        return arr


def trailer_checksum(raw: bytes) -> int:
    """트레일러 체크섬: base-17 곱셈 롤링 해시 h = h*17 + byte (mod 2^32).

    범위는 매직 포함 raw[0:n-4], big-endian 4바이트로 저장된다.
    """
    h = 0
    for byte in raw[:-TRAILER_LEN]:
        h = (h * 17 + byte) & 0xFFFFFFFF
    return h


def dd_trailer_ok(raw: bytes) -> bool:
    """.dd 끝 4바이트가 본문 체크섬과 일치하는지 검증"""
    if len(raw) <= TRAILER_LEN:
        return False
    return trailer_checksum(raw) == int.from_bytes(raw[-TRAILER_LEN:], 'big')


def detect_format(raw: bytes) -> str:
    """`.dd` 형식 자동 감지. 반환: 'binary' | 'text'.

    1. 앞 4바이트가 매직 → binary
    2. NUL 바이트가 있고 출력가능문자 비율 < 85% → binary (매직 없는 변형 대비)
    3. 그 외 → text
    """
    if raw[:4] == MAGIC:
        return 'binary'
    if not raw:
        return 'text'
    if 0 in raw:
        printable = sum(1 for b in raw if 0x20 <= b <= 0x7E or b in (9, 10, 13))
        if printable / len(raw) < 0.85:
            return 'binary'
    return 'text'


@dataclass
class DecodeResult:
    """`.dd` 한 개의 디코드 결과. 문제 신호는 fatal 이 아니라 warnings 로 남긴다."""

    name: str
    tree: dict
    size: int
    format: str                      # 'binary' | 'text'
    magic_ok: bool
    trailer_ok: bool | None          # 매직 없으면 None (검증 불가)
    boundary_ok: bool                # 파싱이 경계(n-4)까지 도달했는가
    trailing_bytes: int              # 경계 미도달 시 남은 바이트 수
    unknown_tags: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.warnings


def decode_dd(raw: bytes, name: str = '') -> DecodeResult:
    """단일 `.dd` 바이트를 재귀 TLV 로 디코드해 DecodeResult 반환.

    텍스트 형식(.dd 의 두 형식 중 사람이 읽는 쪽)은 TLV 대상이 아니므로
    빈 tree + 경고로 반환한다 — 파이프라인에서 분류 실패로 자연 스킵된다.
    """
    fmt = detect_format(raw)
    if fmt == 'text':
        return DecodeResult(
            name=name, tree={}, size=len(raw), format=fmt,
            magic_ok=False, trailer_ok=None, boundary_ok=True, trailing_bytes=0,
            warnings=['텍스트 형식 — 바이너리 TLV 디코드 대상 아님'],
        )

    p = TLVParser(raw)
    tree = p.parse()
    magic_ok = raw[:4] == MAGIC
    trailer_ok = dd_trailer_ok(raw) if magic_ok else None
    trailing = max(0, p.end - p.i) if magic_ok else 0

    unknown_tags: dict[str, int] = {}
    for tag, _off in p.unknown:
        key = f'0x{tag:02x}'
        unknown_tags[key] = unknown_tags.get(key, 0) + 1

    warnings: list[str] = []
    if not magic_ok:
        warnings.append('매직 불일치 (17 FA AE 4E 아님)')
    if trailer_ok is False:
        warnings.append('트레일러 체크섬 불일치')
    if trailing:
        warnings.append(f'경계 미도달: {trailing}B 남기고 파싱 중단 (무증상 절단 가능)')
    if unknown_tags:
        warnings.append(f'미지/오정렬 태그: {sorted(unknown_tags)}')
    for off, kind, detail in p.anomalies[:3]:
        warnings.append(f'배열 디싱크 신호 @0x{off:x}: {kind} {detail}')

    return DecodeResult(
        name=name, tree=tree, size=len(raw), format=fmt,
        magic_ok=magic_ok, trailer_ok=trailer_ok,
        boundary_ok=trailing == 0, trailing_bytes=trailing,
        unknown_tags=unknown_tags, warnings=warnings,
    )


def iter_tdf(path: str | Path, dd_filter: str | None = None) -> Iterator[tuple[str, bytes]]:
    """`.tdf`(ZIP) 안의 (필터에 맞는) `.dd` 멤버를 (이름, bytes) 로 순회.

    ZIP 이 아니면 ValueError — 호출자(파이프라인)가 파일 단위로 격리 처리한다.
    """
    path = Path(path)
    if not zipfile.is_zipfile(path):
        raise ValueError(f'ZIP(TDF) 형식이 아님: {path}')
    with zipfile.ZipFile(path, 'r') as zf:
        for member in zf.namelist():
            if not member.endswith('.dd'):
                continue
            if dd_filter and dd_filter not in member:
                continue
            yield member, zf.read(member)
