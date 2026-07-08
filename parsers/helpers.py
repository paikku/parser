"""버전 무관 재사용 헬퍼.

이들은 '강제되는 베이스 클래스'가 아니라, 각 버전의 normalize() 가 **필요할 때만
불러 쓰는 순수 함수**다. 어떤 축(노드 위치/이름/배열 키/필드/구조)이 바뀔지 미리
못박지 않으므로, 구조가 달라지는 버전은 그냥 이 헬퍼를 안 쓰고 자기 코드를 쓰면 된다.

각 함수는 Validator 호출 전에 isinstance(dict) 가드를 먼저 한다
(LLM.md G1: 문자열 leaf 를 Validator 에 넘기면 JSON 파싱 시도로 예외).
"""

from typing import Any, Mapping, Optional

from jsonparser import Validator, find_text, get_path, get_all, extract


def marked_nodes(data: Any, marker: str, *, base: str = "$.data"):
    """base 밑에서 KEY 이름에 marker 부분문자열을 포함하는 (path, node) 목록.

    find_text 에 스코프 컨테이너를 obj 로, 같은 경로를 base 로 넘겨 TextMatch.path 가
    절대경로가 되게 한다(그래야 get_path(data, path) 로 다시 꺼낼 수 있음).
    """
    container = get_path(data, base)
    if not isinstance(container, (dict, list)):
        return []
    return [(m.path, get_path(data, m.path))
            for m in find_text(container, marker, keys=True, values=False, base=base)]


def array_to_kv(node: Any, array_path: str, key_path: str, val_path: str,
                *, guard: Optional[Validator] = None) -> dict:
    """array_path 원소(dict) 를 {key_path 값: val_path 값} 매핑으로."""
    out: dict = {}
    for item in get_all(node, array_path):
        if not isinstance(item, dict):          # G1 가드 먼저
            continue
        if guard is not None and not guard.is_valid(item):
            continue
        row = extract(item, {"k": key_path, "v": val_path})
        out[row["k"]] = row["v"]
    return out


def array_to_columns(node: Any, array_path: str, columns: Mapping[str, str],
                     *, guard: Optional[Validator] = None) -> dict:
    """array_path 원소(dict) 를 열 단위 {col: [...]} 로.

    guard 는 반드시 **모든 col 경로**를 require 해야 한다. 안 그러면 한 키가 빠진
    행이 일부 열에만 extract 기본값(None)을 append 해 x/y/z 정렬이 어긋난다.
    """
    cols: dict = {c: [] for c in columns}
    for item in get_all(node, array_path):
        if not isinstance(item, dict):          # G1 가드 먼저
            continue
        if guard is not None and not guard.is_valid(item):
            continue
        row = extract(item, dict(columns))
        for c in columns:
            cols[c].append(row[c])
    return cols


# NOTE(확장 seam): 두 개 이상의 버전이 "marked_nodes 를 돌며 result/xyz 를 누적"하는
# 바깥 루프를 실제로 중복하기 시작하면, 그때 콜백을 받는 순수 함수
# collect_over_nodes(data, marker, base, per_node) 로 승격한다. 지금은 v1 하나뿐이라
# (YAGNI) 만들지 않는다. 가변 상태(Ctx blackboard)로는 절대 만들지 말 것.
