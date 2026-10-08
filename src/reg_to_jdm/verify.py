"""verify: the pack gates, from the committed files only. No model call."""

import json
from pathlib import Path

import yaml
import zen

from .config import Config
from .jdm import check_structure, day_set_expression, rows_of, rule_id_of_row
from .readback import render
from .sources import load_sources
from .validator import (
    cell_errors,
    check_expression,
    check_test,
    check_vocabulary,
    evaluate,
    rules_under_test,
)
from .vocab import load_vocabulary


def verify_pack(cfg: Config, pack: Path, final: bool, log=print) -> int:
    errors: list[str] = []
    model = json.loads((pack / "rules.jdm.json").read_text("utf-8"))
    receipts = json.loads((pack / "receipts.json").read_text("utf-8"))
    sources = load_sources(cfg.root, cfg.sources)
    vocab = load_vocabulary(cfg.root, cfg.vocabulary)

    # 1. The model is JDM as documented, and the engine loads it.
    errors += [f"structure: {e}" for e in check_structure(model)]
    try:
        decision = zen.ZenEngine().create_decision(json.dumps(model))
    except RuntimeError as exc:
        log(f"FAIL the ZEN engine does not load rules.jdm.json: {exc}")
        return 1
    errors += [f"vocabulary: {e}" for e in check_vocabulary(vocab)]

    # 2. Receipts: every quote is in its source sentence, character for character, and the
    #    source has not changed since the pack was built.
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

    # 3. Rows and nodes match the receipts; every number against its quote; every field and
    #    function against the vocabulary.
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

    # 4. Tests in the engine; every rule has a passing and a failing case.
    derived_types = {k: v.type for k, v in vocab.derived.items()}
    rules_of_subsection: dict[str, set[str]] = {}
    for rid, r in receipts["rules"].items():
        if r["kind"] == "rule":
            label = sentences[r["sentence_id"]].label if r["sentence_id"] in sentences else ""
            rules_of_subsection.setdefault(label, set()).add(rid)
    covered: dict[str, set] = {rid: set() for rid in receipts["rules"]}
    test_files = sorted((pack / "tests").glob("*.json"))
    for path in test_files:
        test = json.loads(path.read_text("utf-8"))
        result, error = evaluate(decision, test["input"])
        if error:
            errors.append(f"{path.name}: the engine stopped: {error}")
            continue
        problem = check_test(test, result, table_of_rule, derived_types)
        if problem:
            errors.append(f"{path.name}: {problem}")
        for rid, message in cell_errors(model, result,
                                        rules_under_test(test, rules_of_subsection)):
            errors.append(f"{path.name}: {message}")
        rid = test.get("rule_id")
        if rid in covered:
            exp = test["expected"]
            covered[rid].add(exp.get("result") or json.dumps(exp, sort_keys=True))
    for rid, seen in sorted(covered.items()):
        if receipts["rules"][rid]["kind"] == "rule" and not {"pass", "fail"} <= seen:
            errors.append(f"{rid}: needs a passing and a failing test case")
        if receipts["rules"][rid]["kind"] == "derived_field" and len(seen) < 2:
            errors.append(f"{rid}: needs two test cases with different values")

    # 5. Readback is current; changes name only known rules.
    if (pack / "readback.md").read_text("utf-8") != render(model, receipts, sources, vocab):
        errors.append("readback.md is not the rendering of this pack; run reg-to-jdm readback")
    changes = json.loads((pack / "changes.json").read_text("utf-8"))
    for rid in changes.get("added", []) + changes.get("changed", []):
        if rid not in receipts["rules"]:
            errors.append(f"changes.json: {rid} is not in the receipts")

    # 6. Open questions.
    questions = yaml.safe_load((pack / "questions.yaml").read_text("utf-8")) or {}
    open_q = questions.get("questions") or []
    blocked = questions.get("blocked") or []

    for e in errors:
        log(f"FAIL {e}")
    log(f"{len(receipts['rules'])} rules and derived fields, {len(test_files)} test cases, "
        f"{len(open_q)} open question(s), {len(blocked)} blocked")
    if errors:
        return 1
    if final and (open_q or blocked):
        log("FAIL the pack is not final: questions are open")
        return 2
    log("PASS")
    return 0
