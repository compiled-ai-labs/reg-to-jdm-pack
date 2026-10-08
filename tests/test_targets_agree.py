"""Both targets give the same verdict on every test case of the committed pack: every rule's
result, every scalar derived value, and every fixture's verdict for its paragraph.

Day sets: the DMN list must be exactly the calendar window filtered by the day test. The ZEN
list may fall short of it at the window's end and nowhere else: ZEN's d().add(n, "d") adds
n x 24 hours in the machine's local time zone, so on a machine whose zone leaves daylight
saving inside the window the last day(s) drop out (NOTES.md, JDM findings).
"""

import json
from datetime import date, timedelta
from pathlib import Path

import pytest
import zen

from reg_to_jdm.validator import evaluate, get_path
from reg_to_jdm.vocab import load_vocabulary

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "out" / "pack"
TESTS = sorted((PACK / "tests").glob("*.json"))
VOCAB = load_vocabulary(ROOT, "vocab/loan-file.yaml")


def _verdict(entries: list | None) -> str:
    """The paragraph's verdict as the compiler reads a fixture: no row, any fail, all pass."""
    results = [e["result"] for e in entries or []]
    if not results:
        return "not_applicable"
    return "fail" if "fail" in results else "pass"


def _window(inp: dict, window: dict) -> list[str]:
    pad = timedelta(days=window["pad_days"])
    start = date.fromisoformat(get_path(inp, window["from"])) - pad
    end = date.fromisoformat(get_path(inp, window["to"])) + pad
    return [(start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)]


@pytest.fixture(scope="module")
def engines(feel_runner):
    model = (PACK / "rules.jdm.json").read_text("utf-8")
    decision = zen.ZenEngine().create_decision(model)
    problem = feel_runner.load((PACK / "rules.dmn").read_text("utf-8"))
    assert problem is None, problem
    return decision, feel_runner


@pytest.mark.parametrize("path", TESTS, ids=[p.stem for p in TESTS])
def test_same_verdict(engines, path):
    decision, runner = engines
    test = json.loads(path.read_text("utf-8"))
    jdm, error = evaluate(decision, test["input"])
    assert error is None, error
    dmn, error = runner.eval("results", test["input"])
    assert error is None, error
    # A derived-field test supplies only what its field needs; the others are compared on the
    # rule and fixture tests, which give a whole loan file. (Where an input is missing, ZEN's
    # d(null) is an "Invalid date" that still compares, FEEL's date(null) is null.)
    fields = [test["field"]] if "field" in test else list(VOCAB.derived)
    for field in fields:
        spec = VOCAB.derived[field]
        z, f = get_path(jdm, field), get_path(dmn, field)
        if spec.type != "day_set":
            assert f == z, field
            continue
        window = _window(test["input"], spec.window)
        assert f == [d for d in window if d in set(f)], "DMN day set is not in window order"
        assert set(f) <= set(window)
        missing = [d for d in f if d not in z]
        assert not set(z) - set(f), f"{field}: ZEN has days DMN does not"
        assert missing == f[len(f) - len(missing):], f"{field}: differs before the window end"
    keys = set(jdm.get("results") or {}) | set(dmn.get("results") or {})
    for key in keys:
        z = sorted((e["rule_id"], e["result"]) for e in (jdm["results"].get(key) or []))
        f = sorted((e["rule_id"], e["result"]) for e in (dmn["results"].get(key) or []))
        assert z == f, key
    if "subsection_key" in test:
        key = test["subsection_key"]
        assert _verdict(jdm["results"].get(key)) == _verdict(dmn["results"].get(key)) \
            == test["expected"]["result"]
