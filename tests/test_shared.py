"""The rules are one file in two places: the tools' copy and the verifier's copy must be the same bytes."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_the_tools_and_the_verifier_share_the_rules_byte_for_byte() -> None:
    assert (ROOT / "src" / "plugin" / "rules.py").read_bytes() == (ROOT / "verifier" / "rules.py").read_bytes()
