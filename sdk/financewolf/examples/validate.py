"""FINANCEWOLF_API_KEY=... python validate.py invoice.xml fwrs_..."""

import json
import os
import sys
from pathlib import Path

from ironfang_financewolf import Financewolf, FinancewolfError

try:
    result = Financewolf(os.environ.get("FINANCEWOLF_API_KEY", "")).validate(
        Path(sys.argv[1]).read_bytes(), ruleset=sys.argv[2]
    )
    # Print only status/identity; the full result may include invoice text.
    print(
        json.dumps(
            {
                "outcome": result["outcome"],
                "ruleset": result["ruleset"]["id"],
                "sha256": result["input"]["sha256"],
            }
        )
    )
    sys.exit(0 if result["outcome"] == "valid" else 1)
except FinancewolfError as error:
    print(error, file=sys.stderr)
    sys.exit(2)

except (OSError, IndexError):
    print("Financewolf: input unavailable", file=sys.stderr)
    sys.exit(2)
