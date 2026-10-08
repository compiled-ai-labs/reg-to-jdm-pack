# Notes

## Provenance of the example pack

- Source text: eCFR versioner API, title 12, point in time 2026-10-05, sections 1026.19 and 1026.2, extracted from the XML with the italic headings marked as `_Heading._`. Characters as published (§, curly apostrophes, the dashes in the parent headings).
- Model: Claude Opus 5.5 (`claude-opus-5-5`), used through a chat session on 2026-10-07, with no API call.
- Analyst: the answers in `out/pack/answers.yaml` were drafted by the same Claude session and reviewed and accepted by Boris Teplitsky on 2026-10-07, as recorded in `answered_by`.
- Two passes: the first with the original vocabulary (three questions, two rules blocked; kept in `examples/trid-19f-first-pass/`), the second after the answers and the vocabulary change. Every record passed the gates on its first attempt in both passes.

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
13. Loading into the GoRules editor or BRMS: the standard page describes exporting JDM from BRMS, not importing. Not tested here; the Python SDK load is tested.
