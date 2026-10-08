"""readback.md: each row of the decision model in plain English, next to its source sentence.

Rendered by code from rules.jdm.json and receipts.json, with no model call: the readback is a
check on the rules, so it does not come from the model that wrote them.
"""

from .sources import Source
from .vocab import Vocabulary
from .zenexpr import English


def render(model: dict, receipts: dict, sources: list[Source], vocab: Vocabulary) -> str:
    english = English(vocab.labels(), vocab.enums(),
                      {v: e["word"] for v, e in vocab.encodings.items()})
    nodes = {n["id"]: n for n in model["nodes"]}
    by_sentence: dict[str, list[tuple[str, dict]]] = {}
    for rid, r in receipts["rules"].items():
        by_sentence.setdefault(r["sentence_id"], []).append((rid, r))
    links: dict[str, list[dict]] = {}
    for link in receipts["links"]:
        links.setdefault(link["sentence_id"], []).append(link)

    out = ["# Readback", "",
           ("Every row of `rules.jdm.json` in plain English, under the sentence it was compiled "
            "from. Rendered by code from the decision model and the receipts; no model call."),
           ""]
    for src in sources:
        out += [f"## {src.path}", ""]
        for s in src.sentences:
            state = receipts["sentences"][s.id]["state"]
            title = f"{s.id} {s.heading.rstrip('.')}" if s.heading else s.id
            out += [f"### {title}", "", f"> {s.text}", "", f"State: {state}.", ""]
            for rid, r in sorted(by_sentence.get(s.id, [])):
                node = nodes[r["node"]]
                if r["kind"] == "derived_field":
                    spec = vocab.derived[r["field"]]
                    if spec.type == "day_set":
                        what = (f"A day counts as one of the {spec.label} when "
                                f"{english(r['expression'])}.")
                    else:
                        what = f"The {spec.label}: {english(r['expression'])}."
                    out.append(f"- `{rid}` (node `{node['id']}`, field `{r['field']}`): {what}")
                    out.append(f"  Quote: \"{r['quote']}\"")
                    continue
                rows = {row["_id"]: row for row in node["content"]["rules"]}
                for row_id in r["rows"]:
                    row = rows[row_id]
                    result = row["o2"].strip('"')
                    when = row["i1"]
                    lead = "For every loan file" if not when.strip() else \
                        f"When {english(when)}"
                    out.append(f"- Row `{row_id}`: {lead}, and {english(row['i2'])}, "
                               f"the result is **{result}**.")
                out.append(f"  Quote: \"{r['quote']}\"")
            for link in links.get(s.id, []):
                out.append(f"- Link ({link['kind']}) to {link['target']}, cited as "
                           f"\"{link['cited_as']}\".")
            if state == "QUESTION":
                out.append("- Open question: see questions.yaml.")
            out.append("")
    return "\n".join(out).rstrip() + "\n"
