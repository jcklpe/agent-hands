#!/usr/bin/env python3
"""Compatibility entry for the shared, provider-neutral agenda renderer."""
import os
import runpy
from pathlib import Path

os.environ["AGENDA_NO_DESCRIPTION"] = os.environ.get("GOOGLE_CALENDAR_NO_DESCRIPTION", "")
_target = Path(__file__).resolve().parents[2] / "render-calendar-agenda/scripts/events.py"
if __name__ == "__main__":
    runpy.run_path(str(_target), run_name="__main__")
else:
    globals().update(runpy.run_path(str(_target)))
