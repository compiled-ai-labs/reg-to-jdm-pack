"""A parser for the part of the ZEN expression language that rules may use.

The engine's own validator (zen.validate_expression) decides whether an expression parses.
This parser exists for what the engine does not report: which fields, functions, methods and
number literals an expression uses (the vocabulary and number gates), and a plain English
rendering of it (readback). Precedence follows the operator table of
https://docs.gorules.io/learn/zen-language/operators.
"""

import re
from dataclasses import dataclass, field

KEYWORDS = {"and", "or", "not", "in", "as", "true", "false", "null"}

_TOKEN = re.compile(r"""
    (?P<ws>\s+)
  | (?P<num>\d+(?:\.\d+)?(?:e[+-]?\d+)?)
  | (?P<str>"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')
  | (?P<tpl>`[^`]*`)
  | (?P<name>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<op>\.\.|\?\?|==|!=|<=|>=|[-+*/%^<>?:,.()\[\]{}\#$=])
""", re.VERBOSE)


class ParseError(ValueError):
    pass


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
        kind = m.lastgroup
        if kind != "ws":
            out.append(Tok(kind, m.group(), pos))
        pos = m.end()
    out.append(Tok("end", "", pos))
    return out


# AST nodes: plain tuples keep the walkers short.
#   ("num", value) ("str", text) ("bool", v) ("null",) ("path", "a.b.c") ("hash", "x.y"|"")
#   ("dollar", "x"|"") ("call", name, args, alias|None) ("method", obj, name, args)
#   ("index", obj, idx) ("unary", op, x) ("bin", op, a, b) ("tern", c, a, b)
#   ("interval", lo_closed, lo, hi, hi_closed) ("array", items) ("object", pairs)
#   ("member", obj, name) ("assign", target, value) ("template", text)


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
        node = self.sequence()
        if self.peek().kind != "end":
            t = self.peek()
            raise ParseError(f"unexpected {t.text!r} at {t.pos}")
        return node

    def sequence(self):
        node = self.assignment()
        if self.peek().text == ";":
            raise ParseError("multiple statements are not allowed in a rule")
        return node

    def assignment(self):
        node = self.ternary()
        if self.peek().text == "=":
            self.take()
            return ("assign", node, self.ternary())
        return node

    def ternary(self):
        cond = self.or_()
        if self.accept("?"):
            a = self.ternary()
            self.expect(":")
            b = self.ternary()
            return ("tern", cond, a, b)
        return cond

    def or_(self):
        node = self.and_()
        while self.accept("or"):
            node = ("bin", "or", node, self.and_())
        return node

    def and_(self):
        node = self.compare()
        while self.accept("and"):
            node = ("bin", "and", node, self.compare())
        return node

    def compare(self):
        node = self.additive()
        while True:
            t = self.peek()
            if t.text in ("==", "!=", "<", ">", "<=", ">=") and t.kind == "op":
                self.take()
                node = ("bin", t.text, node, self.additive())
            elif t.text == "in" and t.kind == "name":
                self.take()
                node = ("bin", "in", node, self.additive())
            elif t.text == "not" and self.peek(1).text == "in":
                self.take(), self.take()
                node = ("bin", "not in", node, self.additive())
            else:
                return node

    def additive(self):
        node = self.not_()
        while self.peek().text in ("+", "-") and self.peek().kind == "op":
            op = self.take().text
            node = ("bin", op, node, self.not_())
        return node

    def not_(self):
        if self.peek().text == "not" and self.peek().kind == "name":
            self.take()
            return ("unary", "not", self.not_())
        return self.multiplicative()

    def multiplicative(self):
        node = self.power()
        while self.peek().text in ("*", "/", "%") and self.peek().kind == "op":
            op = self.take().text
            node = ("bin", op, node, self.power())
        return node

    def power(self):
        node = self.coalesce()
        if self.accept("^"):
            return ("bin", "^", node, self.power())
        return node

    def coalesce(self):
        node = self.unary()
        while self.accept("??"):
            node = ("bin", "??", node, self.unary())
        return node

    def unary(self):
        if self.peek().text in ("-", "+") and self.peek().kind == "op":
            op = self.take().text
            inner = self.unary()
            if op == "-" and inner[0] == "num":
                return ("num", -inner[1])
            return ("unary", op, inner)
        return self.postfix(self.primary())

    def postfix(self, node):
        while True:
            if self.accept("."):
                name = self.take()
                if name.kind != "name":
                    raise ParseError(f"expected a name after '.' at {name.pos}")
                if self.peek().text == "(":
                    node = ("method", node, name.text, self.args()[0])
                elif node[0] == "path":
                    node = ("path", f"{node[1]}.{name.text}")
                elif node[0] in ("hash", "dollar") and node[1] == "":
                    node = (node[0], name.text)
                elif node[0] in ("hash", "dollar"):
                    node = (node[0], f"{node[1]}.{name.text}")
                else:
                    node = ("member", node, name.text)
            elif self.peek().text == "[":
                self.take()
                idx = self.ternary()
                self.expect("]")
                node = ("index", node, idx)
            else:
                return node

    def args(self):
        self.expect("(")
        args, alias = [], None
        if not self.accept(")"):
            while True:
                args.append(self.ternary())
                if self.accept("as"):
                    name = self.take()
                    if name.kind != "name":
                        raise ParseError(f"expected an alias name at {name.pos}")
                    alias = name.text
                if self.accept(")"):
                    break
                self.expect(",")
        return args, alias

    def primary(self):
        t = self.take()
        if t.kind == "num":
            v = float(t.text)
            return ("num", int(v) if v.is_integer() and "e" not in t.text else v)
        if t.kind == "str":
            return ("str", t.text[1:-1])
        if t.kind == "tpl":
            return ("template", t.text)
        if t.kind == "name":
            if t.text in ("true", "false"):
                return ("bool", t.text == "true")
            if t.text == "null":
                return ("null",)
            if t.text in KEYWORDS:
                raise ParseError(f"unexpected keyword {t.text!r} at {t.pos}")
            if self.peek().text == "(":
                args, alias = self.args()
                return ("call", t.text, args, alias)
            return ("path", t.text)
        if t.text == "#":
            return ("hash", "")
        if t.text == "$":
            return ("dollar", "")
        if t.text in ("[", "("):
            if t.text == "(" or self.peek().text != "]":
                first = self.ternary()
            else:
                first = None
            if self.accept(".."):
                hi = self.ternary()
                close = self.take().text
                if close not in ("]", ")"):
                    raise ParseError(f"interval not closed at {t.pos}")
                return ("interval", t.text == "[", first, hi, close == "]")
            if t.text == "(":
                self.expect(")")
                return first
            items = [] if first is None else [first]
            while self.accept(","):
                items.append(self.ternary())
            self.expect("]")
            return ("array", items)
        if t.text == "{":
            pairs = []
            if not self.accept("}"):
                while True:
                    key = self.take()
                    self.expect(":")
                    pairs.append((key.text, self.ternary()))
                    if self.accept("}"):
                        break
                    self.expect(",")
            return ("object", pairs)
        raise ParseError(f"unexpected {t.text or 'end'!r} at {t.pos}")


def parse(src: str):
    return _Parser(src).parse()


# --- analysis -------------------------------------------------------------------------------

@dataclass
class Uses:
    fields: set[str] = field(default_factory=set)
    functions: set[str] = field(default_factory=set)
    methods: set[str] = field(default_factory=set)
    # (value, role): role is "index" for a list position, "weekday" for a number compared with
    # d(...).weekday(), else "plain".
    numbers: list[tuple[float, str]] = field(default_factory=list)
    unsupported: set[str] = field(default_factory=set)
    uses_hash: bool = False


def analyze(src: str) -> Uses:
    uses = Uses()
    _walk(parse(src), uses, frozenset())
    return uses


def _is_weekday(node) -> bool:
    return node[0] == "method" and node[2] == "weekday"


def _walk(node, uses: Uses, aliases: frozenset[str]) -> None:
    kind = node[0]
    if kind == "num":
        uses.numbers.append((node[1], "plain"))
    elif kind == "path":
        root = node[1].split(".")[0]
        if root not in aliases:
            uses.fields.add(node[1])
    elif kind == "hash":
        uses.uses_hash = True
    elif kind == "dollar":
        uses.unsupported.add("$ (value of the tested column)")
    elif kind == "call":
        _, name, args, alias = node
        uses.functions.add(name)
        inner = aliases | {alias} if alias else aliases
        for i, a in enumerate(args):
            _walk(a, uses, inner if i > 0 else aliases)
    elif kind == "method":
        uses.methods.add(node[2])
        _walk(node[1], uses, aliases)
        for a in node[3]:
            _walk(a, uses, aliases)
    elif kind == "index":
        _walk(node[1], uses, aliases)
        if node[2][0] == "num":
            uses.numbers.append((node[2][1], "index"))
        else:
            _walk(node[2], uses, aliases)
    elif kind == "unary":
        _walk(node[2], uses, aliases)
    elif kind == "bin":
        _, op, a, b = node
        for side, other in ((a, b), (b, a)):
            if side[0] == "num" and _is_weekday(other) and op in ("==", "!="):
                uses.numbers.append((side[1], "weekday"))
            else:
                _walk(side, uses, aliases)
    elif kind == "tern":
        for x in node[1:]:
            _walk(x, uses, aliases)
    elif kind == "interval":
        for x in (node[2], node[3]):
            if x is not None:
                _walk(x, uses, aliases)
    elif kind == "array":
        for x in node[1]:
            _walk(x, uses, aliases)
    elif kind == "object":
        uses.unsupported.add("object literal")
    elif kind == "member":
        _walk(node[1], uses, aliases)
    elif kind == "assign":
        uses.unsupported.add("assignment")
    elif kind == "template":
        uses.unsupported.add("template string")


# --- plain English --------------------------------------------------------------------------

_ORDINALS = ["first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth",
             "ninth", "tenth"]
_DATE_CMP = {"<": "is before", "<=": "is on or before", ">": "is after", ">=": "is on or after",
             "==": "is the same day as", "!=": "is not the same day as"}
_NUM_CMP = {"<": "is less than", "<=": "is at most", ">": "is more than", ">=": "is at least",
            "==": "is", "!=": "is not"}
_UNITS = {"d": "days", "day": "days", "days": "days", "w": "weeks", "M": "months", "y": "years"}


class English:
    """Renders an expression as an English phrase. Labels come from the vocabulary."""

    def __init__(self, labels: dict[str, str], enums: dict[str, dict[str, str]],
                 encodings: dict[float, str], hash_label: str = "the day"):
        self.labels = labels
        self.enums = enums
        self.encodings = encodings
        self.hash_label = hash_label

    def __call__(self, src: str) -> str:
        if not src.strip():
            return "always"
        try:
            return self.r(parse(src), {})
        except ParseError:
            return f"`{src}`"

    def r(self, n, aliases: dict[str, str]) -> str:
        k = n[0]
        if k == "num":
            v = n[1]
            return str(int(v)) if float(v).is_integer() else str(v)
        if k == "str":
            return f'"{n[1]}"'
        if k == "bool":
            return "true" if n[1] else "false"
        if k == "null":
            return "nothing"
        if k == "path":
            root, _, rest = n[1].partition(".")
            if root in aliases:
                return aliases[root] + (f" {rest}" if rest else "")
            return self.labels.get(n[1], n[1])
        if k == "hash":
            return self.hash_label
        if k == "call":
            return self.call(n, aliases)
        if k == "method":
            return self.method(n, aliases)
        if k == "index":
            obj, idx = n[1], n[2]
            if idx[0] == "num" and isinstance(idx[1], int):
                pos = idx[1]
                word = (_ORDINALS[pos] if 0 <= pos < len(_ORDINALS)
                        else f"{-pos}th from last" if pos < 0 else f"{pos + 1}th")
                if obj[0] == "call" and obj[1] == "filter":
                    return f"the {word} of {self.filtered(obj, aliases)}"
                return f"the {word} of {self.r(obj, aliases)}"
            return f"{self.r(obj, aliases)} at position {self.r(idx, aliases)}"
        if k == "unary":
            op, x = n[1], n[2]
            if op == "not":
                if x[0] == "call" and x[1] == "contains" and len(x[2]) == 2:
                    return (f"{self.r(x[2][1], aliases)} is not in "
                            f"{self.r(x[2][0], aliases)}")
                return f"it is not the case that {self.r(x, aliases)}"
            return f"{op}{self.r(x, aliases)}"
        if k == "bin":
            return self.binary(n, aliases)
        if k == "tern":
            return (f"if {self.r(n[1], aliases)}: {self.r(n[2], aliases)}; "
                    f"otherwise {self.r(n[3], aliases)}")
        if k == "array":
            return "[" + ", ".join(self.r(x, aliases) for x in n[1]) + "]"
        if k == "interval":
            return f"from {self.r(n[2], aliases)} to {self.r(n[3], aliases)}"
        return "(expression)"

    def filtered(self, n, aliases) -> str:
        _, _, args, alias = n
        inner = dict(aliases)
        if alias:
            inner[alias] = f"the {alias}"
        what = self.r(args[0], aliases).removeprefix("the ")
        return f"{what} where {self.r(args[1], inner)}"

    def call(self, n, aliases) -> str:
        _, name, args, _alias = n
        if name == "d" and len(args) == 1:
            return self.r(args[0], aliases)
        if name == "filter" and len(args) == 2:
            return f"the {self.filtered(n, aliases)}"
        if name == "count" and len(args) == 2:
            return f"the number of {self.filtered(n, aliases)}"
        if name == "contains" and len(args) == 2:
            return f"{self.r(args[0], aliases)} includes {self.r(args[1], aliases)}"
        if name == "len" and len(args) == 1:
            return f"the number of {self.r(args[0], aliases)}"
        return f"{name}(" + ", ".join(self.r(a, aliases) for a in args) + ")"

    def method(self, n, aliases) -> str:
        _, obj, name, args = n
        base = self.r(obj, aliases)
        if name == "weekday":
            return f"the weekday of {base}"
        if name in ("add", "sub") and len(args) == 2 and args[1][0] == "str":
            unit = _UNITS.get(args[1][1], args[1][1])
            word = "plus" if name == "add" else "minus"
            return f"{base} {word} {self.r(args[0], aliases)} {unit}"
        if name == "format":
            return base
        if name == "diff" and len(args) == 2 and args[1][0] == "str":
            return (f"the number of {args[1][1]}s from {self.r(args[0], aliases)} to {base}")
        cmp = {"isBefore": "<", "isAfter": ">", "isSame": "==", "isSameOrBefore": "<=",
               "isSameOrAfter": ">="}
        if name in cmp and args:
            return f"{base} {_DATE_CMP[cmp[name]]} {self.r(args[0], aliases)}"
        return f"{base}.{name}(" + ", ".join(self.r(a, aliases) for a in args) + ")"

    def binary(self, n, aliases) -> str:
        _, op, a, b = n
        if op in ("and", "or"):
            return f"{self.r(a, aliases)} {op} {self.r(b, aliases)}"
        if op in ("==", "!=") and (_is_weekday(a) or _is_weekday(b)):
            day, num = (a, b) if _is_weekday(a) else (b, a)
            if num[0] == "num" and num[1] in self.encodings:
                word = self.encodings[num[1]]
                neg = "not " if op == "!=" else ""
                return f"{self.r(day[1], aliases)} is {neg}a {word}"
        if op in ("==", "!=") and b[0] == "str" and a[0] == "path" and a[1] in self.enums:
            label = self.enums[a[1]].get(b[1], b[1])
            verb = "is" if op == "==" else "is not"
            return f'{self.r(a, aliases)} {verb} "{b[1]}" ({label})'
        if op in _DATE_CMP and (_is_date(a) or _is_date(b)):
            return f"{self.r(a, aliases)} {_DATE_CMP[op]} {self.r(b, aliases)}"
        if op in _NUM_CMP:
            return f"{self.r(a, aliases)} {_NUM_CMP[op]} {self.r(b, aliases)}"
        if op == "??":
            return f"{self.r(a, aliases)}, or if that is missing, {self.r(b, aliases)}"
        if op in ("in", "not in"):
            return f"{self.r(a, aliases)} is {'not ' if op == 'not in' else ''}in " \
                   f"{self.r(b, aliases)}"
        return f"{self.r(a, aliases)} {op} {self.r(b, aliases)}"


def _is_date(n) -> bool:
    if n[0] == "call" and n[1] == "d":
        return True
    if n[0] == "method" and n[2] in ("add", "sub", "startOf", "endOf"):
        return _is_date(n[1])
    return False
