"""readback.md: each row of the decision models in plain English, next to its source sentence.

Rendered by code from rules.jdm.json, rules.dmn and receipts.json, with no model call: the
readback is a check on the rules, so it does not come from the model that wrote them.
The DMN section is rendered from the FEEL cells with the same phrases as the JDM section;
where a rule is the same in both, the line reads the same.
"""

from .dmn import decisions_of, feel_name
from .feelexpr import FeelEnglish
from .sources import Source
from .vocab import Vocabulary
from .zenexpr import English


def _english(vocab: Vocabulary) -> English:
    return English(vocab.labels(), vocab.enums(),
                   {v: e["word"] for v, e in vocab.encodings.items()})


def feel_english(vocab: Vocabulary) -> FeelEnglish:
    return FeelEnglish(_english(vocab), {feel_name(d): d for d in vocab.derived})


def _derived_line(spec, words: str) -> str:
    if spec.type == "day_set":
        return f"A day counts as one of the {spec.label} when {words}."
    return f"The {spec.label}: {words}."


def _row_line(when_words: str | None, req_words: str, result: str) -> str:
    lead = "For every loan file" if when_words is None else f"When {when_words}"
    return f"{lead}, and {req_words}, the result is **{result}**."


def render(model: dict, dmn_xml: str, receipts: dict, sources: list[Source],
           vocab: Vocabulary) -> str:
    english = _english(vocab)
    feel = feel_english(vocab)
    nodes = {n["id"]: n for n in model["nodes"]}
    decisions = decisions_of(dmn_xml)
    by_sentence: dict[str, list[tuple[str, dict]]] = {}
    for rid, r in receipts["rules"].items():
        by_sentence.setdefault(r["sentence_id"], []).append((rid, r))
    links: dict[str, list[dict]] = {}
    for link in receipts["links"]:
        links.setdefault(link["sentence_id"], []).append(link)

    out = ["# Readback", "",
           ("Every row of `rules.jdm.json` in plain English, under the sentence it was compiled "
            "from, then every rule of `rules.dmn` in the same words. Rendered by code from the "
            "decision models and the receipts; no model call."),
           "", "## JDM (`rules.jdm.json`)", ""]
    for src in sources:
        out += [f"### {src.path}", ""]
        for s in src.sentences:
            state = receipts["sentences"][s.id]["state"]
            title = f"{s.id} {s.heading.rstrip('.')}" if s.heading else s.id
            out += [f"#### {title}", "", f"> {s.text}", "", f"State: {state}.", ""]
            for rid, r in sorted(by_sentence.get(s.id, [])):
                node = nodes[r["node"]]
                if r["kind"] == "derived_field":
                    what = _derived_line(vocab.derived[r["field"]], english(r["expression"]))
                    out.append(f"- `{rid}` (node `{node['id']}`, field `{r['field']}`): {what}")
                    out.append(f"  Quote: \"{r['quote']}\"")
                    continue
                rows = {row["_id"]: row for row in node["content"]["rules"]}
                for row_id in r["rows"]:
                    row = rows[row_id]
                    when = row["i1"]
                    line = _row_line(english(when) if when.strip() else None,
                                     english(row["i2"]), row["o2"].strip('"'))
                    out.append(f"- Row `{row_id}`: {line}")
                out.append(f"  Quote: \"{r['quote']}\"")
            for link in links.get(s.id, []):
                out.append(f"- Link ({link['kind']}) to {link['target']}, cited as "
                           f"\"{link['cited_as']}\".")
            if state == "QUESTION":
                out.append("- Open question: see questions.yaml.")
            out.append("")

    out += ["## DMN (`rules.dmn`)", "",
            ("The same rules as decisions of the DMN model. Rule ids are the DMN `id` of each "
             "rule; the rule id of the receipts is its `rule_id` output and its description."),
            ""]
    for src in sources:
        for s in src.sentences:
            entries = sorted(by_sentence.get(s.id, []))
            if not entries:
                continue
            out += [f"### {s.id}", ""]
            for rid, r in entries:
                d = decisions[r["dmn"]["decision"]]
                if r["kind"] == "derived_field":
                    what = _derived_line(vocab.derived[r["field"]], feel(r["dmn"]["expression"]))
                    out.append(f"- `{rid}` (decision `{r['dmn']['decision']}`): {what}")
                    continue
                rows = {row["xml_id"]: row for row in d["rules"]}
                for xml_id in r["dmn"]["rules"]:
                    row = rows[xml_id]
                    when = row["applies_when"]
                    line = _row_line(None if when.strip() in ("", "-") else feel(when),
                                     feel(row["requirement"]), row["result"])
                    out.append(f"- Rule `{xml_id}` (decision `{r['dmn']['decision']}`): {line}")
            out.append("")
    return "\n".join(out).rstrip() + "\n"
