"""The committed example pack is final and passes every gate."""

from pathlib import Path

from reg_to_jdm.cli import main

ROOT = Path(__file__).resolve().parents[1]
CONFIG = str(ROOT / "config.yaml")


def test_committed_pack_verifies_final():
    assert main(["--config", CONFIG, "verify", "--final"]) == 0


def test_committed_pack_verifies_final_in_both_targets(feel_runner):
    assert main(["--config", CONFIG, "verify", "--final", "--target", "all"]) == 0


def test_readback_reproduces_committed_file(tmp_path):
    import shutil
    pack = tmp_path / "pack"
    shutil.copytree(ROOT / "out/pack", pack)
    (pack / "readback.md").unlink()
    assert main(["--config", CONFIG, "readback", "--pack", str(pack)]) == 0
    assert (pack / "readback.md").read_bytes() == (ROOT / "out/pack/readback.md").read_bytes()
