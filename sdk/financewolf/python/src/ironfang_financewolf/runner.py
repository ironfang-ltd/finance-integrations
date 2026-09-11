"""File selection and reports shared by the CLI and GitHub Action."""

import glob
import hashlib
import json
import os
import tempfile
from pathlib import Path

from .client import MAX_XML, FinancewolfError


def files_in(workspace, patterns):
    root = workspace.resolve()
    selected = set()
    for pattern in patterns:
        if not pattern.strip():
            continue
        found = False
        for match in glob.glob(str(root / pattern.strip()), recursive=True):
            path = Path(match)
            if not path.resolve().is_relative_to(root):
                raise FinancewolfError("path_outside_workspace")
            candidates = path.rglob("*.xml") if path.is_dir() else [path]
            for candidate in candidates:
                resolved = candidate.resolve()
                if not resolved.is_relative_to(root):
                    raise FinancewolfError("path_outside_workspace")
                if resolved.is_file():
                    selected.add(resolved)
                    found = True
        if not found:
            raise FinancewolfError("unmatched_file_pattern")
    if not selected:
        raise FinancewolfError("no_documents_selected")
    return sorted(selected)


def empty_report():
    # Preserve the Action's existing report contract for CLI consumers too.
    return {
        "schema": "financewolf/action-results/v1",
        "total": 0,
        "valid": 0,
        "invalid": 0,
        "errors": 0,
        "results": [],
    }


def run_files(client, files, workspace, ruleset, *, report=None, on_result=None):
    report = report if report is not None else empty_report()
    for path in files:
        item = {"file": path.relative_to(workspace).as_posix()}
        try:
            with path.open("rb") as source:
                raw = source.read(MAX_XML + 1)
            if len(raw) <= MAX_XML:
                item["sha256"] = hashlib.sha256(raw).hexdigest()
            result = client.validate(raw, ruleset=ruleset)
            item.update(outcome=result["outcome"], result=result)
        except FinancewolfError as exc:
            item.update(outcome="error", error=exc.code)
            if exc.status:
                item["http_status"] = exc.status
        except OSError:
            item.update(outcome="error", error="input_read_failed")
        report["results"].append(item)
        report["total"] += 1
        report["errors" if item["outcome"] == "error" else item["outcome"]] += 1
        if on_result:
            on_result(item)
    return report


def exit_code(report):
    # Errors take precedence in a mixed invalid/error selection.
    return 2 if report["errors"] else 1 if report["invalid"] else 0


def summary(report):
    return (
        f"Financewolf: {report['total']} documents, {report['valid']} valid, "
        f"{report['invalid']} invalid, {report['errors']} errors."
    )


def temporary_report(report):
    fd, name = tempfile.mkstemp(
        prefix="financewolf-validation-",
        suffix=".json",
        dir=os.environ.get("RUNNER_TEMP"),
    )
    with os.fdopen(fd, "w", encoding="utf-8") as target:
        json.dump(report, target, indent=2)
        target.write("\n")
    return name
