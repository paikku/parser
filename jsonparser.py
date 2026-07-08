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


def _ensure_obj(data: Any) -> Any:
    """입력이 JSON 문자열/바이트면 파싱해 파이썬 객체로 만든다.

    이미 파싱된 객체(dict/list 등)면 그대로 반환하므로 여러 번 호출해도 안전하다.
    이 덕분에 모든 공개 함수가 파싱된 객체와 원본 JSON 텍스트를 모두 받는다.
    """
    if isinstance(data, (str, bytes, bytearray)):
        return json.loads(data)
    return data


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
    return [m.value for m in _compile(expr).find(_ensure_obj(data))]


def get_path(data: Any, expr: str, default: Any = None) -> Any:
    """단일 path 값을 반환한다 (스칼라/배열/struct 모두).

    - 매칭이 없으면 ``default``.
    - `[*]`, `..`, `[?...]`, 슬라이스, 유니온 등 여러 값을 낼 수 있는
      표현식이면 매칭된 값들의 **리스트**를 반환한다.
    - 그 외(단일 경로)는 매칭된 단일 값을 반환한다.
    """
    matches = _compile(expr).find(_ensure_obj(data))
    if _is_multi(expr):
        return [m.value for m in matches]
    return matches[0].value if matches else default


def has_path(data: Any, expr: str) -> bool:
    """expr 이 하나라도 매칭되면 True."""
    return bool(_compile(expr).find(_ensure_obj(data)))


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
        matches = _compile(self.path).find(_ensure_obj(data))

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
        data = _ensure_obj(data)  # 문자열이면 한 번만 파싱 (조건별 재파싱 방지)
        results = (c.check(data) for c in self.conditions)
        return all(results) if self.logic == "and" else any(results)

    def explain(self, data: Any) -> list[dict[str, Any]]:
        """조건별 통과 여부를 상세히 반환 (디버깅용)."""
        data = _ensure_obj(data)
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
    data = _ensure_obj(data)  # 문자열이면 한 번만 파싱 (필드별 재파싱 방지)
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
# 타입 분류(type classification)
# ---------------------------------------------------------------------------

class UnknownTypeError(ValueError):
    """어느 타입 프로필에도 매칭되지 않는 JSON."""


class AmbiguousTypeError(ValueError):
    """동일하게 구체적인 타입이 둘 이상 매칭되어 하나로 결정할 수 없음."""


@dataclass
class TypeProfile:
    """하나의 JSON 타입을 기술한다.

    Parameters
    ----------
    name    : 타입 이름 (예: "A"). type_field 지름길과 매칭될 값.
    detect  : 이 JSON 이 이 타입인지 판정하는 Validator (path 존재/값/키 조합).
    fields  : 논리 필드명 -> JSONPath/옵션 매핑 (extract() 매핑과 동일 형식).
              타입마다 이 매핑을 달리 주면, 서로 다른 구조가 동일 스키마로 정규화된다.
    require : (선택) 이 타입이 반드시 만족해야 할 조건. classify 시 검증.
    """

    name: str
    detect: "Validator"
    fields: Mapping[str, str | Mapping[str, Any]]
    require: "Validator | None" = None

    def matches(self, data: Any) -> bool:
        """이 JSON 이 이 타입으로 판정되는가."""
        return self.detect.is_valid(data)

    def specificity(self) -> int:
        """구체성 점수. detect 조건 개수 = 많이 맞을수록 더 구체적인 타입.

        예: A(=$.a 만) < B(=$.a + $.a.a). B 는 A 를 포함하므로 더 구체적.
        """
        return len(self.detect.conditions)

    def normalize(self, data: Any) -> dict[str, Any]:
        """타입별 경로로 값을 뽑아 통합 스키마 dict 로 반환."""
        return extract(data, self.fields)


@dataclass
class ClassifyResult:
    """타입 분류 결과."""

    type: str
    data: dict[str, Any]  # 타입과 무관하게 동일한 통합 스키마


@dataclass
class TypeClassifier:
    """여러 TypeProfile 로 JSON 의 타입을 판별하고 통합 스키마로 정규화한다.

    Parameters
    ----------
    profiles   : TypeProfile 목록. **등록 순서와 무관**하게 판별됨
                 (가장 구체적인 타입 우선). 새 타입은 아무 위치에 추가해도 된다.
    type_field : (선택) 명시적 타입 필드 JSONPath. 그 값이 어떤 프로필 name 과
                 같으면 구조 판별을 건너뛰고 즉시 채택하는 지름길.
    """

    profiles: list[TypeProfile] = field(default_factory=list)
    type_field: str | None = None

    def register(self, profile: TypeProfile) -> "TypeClassifier":
        """프로필을 추가하고 self 를 반환 (체이닝용)."""
        self.profiles.append(profile)
        return self

    def resolve(self, data: Any) -> TypeProfile:
        """JSON 을 분석해 해당 TypeProfile 을 반환한다.

        1) type_field 가 있고 그 값이 어떤 프로필 name 과 일치하면 즉시 채택.
        2) 아니면 detect 가 통과하는 프로필 중 **가장 구체적인(조건이 가장 많이
           맞는) 것** 을 채택. 등록 순서는 영향을 주지 않는다.
        매칭이 없으면 UnknownTypeError, 가장 구체적인 타입이 동점이면
        AmbiguousTypeError.

        입력은 파싱된 객체 또는 JSON 문자열/바이트 모두 허용한다.
        """
        data = _ensure_obj(data)
        if self.type_field is not None:
            marker = get_path(data, self.type_field, MISSING)
            if marker is not MISSING:
                for p in self.profiles:
                    if p.name == marker:
                        return p

        matches = [p for p in self.profiles if p.matches(data)]
        if not matches:
            raise UnknownTypeError(
                f"어느 타입에도 매칭되지 않음 (후보: {[p.name for p in self.profiles]})"
            )
        best = max(p.specificity() for p in matches)
        top = [p for p in matches if p.specificity() == best]
        if len(top) > 1:
            raise AmbiguousTypeError(
                f"동일하게 구체적인 타입이 여럿 매칭됨 "
                f"(조건 {best}개): {[p.name for p in top]}"
            )
        return top[0]

    def classify(self, data: Any) -> ClassifyResult:
        """판별 → (필수조건 검증) → 정규화 후 ClassifyResult 반환.

        입력은 파싱된 객체 또는 JSON 문자열/바이트 모두 허용한다.
        """
        data = _ensure_obj(data)
        profile = self.resolve(data)
        if profile.require is not None and not profile.require.is_valid(data):
            raise ValueError(
                f"타입 {profile.name!r} 필수조건 불충족: "
                f"{profile.require.explain(data)}"
            )
        return ClassifyResult(type=profile.name, data=profile.normalize(data))


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
    "UnknownTypeError",
    "AmbiguousTypeError",
    "TypeProfile",
    "ClassifyResult",
    "TypeClassifier",
    "loads",
    "load_file",
]
