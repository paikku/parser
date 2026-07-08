"""JSON 파싱/검증/추출 유틸리티 (표준 JSONPath 기반).

경로 표현식은 표준 **JSONPath** 를 사용합니다. 내부적으로 ``jsonpath-ng``
(확장 파서)를 이용하므로 필터/재귀 하강 등 표준 문법을 그대로 쓸 수 있습니다.

세 가지 기능
-----------
1. 검증(validate) : 원하는 JSON 인지 확인. path 존재 여부, 값 조건 등 여러
   조건을 AND/OR 로 조합해 판정.
2. 조회(get_path/get_all): 특정 path 값을 스칼라/배열/struct 상관없이 조회.
3. 추출(extract): 여러 path 를 하나의 객체(dict)로 재구성.

JSONPath 예시
------------
    $.user.name                     dict 키 접근
    $.items[0].sku                  배열 인덱스
    $.items[-1]                     음수 인덱스(마지막)
    $.items[*].sku                  배열 전체 (여러 값)
    $.items[?(@.qty > 0)]           필터
    $..name                         재귀 하강(모든 깊이의 name)
    $.config.*                      dict 값 전체

의존성: jsonpath-ng>=1.6  (pip install jsonpath-ng)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping

from jsonpath_ng.ext import parse as _parse
from jsonpath_ng.exceptions import JsonPathParserError

# 조회 실패를 명확히 구분하기 위한 센티널 (None 은 정상 값일 수 있으므로).
MISSING = object()

# 컴파일된 JSONPath 캐시 (같은 표현식 반복 파싱 방지).
_CACHE: dict[str, Any] = {}

# "여러 값을 낼 수 있는" 표현식인지 path 문자열만 보고 판정하기 위한 패턴.
# ( [*]  ..  [?  슬라이스[:]  유니온[a,b]  .* )
_MULTI_RE = re.compile(r"\[\s*\*\s*\]|\.\.|\[\s*\?|\[[^\]]*:[^\]]*\]|\[[^\]]*,[^\]]*\]|\.\*")


class JsonPathError(ValueError):
    """잘못된 JSONPath 표현식."""


def _compile(expr: str):
    """JSONPath 표현식을 컴파일(캐시)한다. '$' 접두사는 생략 가능."""
    cached = _CACHE.get(expr)
    if cached is not None:
        return cached
    text = expr if expr.strip().startswith("$") else "$." + expr.lstrip(".")
    try:
        compiled = _parse(text)
    except (JsonPathParserError, Exception) as exc:  # noqa: BLE001
        raise JsonPathError(f"잘못된 JSONPath: {expr!r} ({exc})") from exc
    _CACHE[expr] = compiled
    return compiled


def _is_multi(expr: str) -> bool:
    """path 문자열이 여러 값을 낼 수 있는 형태인지 판정."""
    return bool(_MULTI_RE.search(expr))


# ---------------------------------------------------------------------------
# 기능 2: 조회
# ---------------------------------------------------------------------------

def get_all(data: Any, expr: str) -> list[Any]:
    """expr 에 매칭되는 모든 값을 항상 리스트로 반환한다."""
    return [m.value for m in _compile(expr).find(data)]


def get_path(data: Any, expr: str, default: Any = None) -> Any:
    """단일 path 값을 반환한다 (스칼라/배열/struct 모두).

    - 매칭이 없으면 ``default``.
    - `[*]`, `..`, `[?...]`, 슬라이스, 유니온 등 여러 값을 낼 수 있는
      표현식이면 매칭된 값들의 **리스트**를 반환한다.
    - 그 외(단일 경로)는 매칭된 단일 값을 반환한다.
    """
    matches = _compile(expr).find(data)
    if _is_multi(expr):
        return [m.value for m in matches]
    return matches[0].value if matches else default


def has_path(data: Any, expr: str) -> bool:
    """expr 이 하나라도 매칭되면 True."""
    return bool(_compile(expr).find(data))


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
    path : 검사할 JSONPath
    op   : 연산자 이름 (_OPERATORS 참고). 기본값 "exists".
    value: 기대 값. op 에 따라 의미가 달라짐.
    match : path 가 여러 값을 낼 때 판정 방식.
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
        matches = _compile(self.path).find(data)

        if not _is_multi(self.path):
            actual = matches[0].value if matches else MISSING
            return fn(actual, self.value)

        # 여러 값을 낼 수 있는 표현식: 매칭이 하나도 없을 때
        if not matches:
            # exists=False 만 참, 그 외엔 거짓.
            return self.op == "exists" and not self.value
        checks = [fn(m.value, self.value) for m in matches]
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
            {"path": "$.user.id", "op": "exists"},
            {"path": "$.user.age", "op": "gte", "value": 18},
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
            "id":    "$.user.id",                     # 단순 JSONPath 문자열
            "tags":  {"path": "$.items[*].tag"},      # 옵션 지정 형태
            "first": {"path": "$.items[0].tag", "default": "N/A"},
        }

    옵션(dict 형태)에서 지원하는 키:
        path      : (필수) JSONPath
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
    "JsonPathError",
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
