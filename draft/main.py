from __future__ import annotations

import sys
from typing import Sequence

from .sas_compile import NumericSASCompiler


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "--sas":
        args = args[1:]

    if len(args) != 2:
        print(
            "Usage: python draft/compile.py [--sas] <numeric.sas> <classical.sas>"
        )
        return 1

    NumericSASCompiler().compile_file(args[0], args[1])
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
