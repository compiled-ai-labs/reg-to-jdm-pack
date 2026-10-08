"""Pack gates: the checks `verify` runs on a committed pack in the ZEN engine.

Every expression against the ZEN parser, the vocabulary and the numbers of its quote; every
test case in the engine; every cell of the rows under test evaluated, because a cell that
raises makes its row silently not match.
"""

import json
import re
from fractions import Fraction

import zen

from .jdm import ZEN_DATE_METHODS, ZEN_FUNCTIONS
from .numbers_en import numbers_in
from .vocab import Vocabulary
from .zenexpr import ParseError, analyze


def check_vocabulary(vocab: Vocabulary) -> list[str]:
    """The vocabulary may list only what the expression language documents."""
    errors = [f"vocabulary function {f} is not in the ZEN functions reference"
              for f in sorted(vocab.functions - ZEN_FUNCTIONS)]
    errors += [f"vocabulary method {m} is not in the ZEN date reference"
               for m in sorted(vocab.methods - ZEN_DATE_METHODS)]
    return errors


def _word_in(word: str, quote: str) -> bool:
    return re.search(rf"\b{re.escape(word)}s?\b", quote, re.IGNORECASE) is not None


def check_expression(expr: str, quote: str, vocab: Vocabulary, where: str,
                     day_set: bool = False, allow_empty: bool = False) -> list[str]:
    if not isinstance(expr, str):
        return [f"{where}: expression must be a string"]
    if not expr.strip():
        return [] if allow_empty else [f"{where}: empty expression"]
    error = zen.validate_expression(expr)
    if error:
        return [f"{where}: the ZEN parser rejects {expr!r}: {error.get('source')}"]
    try:
        uses = analyze(expr)
    except ParseError as exc:
        return [f"{where}: {exc} in {expr!r}"]
    errors = [f"{where}: {u} is not allowed" for u in sorted(uses.unsupported)]
    for name in sorted(uses.fields):
        if not vocab.known(name):
            errors.append(f"{where}: {name} is not a field or derived field of the vocabulary")
    for name in sorted(uses.functions - vocab.functions):
        errors.append(f"{where}: function {name} is not in the vocabulary")
    for name in sorted(uses.methods - vocab.methods):
        errors.append(f"{where}: method .{name}() is not in the vocabulary")
    if day_set and not uses.uses_hash:
        errors.append(f"{where}: the test of a day must use # for the day")
    stated = numbers_in(quote)
    for value, role in uses.numbers:
        if role == "index":
            if value < 0:
                errors.append(f"{where}: negative list index [{value:g}] is not allowed")
                continue
            need, shown = value + 1, f"index [{value:g}] (element {value + 1:g})"
        elif role == "weekday":
            enc = vocab.encodings.get(float(value))
            if enc and _word_in(enc["word"], quote):
                continue
            errors.append(f"{where}: weekday number {value:g} needs an encoding whose word is "
                          f"in the quote")
            continue
        else:
            need, shown = value, f"number {value:g}"
        if Fraction(str(need)) not in stated:
            errors.append(f"{where}: {shown} is not stated in the quote {quote!r}")
    return errors


def get_path(data: dict, name: str):
    node = data
    for part in name.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def evaluate(decision, inp: dict) -> tuple[dict | None, str | None]:
    try:
        return decision.evaluate(inp)["result"], None
    except RuntimeError as exc:  # the engine reports every error as RuntimeError
        return None, str(exc)


def cell_errors(model: dict, context: dict, rule_ids: set[str]) -> list[tuple[str, str]]:
    """(rule id, message) for each cell of the given rules' rows that raises on this context.

    A cell that raises makes its row never match, silently. The gate makes it loud.
    """
    out = []
    for node in model["nodes"]:
        if node["type"] != "decisionTableNode":
            continue
        for row in node["content"]["rules"]:
            if json.loads(row["o1"]) not in rule_ids:
                continue
            for col in ("i1", "i2"):
                cell = row.get(col, "")
                if not cell.strip():
                    continue
                try:
                    zen.evaluate_expression(cell, context)
                except RuntimeError as exc:
                    out.append((json.loads(row["o1"]),
                                f"row {row['_id']} column {col} raises in the engine: {exc}"))
    return out


def rules_under_test(test: dict, rules_of_subsection: dict[str, set[str]]) -> set[str]:
    """The rules whose rows a test exercises: its rule, or every rule of a fixture's
    subsection. A derived-field test exercises no row."""
    if "subsection" in test:
        return rules_of_subsection.get(test["subsection"], set())
    if "result" in test["expected"]:
        return {test["rule_id"]}
    return set()


def check_test(test: dict, result: dict, table_of_rule: dict[str, str],
               derived_types: dict[str, str]) -> str | None:
    """None when the test holds, else what went wrong."""
    expected = test["expected"]
    if "result" in expected and test.get("rule_id") is None:
        # A fixture that expects its subsection not to apply names no rule.
        got = (result.get("results") or {}).get(test["subsection_key"])
        if got:
            return f"expected no rule of {test['subsection']} to apply, got {got}"
        return None
    if "result" in expected:
        key = table_of_rule.get(test["rule_id"])
        if key is None:
            return f"rule {test['rule_id']} is not in the decision model"
        entries = [e for e in (result.get("results") or {}).get(key) or []
                   if e.get("rule_id") == test["rule_id"]]
        got = [e.get("result") for e in entries]
        want = [] if expected["result"] == "not_applicable" else [expected["result"]]
        if got != want:
            shown = got or ["not_applicable"]
            return f"expected {expected['result']}, the engine gave {', '.join(shown)}"
        return None
    field = test["field"]
    value = get_path(result, field)
    if derived_types.get(field) == "day_set":
        days = value if isinstance(value, list) else []
        missing = [d for d in expected.get("includes", []) if d not in days]
        extra = [d for d in expected.get("excludes", []) if d in days]
        if missing or extra:
            return f"{field}: missing {missing}, should not contain {extra}"
        return None
    if value != expected["value"]:
        return f"{field}: expected {expected['value']!r}, the engine gave {value!r}"
    return None

