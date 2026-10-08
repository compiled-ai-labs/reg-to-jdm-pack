# JDM target

The exact shape of `rules.jdm.json` in this pack. Every key below is taken from the GoRules documentation pages listed under sources, and the pack uses nothing else. `jdm.check_structure()` enforces this list on every `verify`.

Pages read on 2026-10-07:

- JDM standard: https://docs.gorules.io/developers/jdm/standard
- Node types: https://docs.gorules.io/developers/jdm/node-types
- Expression language: https://docs.gorules.io/learn/zen-language/syntax, .../operators, .../functions, .../dates
- Python SDK: https://docs.gorules.io/developers/sdks/python

Engine: `zen-engine` 2.1.2 from PyPI (abi3 wheels for Linux, macOS, Windows). `tests/test_zen_smoke.py` loads and evaluates the decision table sample of the node types page.

## File

```json
{ "nodes": [ ... ], "edges": [ ... ] }
```

The standard page: "Only `nodes` and `edges` are part of the format." The engine ignores other top-level fields, but the pack has none.

## Nodes

Common properties (node types page): `id`, `type`, `name`, `position` `{x, y}`, `content`.

The graph is a chain, in this order:

| Node | `type` | `id` | One per |
| - | - | - | - |
| Input | `inputNode` | `input` | model |
| Derived field | `expressionNode` | `derive-<n>` | derived field, in dependency order |
| Rules of a subsection | `decisionTableNode` | `table-<key>` | source paragraph with at least one rule |
| Output | `outputNode` | `output` | model |

`<key>` is the paragraph label as a JSON key: `1026.19(f)(1)(ii)(A)` becomes `s1026_19_f_1_ii_A`.

### inputNode, outputNode

```json
{"id": "input", "type": "inputNode", "name": "Loan file", "position": {"x": 0, "y": 0},
 "content": {"schema": ""}}
```

`schema` is documented as an optional JSON Schema string; it is left empty.

### expressionNode

```json
{"id": "derive-2", "type": "expressionNode", "name": "1026.19(f)(1)(iii) date the consumer received ...",
 "position": {"x": 560, "y": 0},
 "content": {
   "expressions": [{"id": "e1", "key": "derived.cd_receipt_date", "value": "<ZEN expression>"}],
   "passThrough": true, "inputField": null, "outputPath": null, "executionMode": "single"}}
```

A key with dots nests: `derived.cd_receipt_date` becomes `{"derived": {"cd_receipt_date": ...}}` (checked in the smoke test). One expression per node.

For a derived field of type `day_set`, `value` wraps the test of one day, taken from the source text, in a list of the days of a window:

```
filter(map([0..d(<to>, "UTC").add(<pad>, "d").diff(d(<from>, "UTC").sub(<pad>, "d"), "day")],
           d(<from>, "UTC").sub(<pad>, "d").add(#, "d").format("%Y-%m-%d")),
       <test of one day, # is the day>)
```

`<from>`, `<to>` and `<pad>` come from the vocabulary (`window`), not from the source text, and have no receipt. The window's dates are taken in UTC (the dates page documents a time zone as the second argument of `d()`): without one, zen-engine 2.1.2 uses the machine's zone, `add(n, "d")` steps 24 hours, and across a daylight-saving change the days slip by one (NOTES.md, item 15).

### decisionTableNode

```json
{"id": "table-s1026_19_f_1_ii_A", "type": "decisionTableNode", "name": "1026.19(f)(1)(ii)(A) In general",
 "position": {"x": 840, "y": 0},
 "content": {
   "hitPolicy": "collect",
   "inputs": [{"id": "i1", "name": "Applies when"}, {"id": "i2", "name": "Requirement met"}],
   "outputs": [{"id": "o1", "name": "Rule id", "field": "rule_id"},
               {"id": "o2", "name": "Result", "field": "result"}],
   "rules": [
     {"_id": "1026.19(f)(1)(ii)(A)/r1/pass", "i1": "<applies_when>", "i2": "<requirement>",
      "o1": "\"1026.19(f)(1)(ii)(A)/r1\"", "o2": "\"pass\""},
     {"_id": "1026.19(f)(1)(ii)(A)/r1/fail", "i1": "<applies_when>", "i2": "not (<requirement>)",
      "o1": "\"1026.19(f)(1)(ii)(A)/r1\"", "o2": "\"fail\""}],
   "passThrough": true, "inputField": null, "outputPath": "results.s1026_19_f_1_ii_A",
   "executionMode": "single"}}
```

- Input columns have no `field`, so their cells are standard-mode expressions (syntax page: "When an input column has no field name, standard expression mode is used instead"). An empty `i1` matches any loan file.
- Rows carry the rule id twice: in `_id`, the only documented row key besides column ids, and in the `rule_id` output column, so that results name the rule that produced them. The node types page documents no row description field.
- `hitPolicy` `collect` returns every matching row as a list under `outputPath`.

### Edges

```json
{"id": "edge-1", "sourceId": "input", "targetId": "derive-1", "sourceHandle": null, "type": "edge"}
```

## Result

Evaluating the model returns the input (`passThrough`), the derived fields, and:

```json
{"results": {"s1026_19_f_1_ii_A": [{"rule_id": "1026.19(f)(1)(ii)(A)/r1", "result": "fail"}],
             "s1026_19_f_1_ii_B": []}}
```

An empty list means no rule of that subsection applies to the loan file.

## Expression language used

Functions and methods a rule may call are the intersection of the vocabulary's lists and the documented ones (`jdm.ZEN_FUNCTIONS`, `jdm.ZEN_DATE_METHODS`):

- Functions page: `abs floor ceil round trunc min max sum avg median mode rand len upper lower trim contains startsWith endsWith matches extract split fuzzyMatch map filter some all one none count flatMap keys values merge mergeDeep d duration string number bool type isNumeric`.
- Dates page methods: `year month day weekday hour minute second dayOfYear quarter timestamp set add sub isBefore isAfter isSame isSameOrBefore isSameOrAfter diff startOf endOf tz offsetName isValid isToday isYesterday isTomorrow isLeapYear format`.

There is no business-day, workday or holiday function. The dates page shows `d(x).weekday() in [1..5]` as a "business days check", which treats Saturday as a non-business day and knows no holidays; it does not fit Regulation Z.

Operators: `and or not == != < <= > >= ?: ?? in`, list index `[n]`, closures with `#` or `as name`. Assignment, `;` sequences, template strings and object literals are refused by `validator.check_expression`.
