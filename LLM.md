# jsonparser — LLM Reference

Machine-readable, complete usage reference for the `jsonparser` module (single file
`jsonparser.py`, stdlib + `jsonpath-ng`). Path expressions are standard **JSONPath**
(via `jsonpath-ng.ext`). Every public symbol, operator, semantic rule, and gotcha is
listed. Examples show exact returns after `# =>`.

## Mental model

- Five capabilities over one JSON value: **get** (`get_path`/`get_all`/`has_path`),
  **validate** (`validate`/`Validator`/`Condition`), **extract** (`extract`),
  **text search** (`find_text`/`struct_contains_text`/`find_nodes_with_all` +
  `deep_contains` operator), **classify** (`TypeClassifier`/`TypeProfile`).
- One shared core, `find_text`, powers all recursive substring search (the
  `deep_contains` validation operator and the search helpers all call it).
- Every public entry point accepts **either** a parsed Python object **or** a JSON
  `str`/`bytes` (parsed once internally). See gotcha G1.
- Inputs are **never mutated** (an upstream `jsonpath-ng` filter-mutation bug is
  root-patched at import). See gotcha G5.

## Import

```python
from jsonparser import (
    # get
    get_path, get_all, has_path, MISSING,
    # validate
    validate, Validator, Condition,
    # extract
    extract,
    # text search
    is_struct, find_text, TextMatch, struct_contains_text, find_nodes_with_all,
    # classify
    TypeClassifier, TypeProfile, ClassifyResult,
    # helpers / errors
    loads, load_file, JsonPathError, UnknownTypeError, AmbiguousTypeError,
)
```

## JSONPath syntax (path `expr`)

`$` prefix optional (`"user.name"` == `"$.user.name"`).

| expr | meaning |
|------|---------|
| `$.a.b` | key access |
| `$.items[0]`, `$.items[-1]` | index / negative index |
| `$.items[*]` | all elements (multi) |
| `$.items[?(@.qty > 0)]` | filter (multi) |
| `$..name` | recursive descent (multi) |
| `$.obj.*` | all dict values (multi) |
| `$."weird.key"` | quote keys containing `.` |

"multi" = expression can yield several values. Detected by the substrings
`[*]`, `..`, `[?`, slice `[a:b]`, union `[a,b]`, `.*`.

---

## GET

### `get_path(data, expr, default=None) -> Any`
- No match → `default`.
- **multi** expr → **list** of all matched values (default is ignored for multi).
- single-path expr → the one matched value.
```python
get_path({"u": {"id": "U1"}}, "$.u.id")            # => "U1"
get_path({"u": {"id": "U1"}}, "$.u")               # => {"id": "U1"}
get_path({"items":[{"sku":"A"}]}, "$.items[*].sku")# => ["A"]
get_path({}, "$.x", default="NA")                  # => "NA"
```

### `get_all(data, expr) -> list`
Always a list (even for single/absent).
```python
get_all({"u": {"id": "U1"}}, "$.u.id")   # => ["U1"]
get_all({}, "$.x")                        # => []
```

### `has_path(data, expr) -> bool`
```python
has_path({"u": {"id": 1}}, "$.u.id")     # => True
```

### `MISSING`
Sentinel object meaning "no match" (distinct from `None`). Used as `default` when you
must tell "absent" from a real `None`: `get_path(d, p, MISSING) is MISSING`.

---

## VALIDATE

### `validate(data, conditions, logic="and") -> bool`
`conditions`: iterable of dicts `{"path", "op"?, "value"?, "match"?}` or `Condition`.
`logic`: `"and"` (all) or `"or"` (any).
```python
validate({"u": {"age": 20}}, [
    {"path": "$.u.age", "op": "gte", "value": 18},
])                                                  # => True
```

### `Condition(path, op="exists", value=True, match="all")`
One check. `match` (`"all"`/`"any"`) decides how a **multi** path is judged.
`.check(data) -> bool`. Unknown `op` → `ValueError`.

### `Validator(conditions=[], logic="and")`
- `.require(path, op="exists", value=True, match="all") -> self` (chainable).
- `.is_valid(data) -> bool`.
- `.explain(data) -> list[dict]` with per-condition `{path, op, value, passed, actual}`.
```python
v = Validator().require("$.u.id").require("$.u.age", "gte", 18)
v.is_valid({"u": {"id": "U1", "age": 20}})          # => True
v.explain({"u": {"id": "U1", "age": 20}})
# => [{"path":"$.u.id","op":"exists","value":True,"passed":True,"actual":"U1"},
#     {"path":"$.u.age","op":"gte","value":18,"passed":True,"actual":20}]
```

### Operators (`op`)

`value` = expected. `actual` = value at `path` (or `MISSING` if absent).

| op | true when | notes |
|----|-----------|-------|
| `exists` | `(actual is not MISSING) == bool(value)` | default op; `value=False` asserts absence |
| `eq` | `actual == value` | |
| `ne` | `actual != value` | |
| `gt`/`gte`/`lt`/`lte` | `actual </<=/>/>= value` | False if `MISSING`; may raise `TypeError` on incomparable types |
| `in` | `actual in value` | `value` is a container |
| `not_in` | `actual not in value` | |
| `contains` | `value in actual` | **top-level** membership: substring for str, key for dict, element for list |
| `deep_contains` | `value` found as **recursive substring** in keys/str-values of `actual` | see TEXT SEARCH; `value` may be options dict |
| `regex` | `re.search(value, actual)` | only if `actual` is `str`, else False |
| `type` | `isinstance(actual, T)` | `value` ∈ `str,int,float,number,bool,list,dict,null` |
| `truthy` | `bool(actual and actual is not MISSING) == bool(value)` | |

**multi path semantics**: with `match="all"` every matched value must pass; `match="any"`
one suffices. If a multi path matches nothing, only `exists` with `value=False` is True.

`contains` vs `deep_contains`:
```python
d = {"data": {"meta": {"wow_score": 9}}}
validate(d, [{"path":"$.data","op":"contains","value":"wow"}])       # => False (not a top-level key)
validate(d, [{"path":"$.data","op":"deep_contains","value":"wow"}])  # => True  (recursive, key name)
```

---

## EXTRACT

### `extract(data, mapping, default=None) -> dict`
`mapping`: `out_key -> expr` **or** `out_key -> {"path", "default"?, "transform"?}`.
```python
extract({"u": {"id":"U1","age":20}, "items":[{"sku":"A"}]}, {
    "id":    "$.u.id",
    "skus":  "$.items[*].sku",
    "cur":   {"path": "$.u.currency", "default": "KRW"},
    "adult": {"path": "$.u.age", "transform": lambda x: x >= 18},
})
# => {"id": "U1", "skus": ["A"], "cur": "KRW", "adult": True}
```

---

## TEXT SEARCH

Recursive substring search over **dict key names** and **string values** at any depth.
Non-string scalars (`int`/`float`/`bool`) are **never** matched (gotcha G3). Case
sensitive by default; `ignore_case=True` uses Unicode `casefold` (gotcha G4).

### `find_text(obj, needle, *, keys=True, values=True, ignore_case=False, base="$") -> list[TextMatch]`
Core primitive. Walks any nested dict/list. `base` prefixes result paths.
```python
find_text({"a": {"b": ["xwowx", {"c": "no"}]}, "wowKey": 1}, "wow")
# => [TextMatch(path='$.a.b[0]', where='value', value='xwowx'),
#     TextMatch(path='$.wowKey', where='key', value='wowKey')]
find_text({"k": "Straße"}, "STRASSE", ignore_case=True)   # => 1 match (casefold)
find_text({"n": 42000}, "42")                             # => []  (int not matched)
```

### `TextMatch(path, where, value)`
`where` ∈ `"key"` (matched a dict key name) | `"value"` (matched a string value).

### `is_struct(data, expr="$.data") -> bool`
True iff value at `expr` is a `dict`.
```python
is_struct({"data": {"x": 1}})     # => True
is_struct({"data": "x"})          # => False
```

### `struct_contains_text(data, needle, expr="$.data", **kwargs) -> (found, matches)`
Guarded: searches **only if `expr` is a dict**, else `(False, [])`.
`**kwargs` = `keys`/`values`/`ignore_case` passed to `find_text`.
```python
doc = {"data": {"title": "wow deal", "meta": {"wow_score": 9}, "tags": ["ok","wowza"]}}
struct_contains_text(doc, "wow")
# => (True, [TextMatch('$.data.title','value','wow deal'),
#            TextMatch('$.data.meta.wow_score','key','wow_score'),
#            TextMatch('$.data.tags[1]','value','wowza')])
struct_contains_text(doc, "WOW", ignore_case=True)   # matches title too
struct_contains_text(doc, "wow", keys=False)         # values only
struct_contains_text({"data": "wow"}, "wow")         # => (False, [])  (not a dict)
```

### `find_nodes_with_all(data, *needles, expr="$", deepest_only=False, ignore_case=False) -> list[(path, node)]`
Nodes whose subtree (self included) contains **all** `needles`. Different needles may
sit at different positions under the same node → their common ancestor is returned.
`deepest_only=True` keeps only minimal nodes (no qualifying descendant). `expr` scopes
the search. ≥1 needle required (else `ValueError`); all needles must be `str`.
```python
doc = {
    "a": {"title": "wow deal", "code": "vmv-1"},          # both (values)
    "b": {"title": "wow only"},                            # wow only -> excluded
    "c": {"items": [{"t": "vmv"}, {"t": "say wow now"}]},  # both in subtree
    "d": "wow and vmv in one string",                      # both in one string
    "e": {"vmvKey": {"note": "wow"}},                      # key + value
}
[p for p,_ in find_nodes_with_all(doc, "wow", "vmv")]
# => ['$.a', '$.c.items', '$.c', '$.d', '$.e', '$']
[p for p,_ in find_nodes_with_all(doc, "wow", "vmv", deepest_only=True)]
# => ['$.a', '$.c.items', '$.d', '$.e']
find_nodes_with_all(doc, "wow", "vmv", ignore_case=True)  # case-insensitive
find_nodes_with_all(doc, "wow", "vmv", expr="$.c")        # scope to subtree
```

### Recipe: does ONE node contain all needles?
```python
node = {"title": "wow", "code": "vmv"}
all(find_text(node, s) for s in ("wow", "vmv"))   # => True
```

### Text search ∘ validation compose freely
`deep_contains` is a normal operator, so it mixes with any conditions / `AND`·`OR` /
`Validator` chaining / `explain` / `TypeProfile.detect`/`require`.
```python
doc = {"data": {"title": "wow"}, "status": "paid", "amount": 42000}
validate(doc, [
    {"path": "$.status", "op": "eq", "value": "paid"},
    {"path": "$.amount", "op": "gte", "value": 10000},
    {"path": "$.data",   "op": "deep_contains", "value": "wow"},
])                                                        # => True
```

`deep_contains` `value` forms:
- `"wow"` — case-sensitive, searches keys+values.
- `{"text": "wow", "ignore_case": True, "keys": bool, "values": bool}` — options.
- Invalid spec (missing `text`, non-str needle, unknown option key) → **`ValueError`**,
  raised **independent of data** (never a silent False). See gotcha G2.

---

## CLASSIFY (types with differing paths → unified schema)

### `TypeProfile(name, detect, fields, require=None)`
- `detect`: `Validator` deciding if data is this type.
- `fields`: `extract`-style mapping (per-type paths → unified logical names).
- `require`: optional `Validator`, mandatory post-detection check.
- `.matches(data)`, `.specificity()` (= number of detect conditions), `.normalize(data)`.

### `TypeClassifier(profiles=[], type_field=None)`
- `.register(profile) -> self`.
- `.resolve(data) -> TypeProfile`: if `type_field`'s value equals a profile `name` →
  that profile; else the **most specific** matching profile (most detect conditions),
  **registration order irrelevant**. No match → `UnknownTypeError`; specificity tie →
  `AmbiguousTypeError`.
- `.classify(data) -> ClassifyResult(type, data)`: resolve → check `require` → normalize.
```python
clf = TypeClassifier(
    profiles=[
        TypeProfile("a", detect=Validator().require("$.user.id"),
                    fields={"user_id": "$.user.id", "name": "$.user.name"}),
        TypeProfile("b", detect=Validator().require("$.data.user.uid"),
                    fields={"user_id": "$.data.user.uid", "name": "$.data.user.fullName"}),
    ],
    type_field="$.kind",
)
clf.classify({"user": {"id": "U1", "name": "Kim"}})
# => ClassifyResult(type="a", data={"user_id": "U1", "name": "Kim"})
clf.classify({"kind": "b", "data": {"user": {"uid": "U2", "fullName": "Lee"}}})
# => ClassifyResult(type="b", data={"user_id": "U2", "name": "Lee"})
```
`ClassifyResult(type, data)` — `data` is always the unified schema regardless of type.

---

## HELPERS / ERRORS
- `loads(text) -> Any` — `json.loads` wrapper.
- `load_file(path, encoding="utf-8") -> Any` — read+parse a file.
- `JsonPathError(ValueError)` — bad JSONPath expression.
- `UnknownTypeError(ValueError)` / `AmbiguousTypeError(ValueError)` — classification.

---

## GOTCHAS (read before generating code)

- **G1 — string inputs are parsed as JSON.** `validate`, `is_valid`, `explain`,
  `get_*`, `extract`, `struct_contains_text`, `find_nodes_with_all`, classifier accept
  JSON `str`/`bytes` and `json.loads` them. So passing a **raw string leaf node** to
  `validate`/`deep_contains` tries to JSON-parse it and may raise. To text-check a bare
  string node, use `find_text(node, needle)` (it does not parse). `find_text` itself
  never parses — pass it a Python object.
- **G2 — `deep_contains` validates its spec eagerly.** Missing `text`, non-string
  needle (incl. omitted `value`, which defaults to `True`), or an unknown option key
  raises `ValueError` regardless of the data. It never silently returns False.
- **G3 — only strings are searched.** `find_text`/`deep_contains` match dict **string
  keys** and **string values** only. `int`/`float`/`bool` leaves are skipped (`42000`
  is not found by `"42"`; `True` not by `"true"`).
- **G4 — `ignore_case` uses `casefold`.** Handles ß/Σ etc.; rare combining-mark cases
  (e.g. Turkish dotted `İ`) may still not match (no NFKD normalization).
- **G5 — inputs are not mutated.** The library root-patches `jsonpath_ng.ext.filter.
  Filter.find` so applying a `[?(...)]` filter to a dict no longer rewrites the input
  in place. `get_path(doc, "$.data..*[?(@ =~ '.*wow.*')]")` leaves `doc` unchanged.
- **G6 — JSONPath `=~` is not substring.** The `jsonpath-ng` regex filter is anchored
  (prefix/`re.match`-like): `[?(@ =~ 'wow')]` misses `"say wow"`. It also can't match
  key names and drops match locations. Prefer `find_text`/`deep_contains` for substring
  search over keys+values with positions.
- **G7 — `get_path` return shape depends on the expr.** multi expr → list; single →
  scalar. `default` only applies to a single-path miss. Use `get_all` for a guaranteed
  list.
- **G8 — `TypeClassifier` resolution.** Most-specific wins (count of `detect`
  conditions), order-independent; ties → `AmbiguousTypeError`, no match →
  `UnknownTypeError`; `type_field` is a shortcut that bypasses structural detection.

## Full public surface
`MISSING`, `JsonPathError`, `get_path`, `get_all`, `has_path`, `Condition`,
`Validator`, `validate`, `extract`, `is_struct`, `TextMatch`, `find_text`,
`struct_contains_text`, `find_nodes_with_all`, `UnknownTypeError`,
`AmbiguousTypeError`, `TypeProfile`, `ClassifyResult`, `TypeClassifier`, `loads`,
`load_file`.
Validation operators: `exists`, `eq`, `ne`, `gt`, `gte`, `lt`, `lte`, `in`, `not_in`,
`contains`, `deep_contains`, `regex`, `type`, `truthy`.
`type` values: `str`, `int`, `float`, `number`, `bool`, `list`, `dict`, `null`.
