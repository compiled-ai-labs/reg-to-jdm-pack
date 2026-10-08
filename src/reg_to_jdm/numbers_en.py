"""Numbers written in an English sentence, in digits or in words.

The number gate compares every number literal of a rule with these. Adapted from the PoC's
Hebrew reader (numbers_he.py): the same contract, English words instead of Hebrew ones.
"""

import re
from fractions import Fraction

_UNITS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
          "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
          "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
          "eighteen": 18, "nineteen": 19}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
         "eighty": 80, "ninety": 90}
_ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6,
             "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10, "eleventh": 11,
             "twelfth": 12, "fifteenth": 15, "twentieth": 20, "thirtieth": 30}
_SCALES = {"hundred": 100, "thousand": 1000, "million": 1_000_000}
_DIGITS = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?")
_WORD = re.compile(r"[a-z]+")


def _word_value(word: str) -> int | None:
    if word in _UNITS:
        return _UNITS[word]
    if word in _TENS:
        return _TENS[word]
    if word in _ORDINALS:
        return _ORDINALS[word]
    return None


def numbers_in(text: str) -> set[Fraction]:
    """Every number the text states: digit runs, number words, compounds, ordinals."""
    found: set[Fraction] = {Fraction(m.group().replace(",", "")) for m in _DIGITS.finditer(text)}
    lowered = text.lower()
    for compound in re.finditer(r"([a-z]+)-([a-z]+)", lowered):   # twenty-one, thirty-first
        tens, unit = compound.groups()
        if tens in _TENS and (_word_value(unit) or 0) < 10 and _word_value(unit):
            found.add(Fraction(_TENS[tens] + _word_value(unit)))
    words = _WORD.findall(lowered)
    for i, word in enumerate(words):
        value = _word_value(word)
        if value is None:
            continue
        if i + 1 < len(words) and words[i + 1] in _SCALES:
            found.add(Fraction(value * _SCALES[words[i + 1]]))
        found.add(Fraction(value))
    return found


def parse_value(value) -> Fraction:
    return Fraction(str(value))
