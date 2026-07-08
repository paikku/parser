"""JSON 파싱/검증/추출 유틸리티.

세 가지 기능을 제공합니다.

1. 검증(validate) : 원하는 JSON 인지 확인. 특정 path 존재 여부, 값이 특정
   조건을 만족하는지 등 여러 조건을 AND/OR 로 조합해 판정합니다.
2. 조회(get_path): 특정 path 의 값을 스칼라/배열/struct 상관없이 가져옵니다.
   와일드카드(`[*]`, `.*`) 로 여러 값을 한 번에 뽑을 수 있습니다.
3. 추출(extract): 여러 path 를 하나의 객체(dict)로 재구성해 반환합니다.

외부 의존성 없이 표준 라이브러리만 사용합니다.

Path 문법
---------
    "user.name"          -> dict 키 접근
    "items[0].id"        -> 배열 인덱스 접근
    "items[-1]"          -> 음수 인덱스(마지막)
    "items[*].id"        -> 배열 전체 순회 (리스트 반환)
    "config.*"           -> dict 값 전체 순회 (리스트 반환)
    "a.b\\.c"            -> 키에 포함된 '.' 은 백슬래시로 이스케이프
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Sequence


# ---------------------------------------------------------------------------
# 내부: path 토크나이징
# ---------------------------------------------------------------------------

# 조회 실패를 명확히 구분하기 위한 센티널 (None 은 정상 값일 수 있으므로).
MISSING = object()

_INDEX_RE = re.compile(r"\[(-?\d+|\*)\]")


@dataclass(frozen=True)
class _Key:
    name: str          # dict 키 이름
    wildcard: bool = False


@dataclass(frozen=True)
class _Index:
    value: int | None  # None 이면 와일드카드 '[*]'


def _tokenize(path: str) -> list[_Key | _Index]:
    """path 문자열을 토큰 리스트로 변환한다."""
    tokens: list[_Key | _Index] = []
    # '.' 로 세그먼트 분리하되, '\\.' 는 리터럴 점으로 취급.
    segments = re.split(r"(?<!\\)\.", path)
    for seg in segments:
        seg = seg.replace("\\.", ".")
        if seg == "":
            continue
        # 세그먼트 안의 '[...]' 인덱스들을 분리.
        # 예: "items[0][*]" -> key "items", index 0, index *
        m = _INDEX_RE.search(seg)
        key_part = seg[: m.start()] if m else seg
        if key_part == "*":
            tokens.append(_Key(name="", wildcard=True))
        elif key_part:
            tokens.append(_Key(name=key_part))
        for idx_match in _INDEX_RE.finditer(seg):
            raw = idx_match.group(1)
            tokens.append(_Index(value=None if raw == "*" else int(raw)))
    return tokens


def _resolve(data: Any, tokens: Sequence[_Key | _Index], i: int) -> list[Any]:
    """토큰을 순서대로 적용하며 매칭되는 모든 값을 리스트로 반환한다.

    와일드카드가 없으면 결과 길이는 0(경로 없음) 또는 1 이다.
    """
    if i == len(tokens):
        return [data]

    tok = tokens[i]
    results: list[Any] = []

    if isinstance(tok, _Key):
        if tok.wildcard:
            if isinstance(data, Mapping):
                for v in data.values():
                    results.extend(_resolve(v, tokens, i + 1))
            return results
        if isinstance(data, Mapping) and tok.name in data:
            results.extend(_resolve(data[tok.name], tokens, i + 1))
        return results

    # _Index
    if isinstance(data, Sequence) and not isinstance(data, (str, bytes)):
        if tok.value is None:  # [*]
            for v in data:
                results.extend(_resolve(v, tokens, i + 1))
        else:
            try:
                results.extend(_resolve(data[tok.value], tokens, i + 1))
            except IndexError:
                pass
    return results


# ---------------------------------------------------------------------------
# 기능 2: 조회
# ---------------------------------------------------------------------------

def get_path(data: Any, path: str, default: Any = None) -> Any:
    """단일 path 값을 반환한다 (스칼라/배열/struct 모두).

    와일드카드가 포함되면 매칭된 값들의 리스트를 반환한다.
    경로가 없으면 ``default`` 를 반환한다.
    """
    tokens = _tokenize(path)
    has_wildcard = any(
        (isinstance(t, _Key) and t.wildcard) or (isinstance(t, _Index) and t.value is None)
        for t in tokens
    )
    results = _resolve(data, tokens, 0)
    if has_wildcard:
        return results
    return results[0] if results else default


def has_path(data: Any, path: str) -> bool:
    """path 가 존재하면 True. 와일드카드는 하나라도 매칭되면 True."""
    return bool(_resolve(data, _tokenize(path), 0))


def get_all(data: Any, path: str) -> list[Any]:
    """path 에 매칭되는 모든 값을 항상 리스트로 반환한다."""
    return _resolve(data, _tokenize(path), 0)


# ---------------------------------------------------------------------------
# 기능 1: 검증
# ---------------------------------------------------------------------------

# 조건 연산자 테이블. (실제 값, 기대 값) -> bool
_OPERATORS: dict[str, Callable[[Any, Any], bool]] = {
    "exists": lambda actual, expected: (actual is not MISSING) == bool(expected),
    "eq": lambda actual, expected: actual == expected,
    "ne": lambda actual, expected: actual != expected,
    "gt": lambda actual, expected: actual is not MISSING and actual > expected,
    "gte": lambda actual, expected: actual is not MISSING and actual >= expected,
    "lt": lambda actual, expected: actual is not MISSING and actual < expected,
    "lte": lambda actual, expected: actual is not MISSING and actual <= expected,
    "in": lambda actual, expected: actual in expected,
    "not_in": lambda actual, expected: actual not in expected,
    "contains": lambda actual, expected: (
        actual is not MISSING and hasattr(actual, "__contains__") and expected in actual
    ),
    "regex": lambda actual, expected: (
        isinstance(actual, str) and re.search(expected, actual) is not None
    ),
    "type": lambda actual, expected: isinstance(actual, _TYPE_MAP.get(expected, ())),
    "truthy": lambda actual, expected: bool(actual is not MISSING and actual) == bool(expected),
}

_TYPE_MAP: dict[str, type | tuple[type, ...]] = {
    "str": str,
    "int": int,
    "float": float,
    "number": (int, float),
    "bool": bool,
    "list": list,
    "dict": dict,
    "null": type(None),
}


@dataclass(frozen=True)
class Condition:
    """path 하나에 대한 단일 조건.

    Parameters
    ----------
    path : 검사할 JSON path
    op   : 연산자 이름 (_OPERATORS 참고). 기본값 "exists".
    value: 기대 값. op 에 따라 의미가 달라짐.
    match : 와일드카드로 여러 값이 나올 때 판정 방식.
            "all"(모두 만족) 또는 "any"(하나라도 만족). 기본 "all".
    """

    path: str
    op: str = "exists"
    value: Any = True
    match: str = "all"

    def check(self, data: Any) -> bool:
        if self.op not in _OPERATORS:
            raise ValueError(f"알 수 없는 연산자: {self.op!r}")
        fn = _OPERATORS[self.op]
        tokens = _tokenize(self.path)
        has_wildcard = any(
            (isinstance(t, _Key) and t.wildcard)
            or (isinstance(t, _Index) and t.value is None)
            for t in tokens
        )
        found = _resolve(data, tokens, 0)

        if not has_wildcard:
            actual = found[0] if found else MISSING
            return fn(actual, self.value)

        # 와일드카드: 매칭된 값이 하나도 없을 때
        if not found:
            # exists=False 만 참으로 처리, 그 외엔 거짓.
            return self.op == "exists" and not self.value
        checks = [fn(v, self.value) for v in found]
        return all(checks) if self.match == "all" else any(checks)


@dataclass
class Validator:
    """여러 조건을 조합해 JSON 을 검증한다.

    logic="and" 이면 모든 조건 충족 시 통과, "or" 이면 하나라도 충족 시 통과.
    """

    conditions: list[Condition] = field(default_factory=list)
    logic: str = "and"

    def require(self, path: str, op: str = "exists", value: Any = True,
                match: str = "all") -> "Validator":
        """조건을 추가하고 self 를 반환 (체이닝용)."""
        self.conditions.append(Condition(path, op, value, match))
        return self

    def is_valid(self, data: Any) -> bool:
        if not self.conditions:
            return True
        results = (c.check(data) for c in self.conditions)
        return all(results) if self.logic == "and" else any(results)

    def explain(self, data: Any) -> list[dict[str, Any]]:
        """조건별 통과 여부를 상세히 반환 (디버깅용)."""
        report = []
        for c in self.conditions:
            report.append({
                "path": c.path,
                "op": c.op,
                "value": c.value,
                "passed": c.check(data),
                "actual": get_path(data, c.path, MISSING),
            })
        return report


def validate(data: Any, conditions: Iterable[Mapping[str, Any] | Condition],
             logic: str = "and") -> bool:
    """딕셔너리/Condition 리스트로 즉시 검증한다.

    예::

        validate(data, [
            {"path": "user.id", "op": "exists"},
            {"path": "user.age", "op": "gte", "value": 18},
        ])
    """
    v = Validator(logic=logic)
    for c in conditions:
        if isinstance(c, Condition):
            v.conditions.append(c)
        else:
            v.conditions.append(Condition(**c))
    return v.is_valid(data)


# ---------------------------------------------------------------------------
# 기능 3: 추출(프로젝션)
# ---------------------------------------------------------------------------

def extract(data: Any, mapping: Mapping[str, str | Mapping[str, Any]],
            default: Any = None) -> dict[str, Any]:
    """여러 path 를 하나의 객체(dict)로 모아 반환한다.

    mapping 의 각 항목은 아래 두 형태를 지원한다::

        {
            "id":    "user.id",                       # 단순 path 문자열
            "name":  "user.profile.name",
            "tags":  {"path": "items[*].tag"},        # 옵션 지정 형태
            "first": {"path": "items[0].tag", "default": "N/A"},
        }

    옵션(dict 형태)에서 지원하는 키:
        path      : (필수) JSON path
        default   : 값이 없을 때 대체 값
        transform : callable, 뽑은 값을 후처리
    """
    result: dict[str, Any] = {}
    for out_key, spec in mapping.items():
        if isinstance(spec, str):
            path, item_default, transform = spec, default, None
        else:
            path = spec["path"]
            item_default = spec.get("default", default)
            transform = spec.get("transform")

        value = get_path(data, path, item_default)
        if transform is not None:
            value = transform(value)
        result[out_key] = value
    return result


# ---------------------------------------------------------------------------
# 진입 헬퍼
# ---------------------------------------------------------------------------

def loads(text: str) -> Any:
    """json 문자열을 파싱한다 (json.loads 얇은 래퍼)."""
    return json.loads(text)


def load_file(path: str, encoding: str = "utf-8") -> Any:
    """json 파일을 읽어 파싱한다."""
    with open(path, "r", encoding=encoding) as fp:
        return json.load(fp)


__all__ = [
    "MISSING",
    "get_path",
    "get_all",
    "has_path",
    "Condition",
    "Validator",
    "validate",
    "extract",
    "loads",
    "load_file",
]
