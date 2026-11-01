#!/usr/bin/env python3
"""Optional global discovery for snapshots; no provider configuration."""
from pathlib import Path
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "setup-agent-hands" / "scripts"))
from skill_links import main

if __name__ == "__main__":
    raise SystemExit(main(__file__, []))
