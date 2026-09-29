# Ironfang Finance integrations

Official Ironfang Finance validation SDKs, Python CLI and GitHub Action,
version 2.1.0. They submit exact invoice bytes to the Ironfang Finance
API: UBL Peppol BIS Billing 3 through V1, and through V2 also XRechnung 3.0.2
(UBL or CII) and ZUGFeRD 2.5.2 / Factur-X 1.09.2 as XML or as a PDF with its
embedded invoice XML. The registered validation artefacts determine the
outcome; clients check response integrity and the chosen ruleset.

## Install

```sh
npm install @ironfang/finance@2.1.0
pip install ironfang-finance==2.1.0
```

The same files are on the
[v2.1.0 release](https://github.com/ironfang-ltd/finance-integrations/releases/tag/v2.1.0);
verify each against `SHA256SUMS` before installing it.

Python requires 3.10+; the TypeScript/JavaScript client requires Node 20+ ESM.
Neither package has runtime dependencies.

These packages were called `@ironfang/financewolf` and `ironfang-financewolf`
up to 0.2.1. 2.0.0 removed the old class names (`Financewolf`,
`FinancewolfError`), the Python module `ironfang_financewolf`, the
`financewolf` command and the `FINANCEWOLF_API_KEY` variable. 2.1.0 follows
Ironfang's unified billing: a V1 error now carries the API's problem code as
well, a billing refusal adds the product, meter, allowance renewal and
Retry-After. A V2 verdict's `usage` carries `remaining` and `period_ends_at`
only on results recorded before usage billing.

## CLI

Set `IRONFANG_API_KEY` through your secret manager using a key scoped to
`finance:einvoices:write`.

```sh
ironfang-finance validate 'invoices/**/*.xml' \
  --ruleset fwrs_bis3_billing_invoice_2026_5_r5 \
  --output invoice-results.json
```

The output path must be new. Exit 0 means all valid, 1 means an invalid document,
and 2 means an input/configuration/service or response-integrity error.

V2 takes `--api v2`, with `--family`, `--variant` and `--scope` to narrow the
detected format; a directory picks up PDFs as well as XML:

```sh
ironfang-finance validate invoices/ --api v2 --family zugferd-facturx \
  --output invoice-results.json
```

[Python SDK and CLI reference](sdk/finance/python/README.md),
[Python example](sdk/finance/examples/validate.py),
[Node example](sdk/finance/examples/validate.mjs), and the V2 examples
[validate-v2.py](sdk/finance/examples/validate-v2.py) and
[validate-v2.mjs](sdk/finance/examples/validate-v2.mjs).

## GitHub Action

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
        uses: ironfang-ltd/finance-integrations/actions/finance-validate@v2.1.0
        with:
          files: invoices/**/*.xml
          ruleset: fwrs_bis3_billing_invoice_2026_5_r5
          api-key: ${{ secrets.IRONFANG_API_KEY }}
      - uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1
        if: always() && steps.invoices.outputs.results != ''
        with:
          name: finance-results
          path: ${{ steps.invoices.outputs.results }}
          retention-days: 7
```

The Action moved from `actions/financewolf-validate` to
`actions/finance-validate` in 1.0.0; its inputs and outputs are unchanged,
and workflows pinned to an earlier tag keep working. Pin the Action to the full
commit SHA in the release notes for reproducible use. CreditNote has its own
ruleset, for example `fwrs_bis3_billing_creditnote_2026_5_r5`. The `latest`
default detects the document type and follows its active ruleset. The Action
loads the bundled Python client without installing dependencies; keep this
repository's directory structure intact. See the
[Action reference](actions/finance-validate/README.md) for file boundaries,
outputs and secure workflow guidance. Set `api-version: v2` (with `family`,
`variant` and `scope` if needed) to validate XRechnung and ZUGFeRD / Factur-X,
including PDFs.

## Behaviour and provenance

Requests are limited to 5 MiB XML, 4 MiB response and a default 30-second timeout;
a V2 PDF may be up to 20 MiB with a 45-second default. There are no automatic
retries. V2 calls accept an idempotency key, so a repeated call replays the
first result instead of charging again; without one, repeat calls can be
billable, and a timeout does not undo work already accepted. Validations count
against your organisation's Ironfang billing account, which has a monthly free
allowance; when it refuses one, nothing is validated and the error carries the
API's code, such as `free_allowance_exhausted`. Keys belong in secrets, never
in command arguments. JSON reports can contain invoice information: restrict
access and retention. Annotations print bounded rule IDs rather than invoice text.

Validation does not transmit invoices through Peppol, make Ironfang an Access
Point, register participants, certify legal/tax compliance or guarantee recipient
acceptance.

This repository contains only the reviewed public Action/Python dependency
bundle, examples, MIT licences and release metadata. The TypeScript package is
supplied as a compiled release asset with declarations and its MIT licence. No
service source or invoice corpus is included. BUILD.json records the source
commit each release was built from.
