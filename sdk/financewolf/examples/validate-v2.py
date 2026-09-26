"""FINANCEWOLF_API_KEY=... python validate-v2.py invoice.pdf [family]

An invoice XML, or a ZUGFeRD / Factur-X PDF, through V2.
"""

import json
import os
import sys
from pathlib import Path

from ironfang_financewolf import Financewolf, FinancewolfError

try:
    options = {"family": sys.argv[2]} if len(sys.argv) > 2 else {}
    result = Financewolf(os.environ.get("FINANCEWOLF_API_KEY", "")).validate_v2(
        Path(sys.argv[1]).read_bytes(), **options
    )
    # Print only status, identity and check groups; findings may quote the invoice.
    print(
        json.dumps(
            {
                "outcome": result["outcome"],
                "ruleset": result["ruleset"]["id"],
                "scope": result["ruleset"]["scope"],
                "sha256": result["input"]["sha256"],
                "groups": {g["group"]: g["status"] for g in result["groups"]},
            }
        )
    )
    sys.exit(0 if result["outcome"] == "valid" else 1)
except FinancewolfError as error:
    print(error, file=sys.stderr)
    sys.exit(2)
except (OSError, IndexError):
    print("Ironfang Finance: input unavailable", file=sys.stderr)
    sys.exit(2)
