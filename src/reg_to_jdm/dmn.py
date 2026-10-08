"""The DMN 1.3 format of the pack, for Camunda 8, and its structure check.

Everything here follows docs/dmn-target.md, taken from the DMN 1.3 specification and XSD
(https://www.omg.org/spec/DMN/1.3, DMN13.xsd) and the Camunda 8.9 DMN and FEEL pages. No
element or attribute is accepted that the target page does not list.
"""

import re
import xml.etree.ElementTree as ET

MODEL = "https://www.omg.org/spec/DMN/20191111/MODEL/"
DMNDI = "https://www.omg.org/spec/DMN/20191111/DMNDI/"
DC = "http://www.omg.org/spec/DMN/20180521/DC/"
DI = "http://www.omg.org/spec/DMN/20180521/DI/"
MODELER = "http://camunda.org/schema/modeler/1.0"
NAMESPACE = "https://github.com/compiled-ai-labs/reg-to-jdm"
PLATFORM_VERSION = "8.9.0"
RESULTS = "results"
PASS, FAIL = "pass", "fail"

# Element -> (attributes, child elements), as docs/dmn-target.md lists them.
_M, _D, _C, _I = (f"{{{MODEL}}}", f"{{{DMNDI}}}", f"{{{DC}}}", f"{{{DI}}}")
_PLATFORM = {f"{{{MODELER}}}executionPlatform", f"{{{MODELER}}}executionPlatformVersion"}
STRUCTURE = {
    _M + "definitions": ({"id", "name", "namespace", *_PLATFORM},
                         {_M + "inputData", _M + "decision", _D + "DMNDI"}),
    _M + "inputData": ({"id", "name", "label"}, set()),
    _M + "decision": ({"id", "name"}, {_M + "informationRequirement",
                                       _M + "literalExpression", _M + "decisionTable"}),
    _M + "informationRequirement": ({"id"}, {_M + "requiredInput", _M + "requiredDecision"}),
    _M + "requiredInput": ({"href"}, set()),
    _M + "requiredDecision": ({"href"}, set()),
    _M + "literalExpression": ({"id"}, {_M + "text"}),
    _M + "decisionTable": ({"id", "hitPolicy"}, {_M + "input", _M + "output", _M + "rule"}),
    _M + "input": ({"id", "label"}, {_M + "inputExpression"}),
    _M + "inputExpression": ({"id", "typeRef"}, {_M + "text"}),
    _M + "output": ({"id", "name", "label", "typeRef"}, set()),
    _M + "rule": ({"id"}, {_M + "description", _M + "inputEntry", _M + "outputEntry"}),
    _M + "description": (set(), set()),
    _M + "inputEntry": ({"id"}, {_M + "text"}),
    _M + "outputEntry": ({"id"}, {_M + "text"}),
    _M + "text": (set(), set()),
    _D + "DMNDI": (set(), {_D + "DMNDiagram"}),
    _D + "DMNDiagram": ({"id"}, {_D + "DMNShape", _D + "DMNEdge"}),
    _D + "DMNShape": ({"id", "dmnElementRef"}, {_C + "Bounds"}),
    _C + "Bounds": ({"x", "y", "width", "height"}, set()),
    _D + "DMNEdge": ({"id", "dmnElementRef"}, {_I + "waypoint"}),
    _I + "waypoint": ({"x", "y"}, set()),
}
_NCNAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")


def slug(text: str) -> str:
    return re.sub(r"_+", "_", re.sub(r"[^A-Za-z0-9]", "_", text)).strip("_")


def rule_xml_id(rule_id: str, verdict: str) -> str:
    """A DMN rule id for a JDM row: DMN ids are xsd:ID (NCName), so no '(', ')', '/'.
    The exact rule id stays in the rule_id output and in the rule's description."""
    return f"rule_{slug(rule_id)}_{verdict}"


def feel_name(path: str) -> str:
    """The FEEL name of a derived field: the id of the decision that computes it. Camunda 8
    stores a required decision's result under the decision id; FEEL names may not contain
    '.', where a vocabulary path is a path into the input."""
    return path.replace(".", "_")


def input_xml_id(field: str) -> str:
    return f"input_{slug(field)}"


def day_set_expression(window: dict, predicate: str) -> str:
    """The days of the window, "YYYY-MM-DD", for which the FEEL test holds, `item` the day.
    The same window as jdm.day_set_expression; code, not text."""
    pad = window["pad_days"]
    start = f'date({window["from"]}) - duration("P{pad}D")'
    end = f'date({window["to"]}) + duration("P{pad}D")'
    days = f'for i in 0..({end} - ({start})).days return string({start} + duration("P1D") * i)'
    return f"({days})[{predicate}]"


def input_entry(feel: str) -> str:
    """The text of an input entry for a boolean FEEL cell. An input entry is FEEL unary tests,
    where a leading `not(...)` is the negation of unary tests ("the input is not ..."), not
    the not() function: with the input `true`, `not(x)` matches when x is null. In
    parentheses it is one expression, which matches only when it is true."""
    text = feel.strip()
    if not text:
        return "-"
    if text.startswith("not(") and _closes_at_end(text, 3):
        return f"({text})"
    return text


def _closes_at_end(text: str, open_at: int) -> bool:
    depth, in_str = 0, False
    for i in range(open_at, len(text)):
        c = text[i]
        if c == '"' and text[i - 1] != "\\":
            in_str = not in_str
        elif not in_str and c == "(":
            depth += 1
        elif not in_str and c == ")":
            depth -= 1
            if depth == 0:
                return i == len(text) - 1
    return False


def _context(entries: dict) -> str:
    return "{" + ", ".join(f"{k}: {_context(v) if isinstance(v, dict) else v}"
                           for k, v in entries.items()) + "}"


def results_expression(table_keys: list[str], derived: list[tuple[str, str]]) -> str:
    """The aggregate decision: {results: {<key>: <table>}, derived: {...}}, the shape of the
    JDM output, so one evaluation gives what the JDM gives."""
    tree: dict = {"results": {k: k for k in table_keys}} if table_keys else {}
    for path, name in derived:
        node = tree
        parts = path.split(".")
        for p in parts[:-1]:
            node = node.setdefault(p, {})
        node[parts[-1]] = name
    return _context(tree)


def check_structure(xml_text: str) -> list[str]:
    """Every element and attribute is one docs/dmn-target.md lists; ids are unique NCNames;
    every reference resolves; every rule has two input and two output entries."""
    try:
        root = ET.fromstring(xml_text.encode("utf-8"))
    except ET.ParseError as exc:
        return [f"not well-formed XML: {exc}"]
    errors: list[str] = []
    if root.tag != _M + "definitions":
        return [f"root is {root.tag}, expected DMN 1.3 definitions"]
    ids: list[str] = []
    refs: list[str] = []

    def walk(el, parent_children: set[str] | None) -> None:
        spec = STRUCTURE.get(el.tag)
        if spec is None or (parent_children is not None and el.tag not in parent_children):
            errors.append(f"element {el.tag} is not in the DMN target")
            return
        attrs, children = spec
        extra = set(el.attrib) - attrs
        if extra:
            errors.append(f"{el.tag} {el.get('id')}: attributes {sorted(extra)} are not in "
                          f"the DMN target")
        if "id" in el.attrib:
            ids.append(el.get("id"))
            if not _NCNAME.match(el.get("id")):
                errors.append(f"id {el.get('id')!r} is not an NCName")
        if "href" in el.attrib:
            refs.append(el.get("href").removeprefix("#"))
        if "dmnElementRef" in el.attrib:
            refs.append(el.get("dmnElementRef"))
        if el.tag == _M + "rule":
            entries = [c.tag for c in el]
            if entries.count(_M + "inputEntry") != 2 or entries.count(_M + "outputEntry") != 2:
                errors.append(f"rule {el.get('id')}: needs two input and two output entries")
        for c in el:
            walk(c, children)

    walk(root, None)
    seen = set()
    for i in ids:
        if i in seen:
            errors.append(f"id {i} is used twice")
        seen.add(i)
    for r in refs:
        if r not in seen:
            errors.append(f"reference {r} names no element")
    return errors


def _text(el) -> str:
    t = el.find(_M + "text")
    return (t.text or "") if t is not None else ""


def decisions_of(xml_text: str) -> dict[str, dict]:
    """decision id -> {name, kind (table|literal), text, rules, requires}."""
    root = ET.fromstring(xml_text.encode("utf-8"))
    out = {}
    for d in root.findall(_M + "decision"):
        requires = [r.get("href").removeprefix("#")
                    for ir in d.findall(_M + "informationRequirement") for r in ir]
        lit = d.find(_M + "literalExpression")
        table = d.find(_M + "decisionTable")
        entry = {"name": d.get("name"), "requires": requires,
                 "kind": "literal" if lit is not None else "table",
                 "text": _text(lit) if lit is not None else None, "rules": []}
        if table is not None:
            for r in table.findall(_M + "rule"):
                ins = [_text(e) for e in r.findall(_M + "inputEntry")]
                outs = [_text(e) for e in r.findall(_M + "outputEntry")]
                desc = r.find(_M + "description")
                entry["rules"].append({
                    "xml_id": r.get("id"), "description": desc.text if desc is not None else "",
                    "applies_when": ins[0], "requirement": ins[1],
                    "rule_id": _unquote(outs[0]), "result": _unquote(outs[1])})
        out[d.get("id")] = entry
    return out


def _unquote(feel_string: str) -> str:
    s = feel_string.strip()
    return s[1:-1].replace('\\"', '"') if s.startswith('"') and s.endswith('"') else s
