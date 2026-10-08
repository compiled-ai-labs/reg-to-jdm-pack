"""verify: the pack gates, from the committed files only. No model call.

`--target jdm` runs the tests in the ZEN engine, `--target dmn` in Camunda's DMN engine
(feel.py), `--target all` in both. The gates on the text, the receipts and the readback run
for every target.
"""

import copy
import json
import re
from collections.abc import Callable
from pathlib import Path

import yaml
import zen

from . import dmn as dmnfiles
from .config import Config
from .feelexpr import WEEKDAYS, check_feel
from .jdm import check_structure, day_set_expression, rows_of, rule_id_of_row
from .numbers_en import numbers_in
from .readback import render
from .sources import load_sources
from .validator import (
    cell_errors,
    check_expression,
    check_test,
    check_vocabulary,
    evaluate,
    get_path,
    rules_under_test,
)
from .vocab import load_vocabulary


def known_names(vocab) -> set[str]:
    """Names a FEEL cell may use: vocabulary fields, and derived fields by decision id."""
    return set(vocab.fields) | {dmnfiles.feel_name(d) for d in vocab.derived}


def stated_weekdays(vocab, quote: str) -> set[str]:
    """Day names whose encoding word is in the quote."""
    return {e["word"] for e in vocab.encodings.values() if e["word"] in WEEKDAYS
            and re.search(r"\b" + re.escape(e["word"]) + r"s?\b", quote, re.IGNORECASE)}


def verify_pack(cfg: Config, pack: Path, final: bool, log=print, target: str = "jdm") -> int:
    errors: list[str] = []
    model = json.loads((pack / "rules.jdm.json").read_text("utf-8"))
    dmn_xml = (pack / "rules.dmn").read_text("utf-8")
    receipts = json.loads((pack / "receipts.json").read_text("utf-8"))
    sources = load_sources(cfg.root, cfg.sources)
    vocab = load_vocabulary(cfg.root, cfg.vocabulary)
    errors += [f"vocabulary: {e}" for e in check_vocabulary(vocab)]

    # Receipts: every quote is in its source sentence, character for character, and the
    # source has not changed since the pack was built.
    sentences = {s.id: s for src in sources for s in src.sentences}
    current = {s.path: s.sha256 for s in sources}
    for path, info in receipts["sources"].items():
        if current.get(path) != info["sha256"]:
            errors.append(f"receipts: {path} changed since the pack was built (hash differs)")
    for rid, r in sorted(receipts["rules"].items()):
        s = sentences.get(r["sentence_id"])
        if s is None:
            errors.append(f"{rid}: sentence {r['sentence_id']} is not in the sources")
            continue
        if r["quote"] not in s.text:
            errors.append(f"{rid}: quote is not in {s.id} character for character")
        if r["source_sha256"] != current.get(r["source"]):
            errors.append(f"{rid}: {r['source']} hash differs from the receipt")

    rules_of_subsection: dict[str, set[str]] = {}
    for rid, r in receipts["rules"].items():
        if r["kind"] == "rule":
            label = sentences[r["sentence_id"]].label if r["sentence_id"] in sentences else ""
            rules_of_subsection.setdefault(label, set()).add(rid)
    test_files = sorted((pack / "tests").glob("*.json"))
    tests = [(p.name, json.loads(p.read_text("utf-8"))) for p in test_files]

    targets = ("jdm", "dmn") if target == "all" else (target,)
    for t in targets:
        check = _jdm if t == "jdm" else _dmn
        try:
            errors += check(model if t == "jdm" else dmn_xml, receipts, vocab, tests,
                            rules_of_subsection)
        except _Stop as stop:
            log(f"FAIL {stop}")
            return 1

    # Readback is current; changes name only known rules.
    if (pack / "readback.md").read_text("utf-8") != render(model, dmn_xml, receipts, sources,
                                                           vocab):
        errors.append("readback.md is not the rendering of this pack; run reg-to-jdm readback")
    changes = json.loads((pack / "changes.json").read_text("utf-8"))
    for rid in changes.get("added", []) + changes.get("changed", []):
        if rid not in receipts["rules"]:
            errors.append(f"changes.json: {rid} is not in the receipts")

    questions = yaml.safe_load((pack / "questions.yaml").read_text("utf-8")) or {}
    open_q = questions.get("questions") or []
    blocked = questions.get("blocked") or []

    for e in errors:
        log(f"FAIL {e}")
    log(f"{len(receipts['rules'])} rules and derived fields, {len(test_files)} test cases "
        f"({' and '.join(t.upper() for t in targets)}), {len(open_q)} open question(s), "
        f"{len(blocked)} blocked")
    if errors:
        return 1
    if final and (open_q or blocked):
        log("FAIL the pack is not final: questions are open")
        return 2
    log("PASS")
    return 0


class _Stop(Exception):
    pass


def _coverage(receipts: dict, covered: dict[str, set], target: str) -> list[str]:
    errors = []
    for rid, seen in sorted(covered.items()):
        if receipts["rules"][rid]["kind"] == "rule" and not {"pass", "fail"} <= seen:
            errors.append(f"{target}: {rid}: needs a passing and a failing test case")
        if receipts["rules"][rid]["kind"] == "derived_field" and len(seen) < 2:
            errors.append(f"{target}: {rid}: needs two test cases with different values")
    return errors


def _run_tests(receipts, vocab, tests, rules_of_subsection, table_of_rule, target: str,
               evaluate_one: Callable, cell_check: Callable) -> list[str]:
    errors = []
    derived_types = {k: v.type for k, v in vocab.derived.items()}
    covered: dict[str, set] = {rid: set() for rid in receipts["rules"]}
    for name, test in tests:
        result, error = evaluate_one(test["input"])
        if error:
            errors.append(f"{target}: {name}: the engine stopped: {error}")
            continue
        problem = check_test(test, result, table_of_rule, derived_types)
        if problem:
            errors.append(f"{target}: {name}: {problem}")
        for _, message in cell_check(test, result, rules_under_test(test, rules_of_subsection)):
            errors.append(f"{target}: {name}: {message}")
        rid = test.get("rule_id")
        if rid in covered:
            exp = test["expected"]
            covered[rid].add(exp.get("result") or json.dumps(exp, sort_keys=True))
    return errors + _coverage(receipts, covered, target)


# --- JDM, in the ZEN engine -----------------------------------------------------------------

def _jdm(model, receipts, vocab, tests, rules_of_subsection) -> list[str]:
    errors = [f"jdm structure: {e}" for e in check_structure(model)]
    try:
        decision = zen.ZenEngine().create_decision(json.dumps(model))
    except RuntimeError as exc:
        raise _Stop(f"the ZEN engine does not load rules.jdm.json: {exc}") from exc

    # Rows and nodes match the receipts; every number against its quote; every field and
    # function against the vocabulary.
    nodes = {n["id"]: n for n in model["nodes"]}
    row_rules = {rule_id_of_row(row) for _, row in rows_of(model)}
    for rid in sorted(row_rules - set(receipts["rules"])):
        errors.append(f"row of {rid}: no receipt")
    table_of_rule = {}
    for rid, r in sorted(receipts["rules"].items()):
        node = nodes.get(r["node"])
        if node is None:
            errors.append(f"{rid}: node {r['node']} is not in the model")
            continue
        if r["kind"] == "rule":
            table_of_rule[rid] = node["content"]["outputPath"].removeprefix("results.")
            rows = {row["_id"]: row for row in node["content"]["rules"]}
            want = {f"{rid}/pass": (r["applies_when"], r["requirement"]),
                    f"{rid}/fail": (r["applies_when"], f"not ({r['requirement']})")}
            for row_id, (when, req) in want.items():
                row = rows.get(row_id)
                if row is None or (row["i1"], row["i2"]) != (when, req):
                    errors.append(f"{row_id}: row does not match its receipt")
            errors += check_expression(r["applies_when"], r["quote"], vocab,
                                       f"{rid} applies_when", allow_empty=True)
            errors += check_expression(r["requirement"], r["quote"], vocab,
                                       f"{rid} requirement")
        else:
            spec = vocab.derived.get(r["field"])
            if spec is None:
                errors.append(f"{rid}: {r['field']} is not a derived field of the vocabulary")
                continue
            value = day_set_expression(spec.window, r["expression"]) \
                if spec.type == "day_set" else r["expression"]
            exprs = node["content"]["expressions"]
            if [(e["key"], e["value"]) for e in exprs] != [(r["field"], value)]:
                errors.append(f"{rid}: node {node['id']} does not match its receipt")
            errors += check_expression(r["expression"], r["quote"], vocab,
                                       f"{rid} expression", day_set=spec.type == "day_set")

    return errors + _run_tests(
        receipts, vocab, tests, rules_of_subsection, table_of_rule, "jdm",
        lambda inp: evaluate(decision, inp),
        lambda test, result, rids: cell_errors(model, result, rids))


# --- DMN, in Camunda's DMN engine -----------------------------------------------------------

def _dmn(dmn_xml, receipts, vocab, tests, rules_of_subsection) -> list[str]:
    from .feel import FeelUnavailable, Runner

    errors = [f"dmn structure: {e}" for e in dmnfiles.check_structure(dmn_xml)]
    try:
        runner = Runner()
    except FeelUnavailable as exc:
        raise _Stop(f"--target dmn needs the FEEL engine: {exc}") from exc
    with runner:
        problem = runner.load(dmn_xml)
        if problem:
            raise _Stop(f"the DMN engine does not load rules.dmn: {problem}")
        errors += _dmn_receipts(dmn_xml, receipts, vocab, runner)
        decisions = dmnfiles.decisions_of(dmn_xml)
        table_of_rule = {rid: r["dmn"]["decision"] for rid, r in receipts["rules"].items()
                         if r["kind"] == "rule"}
        cells = {}
        for d in decisions.values():
            for row in d["rules"]:
                cells.setdefault(row["rule_id"], []).append(row)

        def evaluate_one(inp):
            return runner.eval(dmnfiles.RESULTS, inp)

        def cell_check(test, result, rids):
            """A cell whose evaluation fails is a row that never matches, silently: the engine
            turns the failure into null. The gate makes it loud. The test is the value, not
            the engine's suppressed failures: feel-scala 1.21.1 records failures ("No variable
            found with name 'item'") for a filter whose test is a conjunction, even when the
            filter's value is right (NOTES.md)."""
            context = copy.deepcopy(test["input"])
            for path in vocab.derived:
                context[dmnfiles.feel_name(path)] = get_path(result, path)
            out = []
            for rid in sorted(rids):
                for row in cells.get(rid, []):
                    for col in ("applies_when", "requirement"):
                        cell = row[col]
                        if cell.strip() in ("", "-"):
                            continue
                        value, failures, error = runner.expr(cell, context)
                        if error or not isinstance(value, bool):
                            why = error or "; ".join(dict.fromkeys(failures)) or "no failure"
                            message = (f"rule {row['xml_id']} {col} does not decide "
                                       f"(value {value!r}): {why}")
                            out.append((rid, message))
            return out

        return errors + _run_tests(receipts, vocab, tests, rules_of_subsection, table_of_rule,
                                   "dmn", evaluate_one, cell_check)


def _dmn_receipts(dmn_xml, receipts, vocab, runner) -> list[str]:
    """Decisions and rules match the receipts; every FEEL cell passes the FEEL gate and the
    engine's parser."""
    errors = []
    decisions = dmnfiles.decisions_of(dmn_xml)
    names = known_names(vocab)
    seen_rules = set()

    def gate(expr: str, quote: str, where: str, day_set=False, allow_dash=False):
        out = check_feel(expr, quote, names, stated_weekdays(vocab, quote), where, numbers_in,
                         day_set=day_set, allow_dash=allow_dash)
        if not out and expr.strip() not in ("", "-"):
            problem = runner.parse(expr)
            if problem:
                out.append(f"{where}: the FEEL parser rejects {expr!r}: {problem}")
        return out

    for rid, r in sorted(receipts["rules"].items()):
        info = r.get("dmn")
        if not info:
            errors.append(f"{rid}: no DMN receipt")
            continue
        d = decisions.get(info["decision"])
        if d is None:
            errors.append(f"{rid}: decision {info['decision']} is not in rules.dmn")
            continue
        if r["kind"] == "rule":
            rows = {row["xml_id"]: row for row in d["rules"]}
            when = dmnfiles.input_entry(info["applies_when"])
            want = {info["rules"][0]: (when, dmnfiles.input_entry(info["requirement"]), "pass"),
                    info["rules"][1]: (when, dmnfiles.input_entry(f"not({info['requirement']})"),
                                       "fail")}
            for xml_id, (w, req, verdict) in want.items():
                row = rows.get(xml_id)
                seen_rules.add(xml_id)
                if row is None or (row["applies_when"], row["requirement"], row["rule_id"],
                                   row["result"], row["description"]) != \
                        (w, req, rid, verdict, f"{rid}/{verdict}"):
                    errors.append(f"{xml_id}: DMN rule does not match its receipt")
            errors += gate(when, r["quote"], f"{rid} DMN applies_when", allow_dash=True)
            errors += gate(info["requirement"], r["quote"], f"{rid} DMN requirement")
        else:
            spec = vocab.derived.get(r["field"])
            if spec is None:
                errors.append(f"{rid}: {r['field']} is not a derived field of the vocabulary")
                continue
            day_set = spec.type == "day_set"
            text = dmnfiles.day_set_expression(spec.window, info["expression"]) \
                if day_set else info["expression"]
            if d["kind"] != "literal" or d["text"] != text \
                    or info["decision"] != dmnfiles.feel_name(r["field"]):
                errors.append(f"{rid}: decision {info['decision']} does not match its receipt")
            errors += gate(info["expression"], r["quote"], f"{rid} DMN expression",
                           day_set=day_set)
    for key, d in decisions.items():
        for row in d["rules"]:
            if row["xml_id"] not in seen_rules:
                errors.append(f"DMN rule {row['xml_id']} of {key}: no receipt")
    # The aggregate decision only gathers the others, in the shape of the JDM output.
    tables = [k for k, d in decisions.items() if d["kind"] == "table"]
    derived = [(r["field"], r["dmn"]["decision"]) for _, r in sorted(receipts["rules"].items())
               if r["kind"] == "derived_field" and r.get("dmn")]
    derived.sort(key=lambda fd: list(decisions).index(fd[1]) if fd[1] in decisions else 0)
    agg = decisions.get(dmnfiles.RESULTS)
    if agg is None or agg["text"] != dmnfiles.results_expression(tables, derived):
        errors.append(f"decision {dmnfiles.RESULTS} is not the aggregate of the other decisions")
    return errors
