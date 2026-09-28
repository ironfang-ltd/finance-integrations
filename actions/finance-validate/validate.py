"""Composite Action adapter for the shared Ironfang Finance Python client/runner."""

import os
import re
import sys
from pathlib import Path

# Resolve beside the trusted Action checkout, not the caller's workspace or PYTHONPATH.
sys.path.insert(
    0, str(Path(__file__).resolve().parents[2] / "sdk/finance/python/src")
)
from ironfang_finance import IronfangFinance, IronfangFinanceError
from ironfang_finance.client import check_ruleset
from ironfang_finance.v2 import GROUPS
from ironfang_finance.runner import (
    check_selection,
    empty_report,
    exit_code,
    files_in,
    run_files,
    summary,
    temporary_report,
)


def escape(value, prop=False):
    value = str(value).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    return value.replace(":", "%3A").replace(",", "%2C") if prop else value


def annotation(file, message):
    print(f"::error file={escape(file, True)}::{escape(message)}")


def on_result(item):
    if item["outcome"] == "valid":
        return
    result = item.get("result", {})
    ids = sorted({str(f.get("rule_id", "")) for f in result.get("findings", [])})
    # V2 names PDF/A rules like ISO19005-3:6.2-1.
    ids = [rid for rid in ids if re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", rid)]
    # A V2 verdict names the check groups that failed; a refusal its code.
    failed = [
        str(g.get("group"))
        for g in result.get("groups", [])
        if g.get("status") == "failed" and g.get("group") in GROUPS
    ]
    detail = f" ({', '.join(failed)} failed)" if failed else ""
    if item.get("problem"):
        detail = f" ({item['problem']})"
    annotation(
        item["file"],
        "Ironfang Finance: "
        + item["outcome"]
        + detail
        + ("; " + ", ".join(ids[:20]) if ids else ""),
    )


def main():
    workspace = Path(os.environ.get("GITHUB_WORKSPACE", ".")).resolve()
    api = os.environ.get("FINANCE_ACTION_API") or "v1"
    report = empty_report(api)
    try:
        ruleset = os.environ.get("FINANCE_ACTION_RULESET", "latest")
        check_ruleset(ruleset)
        selectors = check_selection(
            api,
            os.environ.get("FINANCE_ACTION_FAMILY") or None,
            os.environ.get("FINANCE_ACTION_VARIANT") or None,
            os.environ.get("FINANCE_ACTION_SCOPE") or None,
        )
        client = IronfangFinance(os.environ.get("FINANCE_ACTION_KEY", ""))
        files = files_in(
            workspace, os.environ.get("FINANCE_ACTION_FILES", "").splitlines(), api
        )
        run_files(
            client,
            files,
            workspace,
            ruleset,
            report=report,
            on_result=on_result,
            api=api,
            selectors=selectors,
        )
    except (IronfangFinanceError, OSError) as exc:
        report["errors"] += 1
        report["error"] = (
            exc.code if isinstance(exc, IronfangFinanceError) else "input_read_failed"
        )
        annotation("", "Ironfang Finance: " + report["error"])
    output = temporary_report(report)
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as target:
            target.write(f"results={output}\n")
    print(summary(report))
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as target:
            target.write(summary(report) + "\n")
    return exit_code(report)


if __name__ == "__main__":
    sys.exit(main())
