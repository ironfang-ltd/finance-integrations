# Financewolf integrations

Official Ironfang Finance (Financewolf) validation SDKs, Python CLI and GitHub
Action, version 0.2.1. They submit exact invoice bytes to the Ironfang Finance
API: UBL Peppol BIS Billing 3 through V1, and through V2 also XRechnung 3.0.2
(UBL or CII) and ZUGFeRD 2.5.2 / Factur-X 1.09.2 as XML or as a PDF with its
embedded invoice XML. The registered validation artefacts determine the
outcome; clients check response integrity and the chosen ruleset.

## Install

The TypeScript client is on npm:

```sh
npm install @ironfang/financewolf@0.2.1
```

The Python client and the release files are on the
[v0.2.1 release](https://github.com/ironfang-ltd/financewolf-integrations/releases/tag/v0.2.1);
verify each against `SHA256SUMS` before installing it (the npm package is the
same `ironfang-financewolf-0.2.1.tgz`):

```sh
python3 -m pip install ./ironfang_financewolf-0.2.1-py3-none-any.whl
```

0.2.1 calls the API at `api.ironfang.com`, where Ironfang moved on
28 September 2026. Earlier versions call `api.ironfang.uk`, which now
redirects to it; the Python client refuses the redirect and the
TypeScript client loses the API key on it, so upgrade.

Python requires 3.10+; the TypeScript/JavaScript client requires Node 20+ ESM.
Neither package has runtime dependencies. Each npm release is published from
the reviewed GitHub release asset, byte for byte. PyPI registry availability
is not claimed.

Set `FINANCEWOLF_API_KEY` through your secret manager using a key scoped to
`finance:einvoices:write`.

```sh
financewolf validate 'invoices/**/*.xml' \
  --ruleset fwrs_bis3_billing_invoice_2026_5_r5 \
  --output invoice-results.json
```

The output path must be new. Exit 0 means all valid, 1 means an invalid document,
and 2 means an input/configuration/service or response-integrity error. The
`financewolf` validation CLI is separate from the offline `financewolf-verify`
signed-report verifier.

V2 takes `--api v2`, with `--family`, `--variant` and `--scope` to narrow the
detected format; a directory picks up PDFs as well as XML:

```sh
financewolf validate invoices/ --api v2 --family zugferd-facturx \
  --output invoice-results.json
```

[Python SDK and CLI reference](sdk/financewolf/python/README.md),
[Python example](sdk/financewolf/examples/validate.py),
[Node example](sdk/financewolf/examples/validate.mjs), and the V2 examples
[validate-v2.py](sdk/financewolf/examples/validate-v2.py) and
[validate-v2.mjs](sdk/financewolf/examples/validate-v2.mjs).

## GitHub Action

```yaml
permissions:
  contents: read
jobs:
  invoices:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4.4.0
        with:
          persist-credentials: false
      - id: invoices
        uses: ironfang-ltd/financewolf-integrations/actions/financewolf-validate@v0.2.1
        with:
          files: invoices/**/*.xml
          ruleset: fwrs_bis3_billing_invoice_2026_5_r5
          api-key: ${{ secrets.FINANCEWOLF_API_KEY }}
      - uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02 # v4.6.2
        if: always() && steps.invoices.outputs.results != ''
        with:
          name: financewolf-results
          path: ${{ steps.invoices.outputs.results }}
          retention-days: 7
```

Pin the Financewolf Action to the full commit SHA in the release notes for
reproducible use. CreditNote has its own ruleset, for example
`fwrs_bis3_billing_creditnote_2026_5_r5`. The compatible `latest` default detects
the document type and follows its active ruleset. The Action loads the bundled
Python client without installing dependencies; keep this repository's directory
structure intact. See the [Action reference](actions/financewolf-validate/README.md)
for file boundaries, outputs and secure workflow guidance. Set
`api-version: v2` (with `family`, `variant` and `scope` if needed) to validate
XRechnung and ZUGFeRD / Factur-X, including PDFs.

## Behaviour and provenance

Requests are limited to 5 MiB XML, 4 MiB response and a default 30-second timeout;
a V2 PDF may be up to 20 MiB with a 45-second default. There are no automatic
retries. V2 calls accept an idempotency key, so a repeated call replays the
first result instead of charging again; without one, repeat calls can be
billable, and a timeout does not undo work already accepted. Keys belong in secrets, never
in command arguments. JSON reports can contain invoice information: restrict
access and retention. Annotations print bounded rule IDs rather than invoice text.

Validation does not transmit invoices through Peppol, make Ironfang an Access
Point, register participants, certify legal/tax compliance or guarantee recipient
acceptance.

This repository starts with fresh history and contains only the reviewed public
Action/Python dependency bundle, examples, MIT licences and release metadata. The
TypeScript package is supplied as a compiled release asset with declarations and
its MIT licence. No service source or invoice corpus is included.

The archives, bundled READMEs and BUILD.json preserve the reviewed candidate
exactly. Their pre-publication wording and `published: false` describe build-time
state; this README and the release entry describe the public distribution. The
release notes record the source commit, public Action commit and qualification.
No GitHub Marketplace listing is created.
