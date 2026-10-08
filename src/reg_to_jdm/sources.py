"""Source files and their sentences.

A source file holds one paragraph per line: `[label] text`. Lines starting with `#` are notes
about the file. The paragraph label becomes the sentence id: the first sentence of a paragraph
has the label itself, the next ones `label.s2`, `label.s3`. An italic heading at the start of a
paragraph is written `_Heading._`; it is kept as the heading and is not a sentence. Other
`_..._` marks are italics and are dropped from the sentence text.

The sentence splitter is the PoC's (ingest.py) with the Hebrew rules replaced by English ones:
never split after an abbreviation (U.S.C., Jr., e.g.), never inside a section number
(1026.19(f)), never before a lower-case word or a digit. A sentence is a slice of the paragraph
text, never altered.
"""

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

_LINE = re.compile(r"^\[(?P<label>[^\]]+)\]\s+(?P<text>.+)$")
_HEADING = re.compile(r"^_(?P<heading>[^_]+?\.)_\s+")
_ITALIC = re.compile(r"_([^_]+)_")
_ABBREVIATIONS = ("U.S.C.", "U.S.", "Jr.", "Sr.", "e.g.", "i.e.", "No.", "Nos.", "et seq.",
                  "St.", "Inc.", "Co.", "vs.", "cf.")
# A sentence ends at a period or semicolon followed by a space and an upper-case letter or a
# quote mark.
_END = re.compile(r"[.;](?=\s+[\"'“‘(]?[A-Z])")


class SourceError(ValueError):
    pass


@dataclass(frozen=True)
class Sentence:
    id: str
    text: str
    label: str
    heading: str | None
    source: str  # path of the source file, relative to the repo root, forward slashes


@dataclass(frozen=True)
class Source:
    path: str
    sha256: str
    text: str
    sentences: tuple[Sentence, ...]


def _split(text: str) -> list[str]:
    parts, start = [], 0
    for m in _END.finditer(text):
        before = text[start:m.end()]
        if before.rstrip().endswith(_ABBREVIATIONS):
            continue
        parts.append(before.strip())
        start = m.end()
    tail = text[start:].strip()
    if tail:
        parts.append(tail)
    return [p for p in parts if p]


def split_paragraph(label: str, text: str, source: str) -> list[Sentence]:
    heading = None
    m = _HEADING.match(text)
    if m:
        heading = m.group("heading")
        text = text[m.end():]
    text = _ITALIC.sub(r"\1", text)
    out = []
    for n, part in enumerate(_split(text), start=1):
        sid = label if n == 1 else f"{label}.s{n}"
        out.append(Sentence(sid, part, label, heading if n == 1 else None, source))
    return out


def load_source(root: Path, rel: str) -> Source:
    path = root / rel
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    if unicodedata.normalize("NFC", text) != text:
        raise SourceError(f"{rel}: text is not in Unicode NFC form")
    sentences: list[Sentence] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip() or line.startswith("#"):
            continue
        m = _LINE.match(line)
        if not m:
            raise SourceError(f"{rel}:{number}: expected '[label] text'")
        sentences += split_paragraph(m.group("label"), m.group("text"), rel)
    ids = [s.id for s in sentences]
    if len(ids) != len(set(ids)):
        raise SourceError(f"{rel}: duplicate paragraph labels")
    return Source(rel, hashlib.sha256(raw).hexdigest(), text, tuple(sentences))


def load_sources(root: Path, rels: list[str]) -> list[Source]:
    sources = [load_source(root, r) for r in rels]
    seen: set[str] = set()
    for s in sources:
        for sentence in s.sentences:
            if sentence.id in seen:
                raise SourceError(f"sentence id {sentence.id} appears in two source files")
            seen.add(sentence.id)
    return sources


def subsection_key(label: str) -> str:
    """A JSON key for a paragraph label: 1026.19(f)(1)(ii)(A) -> s1026_19_f_1_ii_A."""
    return "s" + re.sub(r"_+", "_", re.sub(r"[^A-Za-z0-9]", "_", label)).strip("_")
