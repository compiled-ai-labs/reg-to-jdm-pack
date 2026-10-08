# Notes

## Provenance of the example pack

- Source text: eCFR versioner API, title 12, point in time 2026-10-05, sections 1026.19 and 1026.2, extracted from the XML with the italic headings marked as `_Heading._`. Characters as published (§, curly apostrophes, the dashes in the parent headings).
- Model: Claude Opus 5.5 (`claude-opus-5-5`), used through a chat session on 2026-10-07, with no API call.
- Analyst: the answers in `out/pack/answers.yaml` were drafted by the same Claude session and reviewed and accepted by Boris Teplitsky on 2026-10-07, as recorded in `answered_by`.
- Two passes: the first with the original vocabulary (three questions, two rules blocked; kept in `examples/trid-19f-first-pass/`), the second after the answers and the vocabulary change. Every record passed the gates on its first attempt in both passes.
- GoRules editor: the pack was loaded and simulated in editor.gorules.io on 2026-10-08. All nodes evaluated, including the map over an interval in the business-days node.

## Assumptions

1. `closing_date` is the date of consummation. In some states consummation and closing differ; the vocabulary label says "date of consummation" and the caller must supply that date.
2. The loan file says how the Closing Disclosure was provided (`cd.delivery_method`). The original vocabulary had no such field, and 1026.19(f)(1)(iii) cannot be applied without it.
3. `cd.received_date` is used as the receipt date only for in-person delivery. For mail and electronic delivery the presumption of (f)(1)(iii) is applied even when the file records an earlier actual receipt; the text alone does not say when the presumption may be rebutted.
4. Legal public holidays come with the loan file (`calendar.holidays`), as observed. The test cases list 2026-10-12, 2026-11-11, 2026-11-26 and 2026-12-25. Juneteenth is a legal public holiday under 5 U.S.C. 6103(a) but is not named in 1026.2(a)(6); the caller's list decides.
5. Business days are listed over a window from `cd.issue_date` minus 10 days to `closing_date` plus 10 days (vocabulary `window`). A mailing date before the window start would give a wrong deemed receipt date. The window is code, not text, and has no receipt.
6. 1026.19(f)(1)(ii)(A) is written as "at least three business days fall on or after the receipt date and before consummation". That is the same as "receipt no later than the third business day before consummation" for every pair of dates: the third business day before consummation, X, has exactly three business days in [X, consummation). The count is taken back from consummation, so a consummation on a Sunday or holiday is judged by the business days before it. The readback shows the counting form.
7. Out of scope by decision (`answers.yaml`): coverage under 1026.19(e)(1)(i), the content requirements of 1026.38, and the exceptions in 1026.19(f)(2)(i), (iii), (iv), (v). The receipts list them as external links. The pack's verdict is wrong for a loan file to which one of those exceptions applies.
8. `note.amount`, `cd.amount`, `ltv` and `flood_zone` stay in the vocabulary although no sentence uses them; they test that the model does not reach for unrelated fields. The model named the amounts once, as reading b of the (f)(1)(i) question, and that reading was not chosen.
9. Rule ids are `<sentence id>/r<n>` and `<sentence id>/d<n>`. A new sentence inserted into a paragraph shifts the `.sN` ids after it.
10. `verify` reports open questions without failing; `verify --final` fails on them. CI uses `--final`.
11. Python 3.12. `zen-engine` is pinned to 2.1.2; its abi3 wheels cover Linux, macOS and Windows.

## Where the JDM docs were unclear

1. The page `/reference/overview` describes deployment and SDKs. The format is on `/developers/jdm/standard` and `/developers/jdm/node-types`.
2. No row description field: the node types page documents only `_id` and column ids on a row. The rule id is in `_id` and in a `rule_id` output column.
3. The standard page says the complete JSON Schema is "available in the zen repository" without a path. `check_structure()` uses the keys listed on the node types page instead.
4. Input columns without a field: the node types page lists `field` as an input column property; the syntax page says a column with no field name uses standard expressions. The pack's columns have no `field`. In zen-engine 2.1.2 an empty-string `field` behaves the same.
5. How the outputs of several nodes combine at the output node is not described. The model is a chain with `passThrough: true`, each table writing under its own `outputPath`; checked in tests.
6. `hitPolicy: "collect"` output shape (a list under `outputPath`) is not shown in the docs; observed in zen-engine 2.1.2.
7. Intervals: `[a..b]` appears only in range checks. `map([0..n], ...)` iterates it in zen-engine 2.1.2; `day_set_expression()` relies on that, and a smoke test pins it.
8. Negative index: the operators page shows `items[-1]`. On a computed list zen-engine 2.1.2 fails with "Failed to convert to usize". The number gate refuses negative indexes.
9. Comparing two date strings with `<` fails in the engine ("Unsupported type"); the docs do not say which types the comparison operators accept. Rules compare dates through `d(...)`.
10. A cell expression that raises an error makes its row not match, with no error in the result. The docs do not mention this. `verify` evaluates every cell of the rows under test and fails on an error.
11. The dates page shows `d(x).weekday() in [1..5]` as a "business days check". It excludes Saturday and knows no holidays, so it does not fit Regulation Z.
12. `inputNode.content.schema` is documented as an optional JSON Schema string, but not whether the Python engine enforces it. It is left empty.
13. Loading into the GoRules editor or BRMS: the standard page describes exporting JDM from BRMS, not importing. The pack loads in editor.gorules.io (see Provenance); BRMS import is not tested.
14. Inputs are nested objects. The docs show nested paths in fields and expressions but do not say that a flat dotted key in the input is stored as a literal key that expressions do not resolve: `{"cd.issue_date": ...}` is not `cd.issue_date`. Confirmed in the web editor on 2026-10-08, where the first expression node returned null; zen-engine 2.1.2 in Python stops with an error in the same node. Fixtures and test cases are nested and reach the engine as written.
15. ZEN date arithmetic runs in the machine's time zone (found 2026-10-08 while comparing with the DMN target; fixed the same day). `d(x)` without a zone takes the machine's zone, though the dates page shows its examples with a `Z` suffix; Windows ignores `TZ`. `add(n, "d")` then adds n x 24 hours, so across the end of daylight saving inside the day window (2026-10-25 on the machine that found it, +03:00 to +02:00) every later day landed at 23:00 of the day before: the business-day list repeated 2026-10-25 and lost the last day(s) of the window (for a closing on 2026-10-19 it ended at 2026-10-27, not 2026-10-29). No verdict was wrong, by luck: the repeated day was a Sunday, which the day test removes, and the window has 10 days of padding. In a zone that leaves daylight saving on a business day, that day would have counted twice. The fix: the window takes its dates in UTC, `d(<field>, "UTC")`, the time-zone argument the dates page documents. Only the business-days node of `rules.jdm.json` changed; the rules, receipts, readback and test cases did not. `tests/test_zen_smoke.py` pins an exact window across the 2026 changes in the EU, Israel and the US on any machine, and `tests/test_targets_agree.py` requires the JDM and DMN day lists to be equal.

## DMN target

Added 2026-10-08: `out/pack/rules.dmn`, DMN 1.3 for Camunda 8, compiled from the same sources, vocabulary and answers as the JDM, with the same test cases. New here: `dmn.py` (structure check), `feelexpr.py` (FEEL parser, gate, readback), `feel.py` and `runner/` (the FEEL engine), `verify --target jdm|dmn|all`, the DMN section of `readback.md`, `dmn` entries in `receipts.json`. `rules.jdm.json` and `tests/` are unchanged. Format: `docs/dmn-target.md`.

### FEEL engine

Camunda's DMN engine, dmn-scala (`org.camunda.bpm.extension.dmn.scala:dmn-engine` 1.11.3), with Camunda's FEEL engine, feel-scala (`org.camunda.feel:feel-engine` 1.21.1), on Java 21 (Temurin 21.0.12 here). `runner/` is a small Java program speaking JSON lines; Maven builds it into one jar.

Why: Camunda 8 (Zeebe) deploys and evaluates DMN with exactly this pair. The versions are the ones `camunda/camunda` pins on `stable/8.9` (`parent/pom.xml`: `version.dmn-scala` 1.11.3, `version.feel-scala` 1.21.1), and the c8run 8.9.23 download ships `dmn-engine-1.11.3.jar` and `feel-engine-1.21.1.jar`. The runner builds the engine as Zeebe's `DmnScalaDecisionEngine` does (`new DmnEngine.Builder().build()`). dmn-scala parses the file with the Camunda DMN model API, which validates against the DMN 1.3 XSD, so loading the file is also the schema check. The other candidates are further from Camunda 8. feel-scala is Camunda's own engine; Red Hat's DMN engine (KIE/Drools) is a separate implementation with its own FEEL. No Python FEEL implementation tracks Camunda's. `tests/test_feel_smoke.py` pins the versions, loads `pricing.dmn` from the Camunda docs repository (`.sdk-repos/orchestration-cluster-api-php/examples/resources/`, unchanged in `tests/data/`), evaluates it, and pins every engine behaviour below.

### Where DMN and JDM model the same rule differently

1. Lists: ZEN indexes from 0 and FEEL from 1. `filter(...)[2]` becomes `[...][3]`. The number gate reads FEEL `[3]` as "third", and the quote says "three business days", in both.
2. Weekdays: ZEN `weekday()` is a number (7 is Sunday) and needs the encoding; FEEL `day of week()` is the name. The gate requires the encoding's word in the quote in both targets.
3. Conditional: `c ? a : b` becomes `if c then a else b`. Equality: `==` becomes `=`. Negation: `not x` becomes `not(x)`.
4. Filters: ZEN names the element (`as day`) or uses `#`; FEEL always calls it `item`, so a filter cannot hold another filter. The readback calls `item` "the day", which reads the same as ZEN's `day`.
5. `contains()`: ZEN has one function for lists and strings. FEEL has `list contains()` and `contains()`, and the vocabulary type decides which.
6. Derived fields: a JDM expression node writes `derived.cd_receipt_date` into the context. In DMN it is a decision with id `derived_cd_receipt_date`, and FEEL cells use that id. Camunda 8 stores a required decision's result under the decision id, and FEEL names may not contain `.`.
7. One evaluation: the JDM evaluates every node and returns one object. Camunda evaluates one decision per call, so a `results` decision gathers the tables and derived values into the JDM's output shape.
8. Cells: JDM table cells are standard expressions. DMN input entries are unary tests, so each table has two inputs whose expression is `true`, and each cell is a boolean expression that matches when it is `true`. A cell whose top level is `not(...)` is put in parentheses (finding 1 below).
9. Rule ids: the JDM row `_id` is the rule id. A DMN `id` must be an NCName, so it is a slug (`rule_1026_19_f_1_ii_A_r1_pass`), and the rule id goes in the `rule_id` output and in the rule's `description` (JDM rows have no description).
10. Inputs: JDM has one input node. DMN has one `inputData` per vocabulary field, wired to the decisions that read it. Camunda does not read them; they document the graph.
11. Day window: the same window and the same test of one day, built as `for i in 0..n return ...` over durations instead of `map([0..n], ...)` over `add(#, "d")`. Both are exact calendar arithmetic; the JDM window was not until its dates were taken in UTC (JDM item 15).
12. No match: the COLLECT result is null in DMN. The JDM gives an empty list in Python and leaves the key out in the editor.
13. Missing input fields: ZEN `d(null)` is an "Invalid date" that still compares, while FEEL `date(null)` is null. Derived values over fields a test does not supply differ: the business-day tests give no delivery method, and ZEN still computes a receipt date. No rule verdict differs. The agreement test compares derived values only where the test supplies their inputs.

### Findings: FEEL, Camunda's engine and the Modeler

1. A leading `not(...)` in an input entry is the unary-tests negation ("the input is not ..."), not the `not()` function. With the input `true`, `not(transaction.timeshare)` matched when `transaction` was missing, so a rule applied where the JDM gives no row. Found by the agreement test on the derived-field test cases. `rules.dmn` puts every such entry in parentheses, which makes it one expression; `verify` checks it (`dmn.input_entry`), and the smoke test pins the behaviour.
2. feel-scala 1.21.1 records suppressed failures ("No variable found with name 'item'", then failures for each comparison) for a filter whose test is a conjunction (`xs[item > 1 and item < 3]`), and the value is still right. The suppressed failures cannot serve as the cell gate. The DMN cell gate checks that each cell of the rows under test evaluates to a boolean; an error turned into null fails it.
3. An expression that fails becomes null with a suppressed failure, and does not stop the evaluation. A table cell that fails is a row that silently does not match, the same as in ZEN (JDM finding 10). The cell gate covers both targets.
4. Five of the nine DMN files in the Camunda docs repository do not load in Camunda's own engine: the hit-policy best-practice assets have empty input expressions or output entries ("The expression ... must not be empty"). The smoke test pins this on `customer-discount.dmn`. The decision-table pages show only fragments, so the full sample came from the SDK examples.
5. The DMN 1.3 specification names a decision's result by its `variable`, whose name equals the decision's name. Camunda 8 uses the decision id (the decision-table page's id rules, and a Camunda forum answer), so `rules.dmn` relies on ids. An engine that follows the specification would need the decision names to be the variable names.
6. A FEEL variable name may not contain `.` ("variables" page), so a vocabulary path like `cd.issue_date` cannot be an `inputData` variable. It is a path into the `cd` context. The `inputData` elements carry the path as `name` and have no `variable`.
7. FEEL negative list indexes count from the end and work on computed lists (ZEN fails; JDM finding 8). The number gate still refuses them: no quote states a position from the end.
8. The Camunda docs give the hit policy COLLECT result as "in an arbitrary order"; nothing here depends on order.
9. Camunda Desktop Modeler 5.52.0 (Windows zip, github.com/camunda/camunda-modeler) opens `rules.dmn` as a Camunda 8 diagram. Its workspace records no import messages for the file (`"messages": []` in its `config.json`) and it draws the requirements graph from the DMNDI. On first start the Modeler asks to enable error reports, usage statistics and update checks; all three were declined.
10. I found no DMN simulator in Desktop Modeler 5.52 (its menus are File, Edit, Window, Help, and the Camunda 8 DMN pages describe modeling only). The evaluation was checked by deploying to Camunda 8 Run instead (below).

### How the DMN was checked

- Engine, on every run of the tests: `verify --final --target all`. It checks the structure, loads into dmn-scala 1.11.3 (XSD and every FEEL expression), matches the receipts against the DMN rules, runs the FEEL gate and the engine parser on every cell, and evaluates all 16 test cases with the cell gate. `tests/test_targets_agree.py` runs every test case in both engines and requires the same rule results, the same scalar derived values, and the same fixture verdicts.
- Camunda Desktop Modeler 5.52.0 on Windows 11, 2026-10-08: `Camunda Modeler.exe out/pack/rules.dmn`. The file opened with no import messages. The screenshot is of the requirements graph, captured with PrintWindow from a window larger than the screen. The screen was not taking input at the time, so the decision-table view was not captured.
- Camunda 8 Run 8.9.23 (Windows, H2, no authentication), 2026-10-08: `scripts/camunda_run_check.py` deployed `rules.dmn` through `POST /v2/deployments`. All five decisions deployed, which is Zeebe's own validation. It then evaluated `results` for every test input through `POST /v2/decision-definitions/evaluation`:

| Test | Expected | ZEN (JDM) | dmn-scala (DMN) | Camunda 8.9.23 (DMN) |
| - | - | - | - | - |
| 1026-19-f-1-ii-A-r1-test-1 | pass | pass | pass | pass |
| 1026-19-f-1-ii-A-r1-test-2 | fail | fail | fail | fail |
| 1026-19-f-1-ii-A-r1-test-3 | not_applicable | not_applicable | not_applicable | not_applicable |
| 1026-19-f-1-ii-B-r1-test-1 | pass | pass | pass | pass |
| 1026-19-f-1-ii-B-r1-test-2 | fail | fail | fail | fail |
| 1026-19-f-1-ii-B-r1-test-3 | not_applicable | not_applicable | not_applicable | not_applicable |
| 1026-19-f-1-iii-d1-test-1 | 2026-10-15 | 2026-10-15 | 2026-10-15 | 2026-10-15 |
| 1026-19-f-1-iii-d1-test-2 | 2026-10-23 | 2026-10-23 | 2026-10-23 | 2026-10-23 |
| 1026-19-f-1-iii-d1-test-3 | 2026-10-14 | 2026-10-14 | 2026-10-14 | 2026-10-14 |
| 1026-2-a-6-s2-d1-test-1 | includes/excludes | holds | holds | holds |
| 1026-2-a-6-s2-d1-test-2 | includes/excludes | holds | holds | holds |
| fixture-cd-mailed-tuesday-closing-thursday | fail | fail | fail | fail |
| fixture-cd-received-friday-closing-monday | fail | fail | fail | fail |
| fixture-cd-received-saturday-closing-after-columbus-day | fail | fail | fail | fail |
| fixture-cd-received-thursday-closing-monday | pass | pass | pass | pass |
| fixture-timeshare-received-friday-closing-monday | pass | pass | pass | pass |
