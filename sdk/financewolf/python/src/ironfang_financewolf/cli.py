"""API-backed validation CLI. Keys come only from FINANCEWOLF_API_KEY."""

import argparse
import json
import os
import sys
from pathlib import Path

from . import Financewolf, FinancewolfError, __version__
from .client import check_ruleset
from .runner import empty_report, exit_code, files_in, run_files, summary


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="financewolf",
        description="Validate UBL files through the Financewolf API.",
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
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="New private JSON report; existing files are refused",
    )
    args = parser.parse_args(argv)
    report = empty_report()
    try:
        check_ruleset(args.ruleset)
        # Reserve the output before making billable calls, but after selection
        # so a report name matching the glob cannot become an invoice input.
        files = files_in(args.workspace, args.files)
        client = Financewolf(os.environ.get("FINANCEWOLF_API_KEY", ""))
        fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except (OSError, FinancewolfError) as exc:
        print(
            str(exc)
            if isinstance(exc, FinancewolfError)
            else "Financewolf: output unavailable",
            file=sys.stderr,
        )
        return 2
    with os.fdopen(fd, "w", encoding="utf-8") as target:
        try:
            run_files(
                client, files, args.workspace.resolve(), args.ruleset, report=report
            )
        finally:
            json.dump(report, target, indent=2)
            target.write("\n")
    print(summary(report), file=sys.stderr)
    return exit_code(report)


if __name__ == "__main__":
    sys.exit(main())
