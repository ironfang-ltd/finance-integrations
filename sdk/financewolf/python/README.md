# Financewolf Python client and CLI

Review candidate **0.1.0**, Python 3.10+, no runtime dependencies. This package
calls the Financewolf HTTPS API; PHIVE and registered artefacts determine the
validation outcome. It performs no local invoice/business-rule validation.

Install the reviewed wheel, or from this checkout:

```sh
python3 -m pip install ./sdk/financewolf/python
```

Provide a Financewolf key with `financewolf:einvoices:write` using your secret
manager or `FINANCEWOLF_API_KEY`. Never commit a key or pass it as a CLI argument.

```python
import os
from pathlib import Path
from ironfang_financewolf import Financewolf, FinancewolfError

client = Financewolf(os.environ["FINANCEWOLF_API_KEY"])
result = client.validate(
    Path("invoice.xml").read_bytes(),
    ruleset="fwrs_bis3_billing_invoice_2026_5_r3",
)
print(result["outcome"])
```

`validate` takes bytes and returns the structured result for `valid` or `invalid`.
Client, HTTP, transport and indeterminate/malformed response failures raise
`FinancewolfError`, with a safe `code` and optional HTTP `status`. It verifies
response hash, length, completed layers and the selected immutable ruleset.
It never changes the document. `latest` defaults to the active detected ruleset;
pin a type-specific ID for reproducible CI. A ruleset's lifecycle may later
prevent new validations, in which case the API error is retained as a failure.

## CLI

```sh
financewolf validate 'invoices/**/*.xml' --ruleset fwrs_bis3_billing_invoice_2026_5_r3 --output invoice-results.json
financewolf validate credit-notes --ruleset fwrs_bis3_billing_creditnote_2026_5_r3 --output credit-results.json
# Equivalent: python3 -m ironfang_financewolf validate ...
```

The CLI requires an explicit `--ruleset` (immutable ID or `latest`) and a new
`--output` path. Individual files, directories and quoted recursive globs work;
duplicates are submitted once, unmatched patterns and paths/symlinks outside
`--workspace` (default current directory) fail. Directories select `*.xml`.
Reports are mode 0600 on POSIX. Existing paths, including symlinks, are refused
before a request; the CLI never overwrites an input or prior report.

Exit codes are **0** all valid, **1** at least one invalid and no service error,
**2** configuration, input, HTTP, transport or response-integrity failure. Errors
take precedence in a mixed run. Once input/output setup succeeds, the JSON report
is written for both valid and failed validations. Setup failures print only a
safe diagnostic. Human output contains counts, never finding messages.

Every document is sent exactly once per run, at most 5 MiB, with a default
30-second HTTP timeout and a 4 MiB response limit. Redirects are refused. There
are no automatic retries or idempotency keys: a new run/call may be a new billable
operation, even if an earlier response was lost. A timeout does not cancel work
already accepted by the API. Do not retry automatically on 429/5xx without
accounting for that behaviour.

The report schema remains `financewolf/action-results/v1`, shared with the
GitHub Action: totals, valid/invalid/error counts and per-file results. Full
results can contain invoice text; review storage, access and retention. XML is
sent to Financewolf under the authenticated API retention policy. Validation
neither transmits through Peppol nor certifies tax/legal compliance or recipient
acceptance. Public PyPI publication is not claimed by this review candidate.
