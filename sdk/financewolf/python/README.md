# Ironfang Finance Python client and CLI

Review candidate **0.2.0**, Python 3.10+, no runtime dependencies. This package
calls the Ironfang Finance HTTPS API; PHIVE and registered artefacts determine
the validation outcome. It performs no local invoice/business-rule validation.

The package keeps the names it launched under: `ironfang-financewolf`, the
`Financewolf` class, the `financewolf` command and `FINANCEWOLF_API_KEY`. The
product is Ironfang Finance; nothing else about the package changed.

Install the reviewed wheel, or from this checkout:

```sh
python3 -m pip install ./sdk/financewolf/python
```

Provide an Ironfang key with `finance:einvoices:write` using your secret
manager or `FINANCEWOLF_API_KEY`. Never commit a key or pass it as a CLI argument.

```python
import os
from pathlib import Path
from ironfang_financewolf import Financewolf, FinancewolfError

client = Financewolf(os.environ["FINANCEWOLF_API_KEY"])
result = client.validate(
    Path("invoice.xml").read_bytes(),
    ruleset="fwrs_bis3_billing_invoice_2026_5_r5",
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

## V2: XRechnung and ZUGFeRD / Factur-X, XML or PDF

The `*_v2` methods use the V2 API, which validates Peppol BIS Billing 3,
XRechnung 3.0.2 (UBL or CII) and ZUGFeRD 2.5.2 / Factur-X 1.09.2 in its five
profiles, as XML or as a PDF with its embedded invoice XML. V1 methods are
unchanged.

```python
pdf = Path("invoice.pdf").read_bytes()
result = client.validate_v2(pdf)  # family, variant and scope detected
print(result["outcome"], result["ruleset"]["id"])
for group in result["groups"]:  # pdfa, attachment_metadata, invoice_xml
    print(group["group"], group["status"])
for finding in result["findings"]:
    print(finding["rule_id"], finding["location"])  # kind: xpath, line-column, pdf or none
```

- `validate_v2(document, *, media_type=None, ruleset="latest", family=None,
  variant=None, document_type=None, scope=None, idempotency_key=None)` sends
  the exact bytes once. A PDF is recognised from its header (or pass
  `media_type`). XML is at most 5 MiB, a PDF 20 MiB. Left at its default, the
  timeout is 45 seconds for a PDF (the server's hybrid deadline is 30).
- The verdict is checked like V1's: hash, length and media type of the bytes
  sent, the scope they imply (`xml` or `hybrid_pdf`), the selection asked
  for, both engines for a PDF, and layers consistent with the outcome.
  `coverage.not_checked` states what a verdict does not establish, such as
  the visible PDF matching its XML.
- A refusal or indeterminate answer raises `FinancewolfError` with
  `problem` set to the API's code (for example `family_mismatch`,
  `no_embedded_invoice` or `validation_timeout`) and `request_id` for
  support. The problem's other text is never kept.
- `idempotency_key` (8-128 of `A-Z a-z 0-9 _ -`) makes a retry after a lost
  response return the first result instead of a second operation.

Reads and durable work, all V1 and V2 together where the API lists both:
`rulesets_v2`, `results_v2`, `result_v2`, `delete_result_v2`;
`submit_job_v2`, `job_v2`, `jobs_v2`, `cancel_job_v2`, `wait_for_job_v2`;
`submit_batch_v2` (a list of up to 100 dicts: `document` bytes, plus any of
`media_type`, `ruleset`, `family`, `variant`, `document_type`, `scope`), `batch_v2`,
`batches_v2`, `cancel_batch_v2`; `deliveries_v2`, `delivery_v2`,
`retry_delivery_v2` (the retry needs `finance:einvoices:destinations:manage`).
Reads need `finance:einvoices:read`.

```python
job = client.submit_job_v2(pdf, idempotency_key="invoice-2026-0042")
job = client.wait_for_job_v2(job["id"], timeout=300)
verdict = client.result_v2(job["operation_id"])
```

## CLI

```sh
financewolf validate 'invoices/**/*.xml' --ruleset fwrs_bis3_billing_invoice_2026_5_r5 --output invoice-results.json
financewolf validate credit-notes --ruleset fwrs_bis3_billing_creditnote_2026_5_r5 --output credit-results.json
financewolf validate e-invoices --api v2 --ruleset latest --output e-invoice-results.json
financewolf validate 'zugferd/*.pdf' --api v2 --family zugferd-facturx --ruleset latest --output zugferd-results.json
# Equivalent: python3 -m ironfang_financewolf validate ...
```

`--api v2` validates through V2: directories select `*.pdf` as well as
`*.xml`, `--family`, `--variant` and `--scope` narrow the selection (they are
refused without `--api v2`), and each file gets one line naming its outcome
and check groups, for example
`e-invoices/invoice.pdf: invalid (pdfa passed, attachment_metadata failed, invoice_xml passed)`.
A refusal shows its problem code. The report adds `"api_version": "v2"`.

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
safe diagnostic. Human output contains counts, check groups and problem
codes, never finding messages.

Every document is sent exactly once per run, at most 5 MiB (20 MiB for a V2
PDF), with a default 30-second HTTP timeout (45 for a V2 PDF) and a 4 MiB
response limit. Redirects are refused. There
are no automatic retries or idempotency keys: a new run/call may be a new billable
operation, even if an earlier response was lost. A timeout does not cancel work
already accepted by the API. Do not retry automatically on 429/5xx without
accounting for that behaviour.

The report schema remains `financewolf/action-results/v1`, shared with the
GitHub Action: totals, valid/invalid/error counts and per-file results. Full
results can contain invoice text; review storage, access and retention. XML is
sent to Ironfang Finance under the authenticated API retention policy.
Validation neither transmits through Peppol nor certifies tax/legal compliance
or recipient acceptance. Public PyPI publication is not claimed by this review
candidate.
