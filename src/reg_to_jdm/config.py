"""config.yaml: where the source text, vocabulary and pack are."""

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Config:
    root: Path
    sources: list[str]
    vocabulary: str
    pack: str


def load_config(path: Path) -> Config:
    data = yaml.safe_load(path.read_text("utf-8")) or {}
    paths = data.get("paths") or {}
    return Config(root=path.resolve().parent, sources=list(paths["sources"]),
                  vocabulary=paths["vocabulary"], pack=paths.get("pack", "out/pack"))
