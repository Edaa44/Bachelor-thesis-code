"""
The implementation is split across:
- ``sas_model.py`` for SAS task data classes,
- ``sas_parser.py`` for SAS parsing/writing,
- ``sas_compile.py`` for the NumericSASCompiler,
- ``main.py`` for the command-line interface.
"""

from __future__ import annotations
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from draft.main import main  # noqa: E402
from draft.sas_compile import NumericSASCompiler, compile_numeric_sas, compile_sas_task  # noqa: E402
from draft.sas_parser import parse_sas, write_sas  # noqa: E402

__all__ = [
    "NumericSASCompiler",
    "compile_numeric_sas",
    "compile_sas_task",
    "main",
    "parse_sas",
    "write_sas",
]

if __name__ == "__main__":
    raise SystemExit(main())
