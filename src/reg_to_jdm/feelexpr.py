"""The part of FEEL that DMN cells may use: a parser, the expression gate, plain English.

The FEEL engine (feel.py, Camunda's feel-scala behind dmn-scala) decides whether an expression
parses. This parser exists for what the engine does not report: which fields, built-in
functions and number literals an expression uses (the vocabulary and number gates), and a
plain English rendering for the readback. It covers the subset the DMN target emits; anything
else is a parse error, never a guess.

Function names are the documented FEEL built-ins, recorded in docs/dmn-target.md from
https://docs.camunda.io/docs/components/modeler/feel/builtin-functions/ (read 2026-10-08).
"""

import re
from dataclasses import dataclass, field
from fractions import Fraction

from .zenexpr import English, ParseError

# Every built-in function the Camunda 8.9 FEEL pages document (one entry per name).
FEEL_FUNCTIONS = frozenset({
    # boolean
    "not", "is defined", "get or else", "assert",
    # string
    "substring", "string length", "upper case", "lower case", "substring before",
    "substring after", "contains", "starts with", "ends with", "matches", "replace", "split",
    "extract", "trim", "uuid", "to base64", "from base64", "is blank", "string join",
    # numeric
    "decimal", "floor", "ceiling", "round up", "round down", "round half up",
    "round half down", "abs", "modulo", "sqrt", "log", "exp", "odd", "even", "random number",
    # list
    "list contains", "count", "min", "max", "sum", "product", "mean", "median", "stddev",
    "mode", "all", "any", "sublist", "append", "concatenate", "insert before", "remove",
    "reverse", "index of", "union", "distinct values", "duplicate values", "flatten", "sort",
    "partition", "is empty",
    # context
    "get value", "get entries", "context put", "context merge", "context",
    # temporal
    "now", "today", "day of week", "day of year", "week of year", "month of year",
    "last day of month",
    # range
    "before", "after", "meets", "met by", "overlaps", "overlaps before", "overlaps after",
    "finishes", "finished by", "includes", "during", "starts", "started by", "coincides",
    # conversion
    "string", "number", "date", "time", "date and time", "duration",
    "years and months duration", "to json", "from json",
})
KEYWORDS = {"if", "then", "else", "for", "in", "return", "and", "or", "true", "false", "null",
            "some", "every", "satisfies", "between", "instance", "of", "function"}
# day of week() returns the English name; zenexpr numbers the days 1 (Monday) to 7 (Sunday).
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
_DURATION = re.compile(r"^P(\d+)([DWMY])$")
_UNIT = {"D": "d", "W": "w", "M": "M", "Y": "y"}

_TOKEN = re.compile(r"""
    (?P<ws>\s+)
  | (?P<num>\d+(?:\.\d+)?)
  | (?P<str>"(?:[^"\\]|\\.)*")
  | (?P<name>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<op>\.\.|\*\*|<=|>=|!=|[-+*/<>=(),.\[\]{}:])
""", re.VERBOSE)


@dataclass(frozen=True)
class Tok:
    kind: str
    text: str
    pos: int


def tokenize(src: str) -> list[Tok]:
    out, pos = [], 0
    while pos < len(src):
        m = _TOKEN.match(src, pos)
        if not m:
            raise ParseError(f"unexpected character {src[pos]!r} at {pos}")
        if m.lastgroup != "ws":
            out.append(Tok(m.lastgroup, m.group(), pos))
        pos = m.end()
    out.append(Tok("end", "", pos))
    return out


_MULTIWORD = sorted((f.split() for f in FEEL_FUNCTIONS if " " in f), key=len, reverse=True)

# AST: ("num", v) ("str", s) ("bool", b) ("null",) ("name", "a.b") ("call", fname, args)
#   ("filter", list, pred) ("index", list, n) ("member", obj, name) ("unary", "-", x)
#   ("bin", op, a, b) ("if", c, a, b) ("for", var, lo, hi, body) ("list", items)
#   ("range", lo_closed, lo, hi, hi_closed) ("context", [(key, value)]) ("dash",)


class _Parser:
    def __init__(self, src: str):
        self.toks = tokenize(src)
        self.i = 0

    def peek(self, k: int = 0) -> Tok:
        return self.toks[min(self.i + k, len(self.toks) - 1)]

    def take(self) -> Tok:
        t = self.toks[self.i]
        self.i += 1
        return t

    def accept(self, text: str) -> bool:
        t = self.peek()
        if t.text == text and t.kind in ("op", "name"):
            self.i += 1
            return True
        return False

    def expect(self, text: str) -> None:
        if not self.accept(text):
            t = self.peek()
            raise ParseError(f"expected {text!r} at {t.pos}, found {t.text or 'end'!r}")

    def parse(self):
        node = self.expr()
        if self.peek().kind != "end":
            t = self.peek()
            raise ParseError(f"unexpected {t.text!r} at {t.pos}")
        return node

    def expr(self):
        if self.accept("if"):
            c = self.expr()
            self.expect("then")
            a = self.expr()
            self.expect("else")
            return ("if", c, a, self.expr())
        if self.accept("for"):
            var = self.take()
            if var.kind != "name" or var.text in KEYWORDS:
                raise ParseError(f"expected a loop variable at {var.pos}")
            self.expect("in")
            lo = self.additive()
            self.expect("..")
            hi = self.additive()
            self.expect("return")
            return ("for", var.text, lo, hi, self.expr())
        return self.disjunction()

    def disjunction(self):
        node = self.conjunction()
        while self.accept("or"):
            node = ("bin", "or", node, self.conjunction())
        return node

    def conjunction(self):
        node = self.comparison()
        while self.accept("and"):
            node = ("bin", "and", node, self.comparison())
        return node

    def comparison(self):
        node = self.additive()
        t = self.peek()
        if t.kind == "op" and t.text in ("=", "!=", "<", ">", "<=", ">="):
            self.take()
            return ("bin", t.text, node, self.additive())
        return node

    def additive(self):
        node = self.multiplicative()
        while self.peek().kind == "op" and self.peek().text in ("+", "-"):
            op = self.take().text
            node = ("bin", op, node, self.multiplicative())
        return node

    def multiplicative(self):
        node = self.power()
        while self.peek().kind == "op" and self.peek().text in ("*", "/"):
            op = self.take().text
            node = ("bin", op, node, self.power())
        return node

    def power(self):
        node = self.unary()
        if self.accept("**"):
            return ("bin", "**", node, self.unary())
        return node

    def unary(self):
        if self.peek().kind == "op" and self.peek().text == "-":
            self.take()
            inner = self.unary()
            return ("num", -inner[1]) if inner[0] == "num" else ("unary", "-", inner)
        return self.postfix(self.primary())

    def postfix(self, node):
        while True:
            if self.peek().text == "." and self.peek().kind == "op":
                self.take()
                name = self.take()
                if name.kind != "name":
                    raise ParseError(f"expected a name after '.' at {name.pos}")
                node = ("name", f"{node[1]}.{name.text}") if node[0] == "name" \
                    else ("member", node, name.text)
            elif self.peek().text == "[" and self.peek().kind == "op":
                self.take()
                inner = self.expr()
                self.expect("]")
                node = ("index", node, inner[1]) if inner[0] == "num" \
                    else ("filter", node, inner)
            else:
                return node

    def function_name(self) -> str | None:
        """The longest documented multi-word function name starting here, if a '(' follows."""
        for words in _MULTIWORD:
            n = len(words)
            if all(self.peek(k).kind == "name" and self.peek(k).text == w
                   for k, w in enumerate(words)) and self.peek(n).text == "(":
                self.i += n
                return " ".join(words)
        t = self.peek()
        if t.kind == "name" and self.peek(1).text == "(" and t.text not in KEYWORDS - {"not"}:
            self.i += 1
            return t.text
        return None

    def primary(self):
        name = self.function_name()
        if name is not None:
            self.expect("(")
            args = []
            if not self.accept(")"):
                while True:
                    args.append(self.expr())
                    if self.accept(")"):
                        break
                    self.expect(",")
            return ("call", name, args)
        t = self.take()
        if t.kind == "num":
            v = float(t.text)
            return ("num", int(v) if v.is_integer() and "." not in t.text else v)
        if t.kind == "str":
            return ("str", t.text[1:-1].replace('\\"', '"').replace("\\\\", "\\"))
        if t.kind == "name":
            if t.text in ("true", "false"):
                return ("bool", t.text == "true")
            if t.text == "null":
                return ("null",)
            if t.text in KEYWORDS:
                raise ParseError(f"unexpected keyword {t.text!r} at {t.pos}")
            return ("name", t.text)
        if t.text == "-" and self.peek().kind == "end":
            return ("dash",)
        if t.text == "(":
            first = self.expr()
            if self.accept(".."):
                hi = self.expr()
                close = self.take().text
                if close not in ("]", ")"):
                    raise ParseError(f"range not closed at {t.pos}")
                return ("range", False, first, hi, close == "]")
            self.expect(")")
            return first
        if t.text == "[":
            if self.accept("]"):
                return ("list", [])
            first = self.expr()
            if self.accept(".."):
                hi = self.expr()
                close = self.take().text
                if close not in ("]", ")"):
                    raise ParseError(f"range not closed at {t.pos}")
                return ("range", True, first, hi, close == "]")
            items = [first]
            while self.accept(","):
                items.append(self.expr())
            self.expect("]")
            return ("list", items)
        if t.text == "{":
            pairs = []
            if not self.accept("}"):
                while True:
                    key = self.take()
                    if key.kind not in ("name", "str"):
                        raise ParseError(f"expected a context key at {key.pos}")
                    self.expect(":")
                    pairs.append((key.text.strip('"'), self.expr()))
                    if self.accept("}"):
                        break
                    self.expect(",")
            return ("context", pairs)
        raise ParseError(f"unexpected {t.text or 'end'!r} at {t.pos}")


def parse(src: str):
    return _Parser(src).parse()


# --- analysis -------------------------------------------------------------------------------

@dataclass
class Uses:
    names: set[str] = field(default_factory=set)
    functions: set[str] = field(default_factory=set)
    # (value, role): "index" for a list position (1-based in FEEL), "duration" for the count
    # of a duration literal, else "plain".
    numbers: list[tuple[float, str]] = field(default_factory=list)
    weekdays: set[str] = field(default_factory=set)
    unsupported: set[str] = field(default_factory=set)
    uses_item: bool = False


def analyze(src: str, day_test: bool = False) -> Uses:
    """`day_test`: the test of one day of a day set, which code puts inside a filter, so
    `item` is the day."""
    uses = Uses()
    _walk(parse(src), uses, frozenset(), day_test)
    return uses


def _is_day_of_week(n) -> bool:
    return n[0] == "call" and n[1] == "day of week"


def _walk(n, uses: Uses, bound: frozenset[str], in_filter: bool = False) -> None:
    k = n[0]
    if k == "num":
        uses.numbers.append((n[1], "plain"))
    elif k == "name":
        root = n[1].split(".")[0]
        if root == "item" and in_filter:
            uses.uses_item = True
        elif root not in bound:
            uses.names.add(n[1])
    elif k == "call":
        uses.functions.add(n[1])
        if n[1] == "duration" and len(n[2]) == 1 and n[2][0][0] == "str":
            m = _DURATION.match(n[2][0][1])
            if not m:
                uses.unsupported.add(f"duration literal {n[2][0][1]!r}")
            else:
                uses.numbers.append((int(m.group(1)), "duration"))
            return
        for a in n[2]:
            _walk(a, uses, bound, in_filter)
    elif k == "filter":
        _walk(n[1], uses, bound, in_filter)
        _walk(n[2], uses, bound, True)
    elif k == "index":
        _walk(n[1], uses, bound, in_filter)
        uses.numbers.append((n[2], "index"))
    elif k == "member":
        _walk(n[1], uses, bound, in_filter)
    elif k == "unary":
        _walk(n[2], uses, bound, in_filter)
    elif k == "bin":
        _, op, a, b = n
        for side, other in ((a, b), (b, a)):
            if side[0] == "str" and _is_day_of_week(other) and op in ("=", "!="):
                if side[1] not in WEEKDAYS:
                    uses.unsupported.add(f"day name {side[1]!r}")
                uses.weekdays.add(side[1])
            else:
                _walk(side, uses, bound, in_filter)
    elif k == "if":
        for x in n[1:]:
            _walk(x, uses, bound, in_filter)
    elif k == "for":
        _walk(n[2], uses, bound, in_filter)
        _walk(n[3], uses, bound, in_filter)
        _walk(n[4], uses, bound | {n[1]}, in_filter)
    elif k == "list":
        for x in n[1]:
            _walk(x, uses, bound, in_filter)
    elif k == "range":
        _walk(n[2], uses, bound, in_filter)
        _walk(n[3], uses, bound, in_filter)
    elif k == "context":
        uses.unsupported.add("context literal")


# --- plain English, through the phrases of the JDM readback ---------------------------------

def lower(n, names: dict[str, str]):
    """The FEEL AST as the zenexpr AST that reads the same, so both targets share one set of
    phrases. `names` maps FEEL names that differ from the vocabulary path (derived fields).
    A FEEL construct with no reading raises ParseError."""
    k = n[0]
    if k in ("num", "str", "bool", "null"):
        return n
    if k == "dash":
        return ("bool", True)
    if k == "name":
        root, _, rest = n[1].partition(".")
        if root == "item":
            return ("hash", rest)
        return ("path", names.get(n[1], n[1]))
    if k == "call":
        name, args = n[1], n[2]
        if name == "date" and len(args) == 1:
            return ("call", "d", [lower(args[0], names)], None)
        if name == "count" and len(args) == 1 and args[0][0] == "filter":
            f = args[0]
            return ("call", "count", [lower(f[1], names), lower(f[2], names)], None)
        if name == "count" and len(args) == 1:
            return ("call", "len", [lower(args[0], names)], None)
        if name == "list contains" and len(args) == 2:
            return ("call", "contains", [lower(a, names) for a in args], None)
        if name == "not" and len(args) == 1:
            return ("unary", "not", lower(args[0], names))
        if name == "day of week" and len(args) == 1:
            return ("method", lower(args[0], names), "weekday", [])
        if name == "string" and len(args) == 1:
            return ("method", lower(args[0], names), "format", [("str", "%Y-%m-%d")])
        raise ParseError(f"no reading for {name}()")
    if k == "filter":
        return ("call", "filter", [lower(n[1], names), lower(n[2], names)], None)
    if k == "index":
        if not isinstance(n[2], int) or n[2] < 1:
            raise ParseError(f"no reading for index {n[2]}")
        return ("index", lower(n[1], names), ("num", n[2] - 1))
    if k == "member" and n[2] == "days" and n[1][0] == "bin" and n[1][1] == "-":
        return ("method", lower(n[1][2], names), "diff",
                [lower(n[1][3], names), ("str", "day")])
    if k == "unary":
        return ("unary", "-", lower(n[2], names))
    if k == "bin":
        _, op, a, b = n
        if op in ("+", "-") and b[0] == "call" and b[1] == "duration" and b[2] \
                and b[2][0][0] == "str" and _DURATION.match(b[2][0][1]):
            m = _DURATION.match(b[2][0][1])
            return ("method", lower(a, names), "add" if op == "+" else "sub",
                    [("num", int(m.group(1))), ("str", _UNIT[m.group(2)])])
        if op in ("=", "!=") and (_is_day_of_week(a) or _is_day_of_week(b)):
            day, name = (a, b) if _is_day_of_week(a) else (b, a)
            if name[0] == "str" and name[1] in WEEKDAYS:
                return ("bin", "==" if op == "=" else "!=", lower(day, names),
                        ("num", WEEKDAYS.index(name[1]) + 1))
        zop = {"=": "==", "**": "^"}.get(op, op)
        return ("bin", zop, lower(a, names), lower(b, names))
    if k == "if":
        return ("tern", *(lower(x, names) for x in n[1:]))
    if k == "list":
        return ("array", [lower(x, names) for x in n[1]])
    if k == "range":
        return ("interval", n[1], lower(n[2], names), lower(n[3], names), n[4])
    raise ParseError(f"no reading for {k}")


class FeelEnglish:
    """Renders a FEEL cell in the words of the JDM readback (zenexpr.English)."""

    def __init__(self, english: English, names: dict[str, str]):
        self.english = english
        self.names = names

    def __call__(self, src: str) -> str:
        if not src.strip() or src.strip() == "-":
            return "always"
        try:
            return self.english.r(lower(parse(src), self.names), {})
        except ParseError:
            return f"`{src}`"


# --- the gate -------------------------------------------------------------------------------

def check_feel(expr: str, quote: str, known_names: set[str], weekday_words: set[str],
               where: str, numbers_in, day_set: bool = False,
               allow_dash: bool = False) -> list[str]:
    """FEEL syntax (this parser), documented built-ins only, known names only, every number
    stated in the quote. `known_names`: vocabulary fields and the FEEL names of derived fields.
    `weekday_words`: day names whose encoding word is in the quote."""
    if not isinstance(expr, str) or not expr.strip():
        return [f"{where}: empty FEEL expression"]
    if allow_dash and expr.strip() == "-":
        return []
    try:
        uses = analyze(expr, day_test=day_set)
    except ParseError as exc:
        return [f"{where}: {exc} in FEEL {expr!r}"]
    errors = [f"{where}: {u} is not allowed in FEEL" for u in sorted(uses.unsupported)]
    for f in sorted(uses.functions - FEEL_FUNCTIONS):
        errors.append(f"{where}: {f}() is not a documented FEEL built-in function")
    for name in sorted(uses.names):
        if name not in known_names:
            errors.append(f"{where}: {name} is not a field or derived field of the vocabulary")
    if day_set and not uses.uses_item:
        errors.append(f"{where}: the test of a day must use item for the day")
    for day in sorted(uses.weekdays - weekday_words):
        errors.append(f"{where}: day name {day!r} needs an encoding whose word is in the quote")
    stated = numbers_in(quote)
    for value, role in uses.numbers:
        if role == "index" and value < 1:
            errors.append(f"{where}: list index [{value:g}] is not allowed (FEEL counts from 1; "
                          f"negative counts from the end)")
            continue
        shown = {"index": f"index [{value:g}] (element {value:g})",
                 "duration": f"duration of {value:g}"}.get(role, f"number {value:g}")
        if Fraction(str(value)) not in stated:
            errors.append(f"{where}: {shown} is not stated in the quote {quote!r}")
    return errors
