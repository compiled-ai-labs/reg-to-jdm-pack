"""The FEEL gate and the FEEL readback of the DMN target."""

import json
from pathlib import Path

import pytest

from reg_to_jdm.feelexpr import ParseError, analyze, check_feel, parse
from reg_to_jdm.numbers_en import numbers_in
from reg_to_jdm.readback import _english, feel_english
from reg_to_jdm.verify import known_names
from reg_to_jdm.vocab import load_vocabulary

ROOT = Path(__file__).resolve().parents[1]
VOCAB = load_vocabulary(ROOT, "vocab/loan-file.yaml")
RECEIPTS = json.loads((ROOT / "out/pack/receipts.json").read_text("utf-8"))
QUOTE = "three business days after they are delivered or placed in the mail"


def _gate(feel_src, quote=QUOTE, day_set=False):
    return check_feel(feel_src, quote, known_names(VOCAB), set(), "x", numbers_in,
                      day_set=day_set)


def test_numbers_are_one_based():
    assert _gate("derived_business_days[date(item) > date(cd.mailed_date)][3]") == []
    errors = _gate("derived_business_days[date(item) > date(cd.mailed_date)][2]")
    assert any("element 2" in e for e in errors)
    assert any("not allowed" in e for e in _gate("calendar.holidays[-1]"))


def test_durations_count_as_numbers():
    assert _gate('date(cd.mailed_date) + duration("P3D")') == []
    assert any("duration of 4" in e for e in _gate('date(cd.mailed_date) + duration("P4D")'))


def test_names_and_functions():
    assert any("note.limit" in e for e in _gate("date(note.limit) < today()"))
    assert any("not a documented FEEL built-in" in e
               for e in _gate("business_days(closing_date) > 3"))


def test_weekday_name_needs_its_word():
    src = 'day of week(date(item)) != "Sunday"'
    assert any("Sunday" in e for e in _gate(src, day_set=True))
    assert check_feel(src, "except Sundays", known_names(VOCAB), {"Sunday"}, "x", numbers_in,
                      day_set=True) == []


def test_parser_multiword_functions_and_errors():
    assert analyze('list contains(calendar.holidays, "x")').functions == {"list contains"}
    with pytest.raises(ParseError):
        parse("a +")


CELLS = [(rid, key) for rid, r in sorted(RECEIPTS["rules"].items())
         for key in (("expression",) if r["kind"] == "derived_field"
                     else ("applies_when", "requirement"))]


@pytest.mark.parametrize("rid,key", CELLS)
def test_dmn_reads_like_jdm(rid, key):
    """Every FEEL cell of the receipts reads, in the JDM readback's phrases, the same as the
    ZEN expression of the same rule."""
    r = RECEIPTS["rules"][rid]
    assert feel_english(VOCAB)(r["dmn"][key]) == _english(VOCAB)(r[key])
