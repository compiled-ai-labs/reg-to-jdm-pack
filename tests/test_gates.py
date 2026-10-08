"""Pack gates on expressions: each defect is caught and named."""

from pathlib import Path

import pytest

from reg_to_jdm.validator import check_expression, check_vocabulary
from reg_to_jdm.vocab import load_vocabulary

ROOT = Path(__file__).resolve().parents[1]
QUOTE = "no later than three business days before consummation"


@pytest.fixture(scope="module")
def vocab():
    return load_vocabulary(ROOT, "vocab/loan-file.yaml")


def test_vocabulary_lists_only_documented_functions(vocab):
    assert check_vocabulary(vocab) == []


def test_good_expression_passes(vocab):
    expr = ("count(derived.business_days as day, d(day) >= d(derived.cd_receipt_date) "
            "and d(day) < d(closing_date)) >= 3")
    assert check_expression(expr, QUOTE, vocab, "rule") == []


@pytest.mark.parametrize("expr,expect", [
    ("count(derived.business_days, true) >= 4", "number 4 is not stated"),
    ("d(cd.closing) >= d(closing_date)", "not a field"),
    ("len(derived.business_days) >= 3 and upper('a') == 'A'",
     "function upper is not in the vocabulary"),
    ("filter(derived.business_days, true)[-3] != null", "negative list index"),
    ("filter(derived.business_days, true)[3] != null", "index [3] (element 4) is not stated"),
    ("d(closing_date).weekday() != 7", "needs an encoding"),
    ("closing_date >=", "ZEN parser rejects"),
    ("a = 1", "assignment is not allowed"),
])
def test_gate_failures(vocab, expr, expect):
    failures = check_expression(expr, QUOTE, vocab, "rule")
    assert any(expect in f for f in failures), failures


def test_encoding_allowed_when_its_word_is_in_the_quote(vocab):
    assert check_expression("d(#).weekday() != 7", "all calendar days except Sundays", vocab,
                            "derived", day_set=True) == []
