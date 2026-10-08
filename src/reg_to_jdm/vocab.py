"""The closed vocabulary: fields, derived fields, functions, methods, encodings."""

import hashlib
from dataclasses import dataclass
from pathlib import Path

import yaml

FIELD_TYPES = {"date", "enum", "boolean", "number", "string", "date_list"}
DERIVED_TYPES = {"date", "day_set", "number", "boolean"}


class VocabularyError(ValueError):
    pass


@dataclass(frozen=True)
class Field:
    id: str
    type: str
    label: str
    values: dict[str, str] | None = None


@dataclass(frozen=True)
class Derived:
    id: str
    type: str
    label: str
    window: dict | None = None


@dataclass(frozen=True)
class Vocabulary:
    path: str
    sha256: str
    fields: dict[str, Field]
    derived: dict[str, Derived]
    functions: frozenset[str]
    methods: frozenset[str]
    encodings: dict[float, dict]

    def labels(self) -> dict[str, str]:
        """Labels as noun phrases for the readback: "the" is added unless the label is a
        statement or a question already ("the transaction is ...", "how ...")."""
        def phrase(label: str) -> str:
            return label if label.startswith(("the ", "how ")) else f"the {label}"
        out = {f.id: phrase(f.label) for f in self.fields.values()}
        out.update({d.id: phrase(d.label) for d in self.derived.values()})
        return out

    def enums(self) -> dict[str, dict[str, str]]:
        return {f.id: f.values for f in self.fields.values() if f.values}

    def known(self, name: str) -> bool:
        return name in self.fields or name in self.derived


def load_vocabulary(root: Path, rel: str) -> Vocabulary:
    raw = (root / rel).read_bytes()
    data = yaml.safe_load(raw) or {}
    fields, derived = {}, {}
    for fid, spec in (data.get("fields") or {}).items():
        if spec.get("type") not in FIELD_TYPES:
            raise VocabularyError(f"{fid}: type must be one of {sorted(FIELD_TYPES)}")
        if spec["type"] == "enum" and not spec.get("values"):
            raise VocabularyError(f"{fid}: an enum needs values")
        fields[fid] = Field(fid, spec["type"], spec["label"], spec.get("values"))
    for did, spec in (data.get("derived") or {}).items():
        if spec.get("type") not in DERIVED_TYPES:
            raise VocabularyError(f"{did}: type must be one of {sorted(DERIVED_TYPES)}")
        window = spec.get("window")
        if spec["type"] == "day_set":
            if not window or not {"from", "to", "pad_days"} <= set(window):
                raise VocabularyError(f"{did}: a day_set needs window.from, .to, .pad_days")
            for end in ("from", "to"):
                if window[end] not in fields or fields[window[end]].type != "date":
                    raise VocabularyError(f"{did}: window.{end} must be a date field")
        derived[did] = Derived(did, spec["type"], spec["label"], window)
    encodings = {}
    for e in data.get("encodings") or []:
        encodings[float(e["value"])] = {"word": e["word"], "means": e["means"]}
    return Vocabulary(rel, hashlib.sha256(raw).hexdigest(), fields, derived,
                      frozenset(data.get("functions") or []),
                      frozenset(data.get("methods") or []), encodings)
