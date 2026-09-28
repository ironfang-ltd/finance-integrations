# Ironfang Finance GitHub Action

Review candidate using the shared Ironfang Finance Python client. Python 3.10+
is required; no packages are installed at Action runtime. It calls the Ironfang
Finance API, with PHIVE as the validator. This is not a Peppol network
transmitter.

Formerly `financewolf-validate`. The report schema keeps its
`financewolf/action-results/v1` name so existing report readers work unchanged.

From the reviewed checkout (which includes `sdk/finance/python/src`):

```yaml
permissions:
  contents: read
jobs:
  invoices:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - id: invoices
        uses: ./actions/finance-validate
        with:
          files: |
            invoices/**/*.xml
          ruleset: fwrs_bis3_billing_invoice_2026_5_r5
          api-key: ${{ secrets.IRONFANG_API_KEY }}
      - uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1
        if: always() && steps.invoices.outputs.results != ''
        with:
          name: finance-results
          path: ${{ steps.invoices.outputs.results }}
          retention-days: 7
```

Run CreditNote in a separate pinned step using its immutable ruleset ID
(`fwrs_bis3_billing_creditnote_2026_5_r5`). The
backward-compatible `latest` default detects the type and selects the current
active ruleset; it intentionally permits behaviour to change after an upgrade.
A pinned ID is checked against the response. Never accept silent substitution.

## XRechnung and ZUGFeRD / Factur-X (V2)

Set `api-version: v2` to validate through the V2 API, which also takes
XRechnung 3.0.2 (UBL or CII) and ZUGFeRD 2.5.2 / Factur-X 1.09.2, as XML or as
a PDF with its embedded invoice XML. Directories then select `*.pdf` as well
as `*.xml`. Without `family`, each document's family is detected from its own
declaration; `family`, `variant` and `scope` narrow it and are checked against
the verdict.

```yaml
      - id: e-invoices
        uses: ./actions/finance-validate
        with:
          files: |
            e-invoices/
          api-version: v2
          family: zugferd-facturx
          api-key: ${{ secrets.IRONFANG_API_KEY }}
```

A V2 PDF may be up to 20 MiB and takes up to 45 seconds; XML stays at 5 MiB.
A refusal such as `no_embedded_invoice` or `family_mismatch` is an error
(exit 2) whose annotation and report item carry the API's problem code. An
invalid document's annotation names the check groups that failed (PDF/A,
attachment metadata, invoice XML) and its rule IDs. The report adds
`"api_version": "v2"`; each result is the V2 verdict. The `family`, `variant`
and `scope` inputs are refused with `api-version: v1`.

`files` accepts newline-separated files, directories (recursive `*.xml`) and
globs. Duplicate paths run once; empty/unmatched selections and resolved paths
outside the workspace fail. Exact bytes are submitted, capped at 5 MiB per file
(20 MiB for a V2 PDF), with a 30-second HTTP timeout (45 for a V2 PDF).
Redirects are refused. There are no automatic retries or idempotency keys:
rerunning can be another billable validation.

Exit **0** means all valid, **1** means invalid, **2** means input/configuration,
HTTP/transport or response-integrity error. All nonzero codes fail the workflow;
service failures are never classified as invalid invoices. A private JSON
report with schema `financewolf/action-results/v1` is exposed through the
unchanged `results` output, including on invalid/error outcomes.

The API key needs only `finance:einvoices:write`. Pass a GitHub secret;
inputs are passed as environment variables, never interpolated into shell code.
Python isolated mode prevents importing code from the caller's workspace or
`PYTHONPATH`; the shared SDK is loaded beside the reviewed Action checkout.
Annotations contain escaped filenames and bounded rule IDs, not invoice text.

Full report artifacts can contain invoice information. Review GitHub artifact
access and retention; selected XML is sent to Ironfang Finance and follows the
API's authenticated retention policy. Do not use `pull_request_target` to run
untrusted checkout code with secrets. Fork PRs should use offline tests or a
separate reviewed manual validation workflow. Pin checkout, upload and the
released Ironfang Finance Action to reviewed full commit SHAs.

The source repository is private. A prepared public bundle includes only the
Action and SDK allowlist, without service source or repository history. No
Marketplace listing or external `uses:` URL is claimed before a reviewed public
release. Copying this directory alone is insufficient: retain the accompanying
SDK directory from the bundle. The package script and live workflow are described
in the service repository.

```sh
PYTHONPATH=sdk/finance/python/src python3 -m unittest discover -s sdk/finance/python/tests -v
python3 -m unittest discover -s actions/finance-validate -v
```
