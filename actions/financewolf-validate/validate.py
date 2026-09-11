"""Composite Action adapter for the shared Financewolf Python client/runner."""

import os
import re
import sys
from pathlib import Path

# Resolve beside the trusted Action checkout, not the caller's workspace or PYTHONPATH.
sys.path.insert(
    0, str(Path(__file__).resolve().parents[2] / "sdk/financewolf/python/src")
)
from ironfang_financewolf import Financewolf, FinancewolfError
from ironfang_financewolf.client import check_ruleset
from ironfang_financewolf.runner import (
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
    ids = sorted(
        {str(f.get("rule_id", "")) for f in item.get("result", {}).get("findings", [])}
    )
    ids = [rid for rid in ids if re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", rid)]
    annotation(
        item["file"],
        "Financewolf: " + item["outcome"] + ("; " + ", ".join(ids[:20]) if ids else ""),
    )


def main():
    workspace = Path(os.environ.get("GITHUB_WORKSPACE", ".")).resolve()
    report = empty_report()
    try:
        ruleset = os.environ.get("FW_ACTION_RULESET", "latest")
        check_ruleset(ruleset)
        client = Financewolf(os.environ.get("FW_ACTION_KEY", ""))
        files = files_in(workspace, os.environ.get("FW_ACTION_FILES", "").splitlines())
        run_files(client, files, workspace, ruleset, report=report, on_result=on_result)
    except (FinancewolfError, OSError) as exc:
        report["errors"] += 1
        report["error"] = (
            exc.code if isinstance(exc, FinancewolfError) else "input_read_failed"
        )
        annotation("", "Financewolf: " + report["error"])
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
