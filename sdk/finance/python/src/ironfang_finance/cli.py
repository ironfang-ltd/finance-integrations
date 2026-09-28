"""API-backed validation CLI. Keys come only from IRONFANG_API_KEY (or the older FINANCEWOLF_API_KEY)."""

import argparse
import json
import os
import sys
from pathlib import Path

from . import IronfangFinance, IronfangFinanceError, __version__
from .client import check_ruleset
from .runner import (
    check_selection,
    describe,
    empty_report,
    exit_code,
    files_in,
    run_files,
    summary,
)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="ironfang-finance",
        description=(
            "Validate invoices through the Ironfang Finance API: UBL through V1, "
            "or with --api v2 also XRechnung and ZUGFeRD / Factur-X, XML or PDF."
        ),
    )
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("command", choices=["validate"])
    parser.add_argument(
        "files",
        nargs="+",
        help="Files, directories or quoted globs within the workspace",
    )
    parser.add_argument(
        "--ruleset",
        required=True,
        help="Exact immutable ruleset ID, or explicitly choose latest",
    )
    parser.add_argument(
        "--api",
        choices=["v1", "v2"],
        default="v1",
        help="v2 also validates XRechnung and ZUGFeRD / Factur-X, and PDFs",
    )
    parser.add_argument("--family", help="V2 only: e.g. xrechnung or zugferd-facturx")
    parser.add_argument("--variant", help="V2 only: e.g. en16931 or extended")
    parser.add_argument("--scope", help="V2 only: xml or hybrid_pdf")
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="New private JSON report; existing files are refused",
    )
    args = parser.parse_args(argv)
    report = empty_report(args.api)
    try:
        check_ruleset(args.ruleset)
        selectors = check_selection(args.api, args.family, args.variant, args.scope)
        # Reserve the output before making billable calls, but after selection
        # so a report name matching the glob cannot become an invoice input.
        files = files_in(args.workspace, args.files, args.api)
        client = IronfangFinance(os.environ.get("IRONFANG_API_KEY") or os.environ.get("FINANCEWOLF_API_KEY", ""))
        fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except (OSError, IronfangFinanceError) as exc:
        print(
            str(exc)
            if isinstance(exc, IronfangFinanceError)
            else "Ironfang Finance: output unavailable",
            file=sys.stderr,
        )
        return 2
    with os.fdopen(fd, "w", encoding="utf-8") as target:
        try:
            run_files(
                client,
                files,
                args.workspace.resolve(),
                args.ruleset,
                report=report,
                api=args.api,
                selectors=selectors,
                # V2 names each file's check groups; V1 keeps its counts-only output.
                on_result=(
                    (lambda item: print(describe(item), file=sys.stderr))
                    if args.api == "v2"
                    else None
                ),
            )
        finally:
            json.dump(report, target, indent=2)
            target.write("\n")
    print(summary(report), file=sys.stderr)
    return exit_code(report)


if __name__ == "__main__":
    sys.exit(main())
