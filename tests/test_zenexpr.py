import pytest

from reg_to_jdm.numbers_en import numbers_in
from reg_to_jdm.zenexpr import English, ParseError, analyze, parse


def test_analyze_fields_functions_numbers():
    uses = analyze('count(derived.business_days as day, d(day) >= d(cd.received_date)) >= 3')
    assert uses.fields == {"derived.business_days", "cd.received_date"}
    assert uses.functions == {"count", "d"}
    assert uses.numbers == [(3, "plain")]


def test_index_and_weekday_roles():
    uses = analyze('filter(x as day, d(day).weekday() != 7)[2]')
    assert (2, "index") in uses.numbers
    assert (7, "weekday") in uses.numbers
    assert uses.methods == {"weekday"}


def test_alias_is_not_a_field():
    assert analyze("filter(items as day, day.ok)").fields == {"items"}


def test_assignment_is_flagged():
    assert "assignment" in analyze("a = 1").unsupported


def test_parse_errors():
    with pytest.raises(ParseError):
        parse("a +")
    with pytest.raises(ParseError):
        parse("a = 1; b = 2")


def test_english():
    en = English({"closing_date": "the date of consummation", "x.y": "the receipt date"},
                 {"m": {"in_person": "in person"}}, {7: "Sunday"})
    assert en("d(x.y) <= d(closing_date)") == \
        "the receipt date is on or before the date of consummation"
    assert en("d(#).weekday() != 7") == "the day is not a Sunday"
    assert en('m == "in_person"') == 'm is "in_person" (in person)'
    assert en("") == "always"


def test_numbers_in_words_digits_ordinals():
    found = numbers_in("no later than three business days, the third day, 1,500 and twenty-one")
    assert {3, 1500, 21} <= found
