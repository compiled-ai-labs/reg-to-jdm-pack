"""zen-engine loads and evaluates the decision table sample of the GoRules node types page,
and behaves as this pack relies on. If an engine upgrade changes one of these, a test
here fails before a pack does."""

import json

import pytest
import zen

# https://docs.gorules.io/developers/jdm/node-types, decision table node, wired from an input
# node to an output node as the JDM standard page describes.
DOCS_SAMPLE = {
    "nodes": [
        {"id": "input", "type": "inputNode", "name": "Request", "position": {"x": 0, "y": 100},
         "content": {"schema": ""}},
        {"id": "table", "type": "decisionTableNode", "name": "Customer Discount",
         "position": {"x": 200, "y": 100},
         "content": {
             "hitPolicy": "first",
             "inputs": [{"id": "i1", "name": "Customer Tier", "field": "customer.tier"},
                        {"id": "i2", "name": "Order Total", "field": "order.total"}],
             "outputs": [{"id": "o1", "name": "Discount", "field": "discount"}],
             "rules": [{"_id": "r1", "i1": "\"gold\"", "i2": ">= 100", "o1": "0.15"},
                       {"_id": "r2", "i1": "", "i2": "", "o1": "0"}],
             "passThrough": True, "inputField": None, "outputPath": None,
             "executionMode": "single"}},
        {"id": "output", "type": "outputNode", "name": "Response",
         "position": {"x": 600, "y": 100}, "content": {"schema": ""}},
    ],
    "edges": [
        {"id": "e1", "sourceId": "input", "targetId": "table", "sourceHandle": None,
         "type": "edge"},
        {"id": "e2", "sourceId": "table", "targetId": "output", "sourceHandle": None,
         "type": "edge"},
    ],
}


def _decision(model: dict):
    return zen.ZenEngine().create_decision(json.dumps(model))


def test_docs_sample_loads_and_evaluates():
    decision = _decision(DOCS_SAMPLE)
    gold = decision.evaluate({"customer": {"tier": "gold"}, "order": {"total": 150}})
    silver = decision.evaluate({"customer": {"tier": "silver"}, "order": {"total": 150}})
    assert gold["result"]["discount"] == 0.15
    assert silver["result"]["discount"] == 0


def test_date_functions_from_the_dates_page():
    ev = zen.evaluate_expression
    assert ev('d("2024-01-15").weekday()', {}) == 1          # the page's example: Monday
    assert ev('d("2026-10-04").weekday()', {}) == 7          # Sunday is 7
    assert ev('d("2024-01-15").diff("2024-01-10", "day")', {}) == 5
    assert ev('d("2024-01-15").add(1, "d").format("%Y-%m-%d")', {}) == "2024-01-16"


def test_map_over_an_interval_works_though_undocumented():
    # The docs show [a..b] only in range checks; day_set_expression() relies on map() over it.
    days = zen.evaluate_expression('map([0..2], d("2026-10-03").add(#, "d").format("%Y-%m-%d"))',
                                   {})
    assert days == ["2026-10-03", "2026-10-04", "2026-10-05"]


def test_negative_index_on_a_computed_list_fails_though_documented():
    # The operators page documents items[-1]; on a computed list zen-engine 2.1.2 rejects it,
    # which is why the number gate refuses negative indexes.
    with pytest.raises(RuntimeError):
        zen.evaluate_expression("filter([1, 2, 3], # > 0)[-1]", {})


def test_plain_string_comparison_fails():
    with pytest.raises(RuntimeError):
        zen.evaluate_expression('"2026-10-09" < "2026-10-12"', {})


def test_a_cell_that_raises_makes_its_row_silently_not_match():
    model = json.loads(json.dumps(DOCS_SAMPLE))
    table = model["nodes"][1]["content"]
    table["inputs"] = [{"id": "i1", "name": "Bad"}]
    table["rules"] = [{"_id": "r1", "i1": '"a" < "b"', "o1": "1"}]
    result = _decision(model).evaluate({})["result"]
    assert "discount" not in result


def test_expression_key_with_dots_nests():
    model = json.loads(json.dumps(DOCS_SAMPLE))
    model["nodes"][1] = {
        "id": "table", "type": "expressionNode", "name": "x", "position": {"x": 0, "y": 0},
        "content": {"expressions": [{"id": "e1", "key": "derived.x", "value": "1 + 1"}],
                    "passThrough": True, "inputField": None, "outputPath": None,
                    "executionMode": "single"}}
    assert _decision(model).evaluate({})["result"]["derived"] == {"x": 2}


def test_utc_window_is_exact_across_daylight_saving():
    """day_set_expression() takes the window's dates in UTC. Without a zone, d() takes the
    machine's zone and add(n, "d") steps 24 hours, so across the end of daylight saving every
    later day lands on the day before (NOTES.md, JDM item 15). These must hold on any machine."""
    from datetime import date, timedelta

    from reg_to_jdm.jdm import day_set_expression

    window = {"from": "a", "to": "b", "pad_days": 10}
    expr = day_set_expression(window, "true")
    for a, b in (("2026-10-14", "2026-10-19"),   # EU and Israel leave summer time 2026-10-25
                 ("2026-10-28", "2026-11-02"),   # the US leaves it 2026-11-01
                 ("2026-03-20", "2026-03-30")):  # EU starts it 2026-03-29
        days = zen.evaluate_expression(expr, {"a": a, "b": b})
        start = date.fromisoformat(a) - timedelta(days=10)
        n = (date.fromisoformat(b) - date.fromisoformat(a)).days + 21
        assert days == [(start + timedelta(days=i)).isoformat() for i in range(n)], (a, b)
