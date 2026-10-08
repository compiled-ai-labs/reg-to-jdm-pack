# DMN target

The exact XML of `out/pack/rules.dmn`, next to `rules.jdm.json`: the same rules, from the same sources, vocabulary and test cases, as a DMN 1.3 model for Camunda 8. `dmn.check_structure()` enforces the element and attribute list below on every `verify --target dmn`, and the FEEL engine parses the file against the DMN 1.3 XSD.

Read on 2026-10-08:

- DMN 1.3 specification and XSD: https://www.omg.org/spec/DMN/1.3, https://www.omg.org/spec/DMN/20191111/DMN13.xsd (decision tables, unary tests, FEEL, `tDecision`, `tDecisionTable`, `tInputClause`, `tOutputClause`, `tDecisionRule`, `tInputData`, `tLiteralExpression`, `tInformationRequirement`, DMNDI).
- Camunda 8.9 DMN pages: https://docs.camunda.io/docs/components/modeler/dmn/ (decision table, input, output, rule, hit policy, literal expression, decision requirements graph).
- Camunda 8.9 FEEL pages: https://docs.camunda.io/docs/components/modeler/feel/ (language guide: variables, lists, unary tests, temporal expressions, error handling; built-in functions: boolean, string, numeric, list, context, temporal, range, conversion).
- Camunda versions: `camunda/camunda` branch `stable/8.9`, `parent/pom.xml`: `version.dmn-scala` 1.11.3, `version.feel-scala` 1.21.1. The c8run 8.9.23 distribution ships exactly `dmn-engine-1.11.3.jar` and `feel-engine-1.21.1.jar`.

Engine: Camunda's DMN engine (dmn-scala, `org.camunda.bpm.extension.dmn.scala:dmn-engine` 1.11.3) with Camunda's FEEL engine (feel-scala, `org.camunda.feel:feel-engine` 1.21.1), the pair Zeebe uses to deploy and evaluate DMN in Camunda 8.9, built as Zeebe builds it (`new DmnEngine.Builder().build()`). It runs as a Java 21 process (`runner/`, `src/reg_to_jdm/feel.py`). `tests/test_feel_smoke.py` loads and evaluates a sample DMN from the Camunda docs repository and pins every engine behaviour the target relies on.

## File

```xml
<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="https://www.omg.org/spec/DMN/20191111/MODEL/"
             xmlns:dmndi="https://www.omg.org/spec/DMN/20191111/DMNDI/"
             xmlns:dc="http://www.omg.org/spec/DMN/20180521/DC/"
             xmlns:di="http://www.omg.org/spec/DMN/20180521/DI/"
             xmlns:modeler="http://camunda.org/schema/modeler/1.0"
             id="reg_to_jdm" name="reg-to-jdm rule pack"
             namespace="https://github.com/compiled-ai-labs/reg-to-jdm"
             modeler:executionPlatform="Camunda Cloud"
             modeler:executionPlatformVersion="8.9.0">
  <inputData .../>            one per vocabulary field
  <decision .../>             one per derived field, in evaluation order
  <decision .../>             one per source paragraph with rules, in source order
  <decision id="results" .../>
  <dmndi:DMNDI>...</dmndi:DMNDI>
</definitions>
```

The DMN 1.3 namespace is the one Camunda 8 reads and the Desktop Modeler writes. `modeler:executionPlatform` and `modeler:executionPlatformVersion` are the Camunda Modeler's own attributes (`tDMNElement` allows attributes of other namespaces); with them the Modeler opens the file as a Camunda 8 diagram. No Camunda 7 `camunda:` attributes are emitted: Camunda 8 has none for DMN. No element is emitted without an `id`.

## inputData

```xml
<inputData id="input_cd_issue_date" name="cd.issue_date" label="date the Closing Disclosure was issued" />
```

One per vocabulary field, including the fields no rule uses (NOTES.md, assumption 8). `name` is the vocabulary path. No `variable` element: in Camunda 8 the input is the evaluation's variables, and `cd.issue_date` in FEEL is a path into the context `cd`; a FEEL variable name may not contain `.` (Camunda FEEL "variables" page). The inputData elements document what a decision needs and draw the graph; the engine does not read them.

## Derived fields: decision with a literal expression

```xml
<decision id="derived_cd_receipt_date" name="1026.19(f)(1)(iii) date the consumer received, ...">
  <informationRequirement id="derived_cd_receipt_date_needs_input_cd_delivery_method">
    <requiredInput href="#input_cd_delivery_method" />
  </informationRequirement>
  <informationRequirement id="derived_cd_receipt_date_needs_derived_business_days">
    <requiredDecision href="#derived_business_days" />
  </informationRequirement>
  <literalExpression id="derived_cd_receipt_date_expression">
    <text>if cd.delivery_method = "in_person" then cd.received_date else derived_business_days[date(item) &gt; date(cd.mailed_date)][3]</text>
  </literalExpression>
</decision>
```

The decision id is the derived field's path with `.` replaced by `_`. Camunda 8 makes a required decision's result available under the decision **id** (the Camunda docs say a dependent decision cannot reach a result whose id holds special characters), so FEEL cells name a derived field by that id: `derived.cd_receipt_date` is `derived_cd_receipt_date`. No `variable` element (optional in the XSD). The DMN 1.3 specification names a decision's result by its `variable`, whose name equals the decision's name; this target follows Camunda 8, where names are free text and ids are the variables. A DMN engine that resolves required decisions by name will not run this file without renaming.

No business knowledge models: a derived field is computed once per evaluation, so a decision fits. A BKM would be a function, called per rule.

A derived field of type `day_set` is the calendar window around the test of one day from the source text, as in the JDM (`dmn.day_set_expression`):

```
(for i in 0..(date(<to>) + duration("P<pad>D") - (date(<from>) - duration("P<pad>D"))).days
   return string(date(<from>) - duration("P<pad>D") + duration("P1D") * i))[<test of one day, item is the day>]
```

## Rules: one decision with a decision table per source paragraph

```xml
<decision id="s1026_19_f_1_ii_A" name="1026.19(f)(1)(ii)(A) In general">
  <informationRequirement ...>...</informationRequirement>
  <decisionTable id="s1026_19_f_1_ii_A_table" hitPolicy="COLLECT">
    <input id="s1026_19_f_1_ii_A_applies" label="Applies when">
      <inputExpression id="s1026_19_f_1_ii_A_applies_expression" typeRef="boolean"><text>true</text></inputExpression>
    </input>
    <input id="s1026_19_f_1_ii_A_requirement" label="Requirement met">
      <inputExpression id="s1026_19_f_1_ii_A_requirement_expression" typeRef="boolean"><text>true</text></inputExpression>
    </input>
    <output id="s1026_19_f_1_ii_A_rule_id" name="rule_id" label="Rule id" typeRef="string" />
    <output id="s1026_19_f_1_ii_A_result" name="result" label="Result" typeRef="string" />
    <rule id="rule_1026_19_f_1_ii_A_r1_pass">
      <description>1026.19(f)(1)(ii)(A)/r1/pass</description>
      <inputEntry id="rule_1026_19_f_1_ii_A_r1_pass_applies"><text>(not(transaction.timeshare))</text></inputEntry>
      <inputEntry id="rule_1026_19_f_1_ii_A_r1_pass_requirement"><text>count(...) &gt;= 3</text></inputEntry>
      <outputEntry id="rule_1026_19_f_1_ii_A_r1_pass_rule_id"><text>"1026.19(f)(1)(ii)(A)/r1"</text></outputEntry>
      <outputEntry id="rule_1026_19_f_1_ii_A_r1_pass_result"><text>"pass"</text></outputEntry>
    </rule>
    <rule id="rule_1026_19_f_1_ii_A_r1_fail"> ... (not(<requirement>)) ... "fail" </rule>
  </decisionTable>
</decision>
```

- Decision id: the paragraph label as a key, `1026.19(f)(1)(ii)(A)` becomes `s1026_19_f_1_ii_A`, the same key as the JDM `outputPath`.
- Hit policy `COLLECT` without aggregation: the result is the list of `{rule_id, result}` of every matching rule, or null when none matches. The Camunda page says the order is arbitrary; nothing here depends on order.
- Two inputs whose input expression is the literal `true`, and input entries that are whole FEEL boolean expressions. The Camunda unary-tests page: an entry is satisfied when the expression's value equals the input value, so a boolean cell matches when it is `true`. This is the JDM shape (cells holding standard expressions) in DMN terms.
- An entry is unary tests, where a leading `not(...)` is the negation of unary tests ("the input is not ..."), not the `not()` function: with input `true`, `not(x)` matches when `x` is null. An entry whose top level is `not(...)` is emitted in parentheses, which makes it one expression (`dmn.input_entry` checks it; pinned in `tests/test_feel_smoke.py`).
- An empty "applies when" is `-` (any input).
- Rule ids: `rule_<slug of the rule id>_<pass|fail>`. DMN ids are `xsd:ID` (NCName): `(`, `)` and `/` are not allowed, so the rule id cannot be the DMN id as it is the JDM `_id`. The exact rule id is in the `rule_id` output and in the rule's `description` (`DMNElement` has a description; the JDM row has none). `receipts.json` maps each rule id to its two DMN rule ids under `dmn.rules`.

## The results decision

```xml
<decision id="results" name="Results">
  <informationRequirement ...> every table decision and every derived decision </informationRequirement>
  <literalExpression id="results_expression">
    <text>{results: {s1026_19_f_1_ii_A: s1026_19_f_1_ii_A, ...}, derived: {business_days: derived_business_days, ...}}</text>
  </literalExpression>
</decision>
```

Camunda 8 evaluates one decision (with the decisions it requires) per call. The JDM evaluates every node and returns one object. The aggregate decision returns the same shape as the JDM output (`results.<key>` lists, `derived.<field>` values), so `verify` runs the same test checks on both. It holds no rule; `verify` checks that it is exactly the aggregate of the other decisions.

## Diagram (DMNDI)

`dmndi:DMNDI/dmndi:DMNDiagram` with one `dmndi:DMNShape` (`dc:Bounds`) per inputData and decision and one `dmndi:DMNEdge` (two `di:waypoint`) per information requirement. Without DI the Modeler draws no requirements graph. Layout: inputs used by a decision in a row at the bottom (in order of first use), unused vocabulary fields below them, derived decisions above, table decisions above those, results on top.

## Elements and attributes emitted

| Element | Attributes | Children |
| - | - | - |
| `definitions` | `id`, `name`, `namespace`, `modeler:executionPlatform`, `modeler:executionPlatformVersion` | `inputData`, `decision`, `dmndi:DMNDI` |
| `inputData` | `id`, `name`, `label` | |
| `decision` | `id`, `name` | `informationRequirement`, `literalExpression`, `decisionTable` |
| `informationRequirement` | `id` | `requiredInput` or `requiredDecision` (`href`) |
| `literalExpression` | `id` | `text` |
| `decisionTable` | `id`, `hitPolicy` | `input`, `output`, `rule` |
| `input` | `id`, `label` | `inputExpression` (`id`, `typeRef`; `text`) |
| `output` | `id`, `name`, `label`, `typeRef` | |
| `rule` | `id` | `description`, `inputEntry` (`id`; `text`), `outputEntry` (`id`; `text`) |
| `dmndi:DMNDiagram` | `id` | `dmndi:DMNShape` (`id`, `dmnElementRef`; `dc:Bounds`), `dmndi:DMNEdge` (`id`, `dmnElementRef`; `di:waypoint`) |

Element order follows the XSD sequences (`description` first, `informationRequirement` before the expression, `input` before `output` before `rule`).

## FEEL in cells

Rules may use only the FEEL built-in functions the Camunda 8.9 pages document. The list is `feelexpr.FEEL_FUNCTIONS`, one entry per documented name: boolean (`not`, `is defined`, `get or else`, `assert`), string, numeric, list (`list contains`, `count`, `min`, `max`, `sum`, ...), context, temporal (`now`, `today`, `day of week`, `day of year`, `week of year`, `month of year`, `last day of month`), range, and conversion (`string`, `number`, `date`, `time`, `date and time`, `duration`, `years and months duration`, `to json`, `from json`). The AI-agent function `fromAi` is left out: it is not a rule function.

The FEEL gate (`feelexpr.check_feel`) on every cell: the cell parses (this repo's parser for the subset below, and the engine's parser in `verify`); every function is a documented built-in; every name is a vocabulary field or a derived field's decision id; every number is stated in the rule's quote, where a list index `[n]` counts as element n (FEEL lists start at 1) and a negative index is refused, a duration literal `"PnD"` counts as the number n, and a weekday name compared with `day of week()` needs a vocabulary encoding whose word is in the quote.

There is no business-day or holiday function in FEEL. As in the JDM target, the day set is built from the calendar window and `calendar.holidays`, supplied with the input.

## The same rule in both targets

Each line is a place where `rules.jdm.json` and `rules.dmn` write the same rule differently. `tests/test_feelexpr.py` checks that every FEEL cell reads, in the readback's words, the same as the ZEN expression of the same rule, and `tests/test_targets_agree.py` that both give the same verdict on every test case.

| ZEN (JDM) | FEEL (DMN) |
| - | - |
| `d(x)` | `date(x)` |
| `c ? a : b` | `if c then a else b` |
| `a == b` | `a = b` |
| `not x` | `not(x)` |
| `count(L as day, P)`, `#` | `count(L[P])`, `item` (no nested filters: both would be `item`) |
| `filter(L as day, P)[n]` (0-based) | `L[P][n+1]` (1-based) |
| `contains(date_list, x)` | `list contains(L, x)` (`contains()` for strings; the type comes from the vocabulary) |
| `len(list)` | `count(list)` (`string length()` for strings) |
| `d(x).weekday() == 7` | `day of week(date(x)) = "Sunday"` (FEEL gives the name, not a number) |
| `d(x).add(n, "d")`, `.sub` | `date(x) + duration("PnD")`, `-` |
| `a.diff(b, "day")` | `(a - b).days` |
| `.format("%Y-%m-%d")` | `string(...)` |
| `.isBefore`, `.isAfter`, `.isSame`, `.isSameOrBefore`, `.isSameOrAfter` | `<`, `>`, `=`, `<=`, `>=` |
| `derived.x` | `derived_x` (the decision id) |
