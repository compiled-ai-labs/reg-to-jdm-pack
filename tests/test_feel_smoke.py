"""The FEEL engine (dmn-scala 1.11.3, feel-scala 1.21.1, the versions Camunda 8.9 pins) loads
and evaluates a sample DMN from the Camunda docs, and behaves as the DMN target relies on.
If an engine upgrade changes one of these, a test here fails before a pack does."""

from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"


def _load(runner, xml: str):
    problem = runner.load(xml)
    assert problem is None, problem


def test_versions_are_camunda_8_9(feel_runner):
    assert feel_runner.version() == "dmn-engine 1.11.3, feel-engine 1.21.1"


def test_docs_sample_evaluates(feel_runner):
    # camunda/camunda-docs .sdk-repos/orchestration-cluster-api-php/examples/resources/
    # pricing.dmn, copied unchanged.
    _load(feel_runner, (DATA / "camunda-docs-pricing.dmn").read_text("utf-8"))
    assert feel_runner.eval("pricing", {"orderTotal": 50}) == ("STANDARD", None)
    assert feel_runner.eval("pricing", {"orderTotal": 150}) == ("PREMIUM", None)


def test_docs_sample_with_empty_input_expressions_is_rejected(feel_runner):
    # camunda/camunda-docs static/bpmn/best-practices/choosing-the-dmn-hit-policy-assets/
    # customer-discount.dmn: its input expressions have no text, which the engine refuses.
    problem = feel_runner.load(
        (DATA / "camunda-docs-customer-discount.dmn").read_text("utf-8"))
    assert problem and "must not be empty" in problem


def _value(runner, expr, context=None):
    value, _, error = runner.expr(expr, context or {})
    assert error is None, error
    return value


def test_list_index_starts_at_one(feel_runner):
    assert _value(feel_runner, "[10, 20, 30][1]") == 10
    assert _value(feel_runner, "[10, 20, 30][item > 10][2]") == 30


def test_day_of_week_is_the_english_name(feel_runner):
    assert _value(feel_runner, 'day of week(date("2026-10-11"))') == "Sunday"


def test_day_window_and_duration_days(feel_runner):
    assert _value(feel_runner, 'for i in 0..2 return string(date("2026-10-09") + '
                               'duration("P1D") * i)') == ["2026-10-09", "2026-10-10",
                                                           "2026-10-11"]
    assert _value(feel_runner, '(date("2026-10-19") - date("2026-10-09")).days') == 10


def test_failure_becomes_null_with_a_suppressed_failure(feel_runner):
    value, failures, error = feel_runner.expr('date(x) < date("2026-01-01")', {"x": None})
    assert error is None and value is None and failures


def test_filter_reports_failures_even_when_right(feel_runner):
    # Why the cell gate checks the value and not the suppressed failures (verify.py).
    # A filter whose test is a conjunction: the value is right, and the engine still records
    # "No variable found with name 'item'" and the failures that follow from it.
    value, failures, _ = feel_runner.expr("xs[item > 1 and item < 3]", {"xs": [1, 2, 3]})
    assert value == [2] and "No variable found with name 'item'" in failures


TABLE = """<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="https://www.omg.org/spec/DMN/20191111/MODEL/" id="d" name="d"
             namespace="http://example.org">
  <decision id="span" name="Span in days">
    <literalExpression id="le1"><text>(date(b) - date(a)).days</text></literalExpression>
  </decision>
  <decision id="t" name="Table">
    <informationRequirement id="ir1"><requiredDecision href="#span"/></informationRequirement>
    <decisionTable id="dt" hitPolicy="COLLECT">
      <input id="i1" label="Applies when">
        <inputExpression id="ie1" typeRef="boolean"><text>true</text></inputExpression>
      </input>
      <input id="i2" label="Requirement met">
        <inputExpression id="ie2" typeRef="boolean"><text>true</text></inputExpression>
      </input>
      <output id="o1" name="rule_id" typeRef="string"/>
      <output id="o2" name="result" typeRef="string"/>
      <rule id="r1">
        <inputEntry id="e1"><text>not(flag)</text></inputEntry>
        <inputEntry id="e2"><text>span &gt;= 3</text></inputEntry>
        <outputEntry id="e3"><text>"x/r1"</text></outputEntry>
        <outputEntry id="e4"><text>"pass"</text></outputEntry>
      </rule>
      <rule id="r2">
        <inputEntry id="e5"><text>-</text></inputEntry>
        <inputEntry id="e6"><text>date(missing) &lt; date(b)</text></inputEntry>
        <outputEntry id="e7"><text>"x/r2"</text></outputEntry>
        <outputEntry id="e8"><text>"pass"</text></outputEntry>
      </rule>
    </decisionTable>
  </decision>
</definitions>
"""


NOT_ENTRY = """<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="https://www.omg.org/spec/DMN/20191111/MODEL/" id="d" name="d"
             namespace="http://example.org">
  <decision id="t" name="t">
    <decisionTable id="dt" hitPolicy="COLLECT">
      <input id="i1"><inputExpression id="ie" typeRef="boolean"><text>true</text>
      </inputExpression></input>
      <output id="o" name="r" typeRef="string"/>
      <rule id="u1"><inputEntry id="a1"><text>not(t.x)</text></inputEntry>
        <outputEntry id="b1"><text>"negation"</text></outputEntry></rule>
      <rule id="u2"><inputEntry id="a2"><text>(not(t.x))</text></inputEntry>
        <outputEntry id="b2"><text>"function"</text></outputEntry></rule>
    </decisionTable>
  </decision>
</definitions>
"""


def test_leading_not_in_an_input_entry_is_unary_negation(feel_runner):
    """Why dmn.input_entry() puts a leading not(...) in parentheses: as unary tests,
    not(t.x) means "the input is not t.x", which holds when t.x is missing."""
    _load(feel_runner, NOT_ENTRY)
    assert feel_runner.eval("t", {"t": {"x": False}}) == (["negation", "function"], None)
    assert feel_runner.eval("t", {"t": {"x": True}}) == (None, None)
    assert feel_runner.eval("t", {}) == (["negation"], None)


def test_table_shape_of_the_dmn_target(feel_runner):
    """Boolean cells against a `true` input expression; a required decision by its id;
    COLLECT gives a list of rows, or null when none match; a cell that fails is a row that
    does not match, with no error."""
    _load(feel_runner, TABLE)
    ok = {"a": "2026-10-09", "b": "2026-10-19", "flag": False}
    assert feel_runner.eval("t", ok) == ([{"rule_id": "x/r1", "result": "pass"}], None)
    assert feel_runner.eval("t", {**ok, "flag": True}) == (None, None)
