import json

from jsonparser import (
    find_text, get_path, get_all, extract, validate, Validator, load_file,
)

# ============================================================
# 파일 종류: FILT_DATA_STRUCT
#   - detect() : 이 파일 종류가 맞는지 "검증"
#   - parse()  : 맞을 때 "파싱"
#   나중에 파일 종류가 늘면 같은 인터페이스(detect/parse)로 클래스만 추가.
# ============================================================
class FiltDataStruct:
    name = "FILT_DATA_STRUCT"

    _NODE_CHECK = (Validator()
                   .require("$.detector", "type", "list")
                   .require("$.zzef", "type", "list"))
    _DETECTOR_CHECK = Validator().require("$.name").require("$.wow")
    _ZZEF_CHECK = Validator().require("$.x").require("$.y").require("$.z")

    # ---- 검증 -------------------------------------------------
    @classmethod
    def detect(cls, data) -> bool:
        """data 밑 '키 이름'에 FILT_DATA_STRUCT 가 있는 파일인지."""
        return validate(data, [{
            "path": "$.data", "op": "deep_contains",
            "value": {"text": cls.name, "keys": True, "values": False},
        }])

    # ---- 파싱 -------------------------------------------------
    @classmethod
    def parse(cls, data):
        """검증 통과한 원소만 추출. -> {'result':..., 'xyz':...}"""
        result = {}                          # detector: name -> wow
        xyz = {"x": [], "y": [], "z": []}    # zzef: x/y/z

        for m in find_text(get_path(data, "$.data"), cls.name,
                           keys=True, values=False, base="$.data"):
            node = get_path(data, m.path)
            if not cls._NODE_CHECK.is_valid(node):
                continue

            for item in get_all(node, "$.detector[*]"):
                if isinstance(item, dict) and cls._DETECTOR_CHECK.is_valid(item):
                    row = extract(item, {"k": "$.name", "v": "$.wow"})
                    result[row["k"]] = row["v"]

            for s in get_all(node, "$.zzef[*]"):
                if isinstance(s, dict) and cls._ZZEF_CHECK.is_valid(s):
                    row = extract(s, {"x": "$.x", "y": "$.y", "z": "$.z"})
                    xyz["x"].append(row["x"])
                    xyz["y"].append(row["y"])
                    xyz["z"].append(row["z"])

        return {"result": result, "xyz": xyz}


# ============================================================
# 디스패처: 등록된 파일 종류 중 detect 되는 것으로 parse
# ============================================================
PARSERS = [FiltDataStruct]   # 나중에 다른 파일 종류 클래스를 여기에 추가


def parse_file(data, save_to=None):
    """detect 되는 파서로 parse 하고, save_to 가 주어지면 결과를 파일로 저장."""
    for parser in PARSERS:
        if parser.detect(data):
            out = parser.parse(data)
            if save_to is not None:
                with open(save_to, "w", encoding="utf-8") as f:
                    json.dump({"kind": parser.name, **out}, f,
                              ensure_ascii=False, indent=2)
            return parser.name, out
    raise ValueError("알 수 없는 파일 종류")


# ============================================================
# 검증용 실행
# ============================================================
if __name__ == "__main__":
    sample = {
        "data": {
            "FILT_DATA_STRUCT_001": {
                "detector": [
                    {"name": "alpha", "wow": 100, "extra": "ignore"},
                    {"name": "beta",  "wow": "hi"},
                    "not-a-struct",
                    {"noName": 1, "wow": 9},
                    {"name": "gamma"},
                ],
                "zzef": [
                    {"x": 1, "y": 2, "z": 3},
                    {"x": 4, "y": 5, "z": 6},
                    {"x": 7, "y": 8},
                ],
            },
            "OTHER": {
                "detector": [{"name": "nope", "wow": -1}],
                "zzef": [{"x": 9, "y": 9, "z": 9}],
            },
        }
    }

    out_path = "parsed.json"
    kind, out = parse_file(sample, save_to=out_path)
    print("kind   =", kind)
    print("result =", out["result"])
    print("xyz    =", out["xyz"])
    assert kind == "FILT_DATA_STRUCT"
    assert out["result"] == {"alpha": 100, "beta": "hi"}, out["result"]
    assert out["xyz"] == {"x": [1, 4], "y": [2, 5], "z": [3, 6]}, out["xyz"]

    # 저장된 파일을 LLM.md 의 load_file 로 다시 읽어 round-trip 검증
    reloaded = load_file(out_path)
    assert reloaded == {"kind": "FILT_DATA_STRUCT", **out}, reloaded
    print("saved  =", out_path)
    print("OK")
