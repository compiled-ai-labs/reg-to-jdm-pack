"""reg-to-jdm: verify a compiled GoRules JDM and Camunda DMN rule pack and render its readback.

    reg-to-jdm verify [--final] [--target jdm|dmn|all]
    reg-to-jdm readback
"""

import argparse
import json
import sys
from pathlib import Path

from .config import load_config
from .readback import render
from .sources import load_sources
from .verify import verify_pack
from .vocab import load_vocabulary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="reg-to-jdm", description=__doc__.splitlines()[0])
    parser.add_argument("--config", default="config.yaml")
    sub = parser.add_subparsers(dest="command", required=True)
    v = sub.add_parser("verify", help="run the pack gates on the pack")
    v.add_argument("--final", action="store_true", help="also fail when questions are open")
    v.add_argument("--target", choices=("jdm", "dmn", "all"), default="jdm",
                   help="which decision model to run the tests in (default: jdm)")
    r = sub.add_parser("readback", help="write readback.md from the pack")
    for p in (v, r):
        p.add_argument("--pack", help="pack folder (default: paths.pack of the config)")
    args = parser.parse_args(argv)

    cfg = load_config(Path(args.config))
    pack = Path(args.pack) if args.pack else cfg.root / cfg.pack
    if args.command == "verify":
        return verify_pack(cfg, pack, args.final, target=args.target)
    model = json.loads((pack / "rules.jdm.json").read_text("utf-8"))
    dmn_xml = (pack / "rules.dmn").read_text("utf-8")
    receipts = json.loads((pack / "receipts.json").read_text("utf-8"))
    text = render(model, dmn_xml, receipts, load_sources(cfg.root, cfg.sources),
                  load_vocabulary(cfg.root, cfg.vocabulary))
    path = pack / "readback.md"
    path.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
