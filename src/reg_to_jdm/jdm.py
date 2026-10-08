"""The JDM format of the pack, and the parts of ZEN a rule may use.

Everything here is taken from the GoRules documentation, recorded in docs/jdm-target.md:
https://docs.gorules.io/developers/jdm/standard and .../developers/jdm/node-types for the
format, https://docs.gorules.io/learn/zen-language/functions and .../dates for the functions.
check_structure() accepts no key those pages do not define.
"""

import json

# Node and edge properties, per node type, as the node types page lists them.
NODE_KEYS = {"id", "type", "name", "position", "content"}
CONTENT_KEYS = {
    "inputNode": {"schema"},
    "outputNode": {"schema"},
    "decisionTableNode": {"hitPolicy", "inputs", "outputs", "rules", "passThrough",
                          "inputField", "outputPath", "executionMode"},
    "expressionNode": {"expressions", "passThrough", "inputField", "outputPath",
                       "executionMode"},
}
EDGE_KEYS = {"id", "sourceId", "targetId", "sourceHandle", "type"}
INPUT_COLUMN_KEYS = {"id", "name", "field"}
OUTPUT_COLUMN_KEYS = {"id", "name", "field", "type"}
EXPRESSION_KEYS = {"id", "key", "value"}

# Built-in functions on https://docs.gorules.io/learn/zen-language/functions.
ZEN_FUNCTIONS = frozenset({
    "abs", "floor", "ceil", "round", "trunc", "min", "max", "sum", "avg", "median", "mode",
    "rand", "len", "upper", "lower", "trim", "contains", "startsWith", "endsWith", "matches",
    "extract", "split", "fuzzyMatch", "map", "filter", "some", "all", "one", "none", "count",
    "flatMap", "keys", "values", "merge", "mergeDeep", "d", "duration", "string", "number",
    "bool", "type", "isNumeric",
})
# Date methods on https://docs.gorules.io/learn/zen-language/dates.
ZEN_DATE_METHODS = frozenset({
    "year", "month", "day", "weekday", "hour", "minute", "second", "dayOfYear", "quarter",
    "timestamp", "set", "add", "sub", "isBefore", "isAfter", "isSame", "isSameOrBefore",
    "isSameOrAfter", "diff", "startOf", "endOf", "tz", "offsetName", "isValid", "isToday",
    "isYesterday", "isTomorrow", "isLeapYear", "format",
})

def day_set_expression(window: dict, predicate: str) -> str:
    """The list of window days, "YYYY-MM-DD", for which the predicate holds.

    The window comes from the vocabulary; only the predicate comes from the source text.
    `[0..n]` iterated by map() works in zen-engine 2.1.2 but the docs show intervals only
    in range checks (NOTES.md).
    """
    start = f'd({window["from"]}).sub({window["pad_days"]}, "d")'
    end = f'd({window["to"]}).add({window["pad_days"]}, "d")'
    days = f'map([0..{end}.diff({start}, "day")], {start}.add(#, "d").format("%Y-%m-%d"))'
    return f"filter({days}, {predicate})"


def check_structure(model: dict) -> list[str]:
    """Every key of the model is one the JDM pages define."""
    errors = []
    if set(model) != {"nodes", "edges"}:
        errors.append(f"top level has {sorted(model)}, expected nodes and edges")
    ids = set()
    for node in model.get("nodes", []):
        where = f"node {node.get('id')}"
        if set(node) - NODE_KEYS:
            errors.append(f"{where}: undocumented keys {sorted(set(node) - NODE_KEYS)}")
        ntype = node.get("type")
        if ntype not in CONTENT_KEYS:
            errors.append(f"{where}: node type {ntype} is not used in this pack format")
            continue
        extra = set(node["content"]) - CONTENT_KEYS[ntype]
        if extra:
            errors.append(f"{where}: undocumented content keys {sorted(extra)}")
        content = node["content"]
        if ntype == "decisionTableNode":
            columns = set()
            for c in content["inputs"]:
                columns.add(c["id"])
                if set(c) - INPUT_COLUMN_KEYS:
                    errors.append(f"{where}: undocumented input column keys")
            for c in content["outputs"]:
                columns.add(c["id"])
                if set(c) - OUTPUT_COLUMN_KEYS:
                    errors.append(f"{where}: undocumented output column keys")
            for row in content["rules"]:
                if set(row) - columns - {"_id"}:
                    errors.append(f"{where}: row {row.get('_id')} has undocumented keys")
            if content["hitPolicy"] not in ("first", "collect"):
                errors.append(f"{where}: hitPolicy {content['hitPolicy']}")
        if ntype == "expressionNode":
            for e in content["expressions"]:
                if set(e) - EXPRESSION_KEYS:
                    errors.append(f"{where}: undocumented expression keys")
        ids.add(node["id"])
    for edge in model.get("edges", []):
        if set(edge) - EDGE_KEYS:
            errors.append(f"edge {edge.get('id')}: undocumented keys")
        if edge.get("sourceId") not in ids or edge.get("targetId") not in ids:
            errors.append(f"edge {edge.get('id')}: unknown node")
    return errors


def rows_of(model: dict) -> list[tuple[dict, dict]]:
    """(table node, row) for every row of every decision table."""
    return [(n, row) for n in model["nodes"] if n["type"] == "decisionTableNode"
            for row in n["content"]["rules"]]


def rule_id_of_row(row: dict) -> str:
    return json.loads(row["o1"])
