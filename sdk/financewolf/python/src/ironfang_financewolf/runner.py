"""File selection and reports shared by the CLI and GitHub Action."""

import glob
import hashlib
import json
import os
import tempfile
from pathlib import Path

from .client import MAX_XML, FinancewolfError
from .v2 import FAMILIES, MAX_PDF, SCOPES, VARIANTS

# What a directory selects: V1 validates UBL XML; V2 also takes the
# ZUGFeRD / Factur-X PDF that carries its invoice XML.
SUFFIXES = {"v1": ("*.xml",), "v2": ("*.xml", "*.pdf")}


def files_in(workspace, patterns, api="v1"):
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
            candidates = (
                [c for suffix in SUFFIXES[api] for c in path.rglob(suffix)]
                if path.is_dir()
                else [path]
            )
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


def empty_report(api="v1"):
    # Preserve the Action's existing report contract for CLI consumers too.
    # A V2 run says so; each result then carries the V2 verdict schema.
    report = {
        "schema": "financewolf/action-results/v1",
        "total": 0,
        "valid": 0,
        "invalid": 0,
        "errors": 0,
        "results": [],
    }
    if api == "v2":
        report["api_version"] = "v2"
    return report


def describe(item):
    """One line for a file: its outcome, and for a V2 verdict its check groups.

    Never a finding message: those can quote the invoice.
    """
    line = f"{item['file']}: {item['outcome']}"
    groups = item.get("result", {}).get("groups")
    if groups:
        line += " (" + ", ".join(f"{g['group']} {g['status']}" for g in groups) + ")"
    if item["outcome"] == "error":
        line += f" {item['error']}" + (f" {item['problem']}" if item.get("problem") else "")
    return line


def check_selection(api, family=None, variant=None, scope=None):
    """The V2 selectors, refused with V1 (which has none) or when unknown."""
    if api not in SUFFIXES:
        raise FinancewolfError("invalid_api_version")
    if api == "v1" and (family or variant or scope):
        raise FinancewolfError("v2_selector_with_v1")
    if (family and family not in FAMILIES) or (variant and variant not in VARIANTS):
        raise FinancewolfError("invalid_family_or_variant")
    if scope and scope not in SCOPES:
        raise FinancewolfError("invalid_scope")
    return {k: v for k, v in (("family", family), ("variant", variant), ("scope", scope)) if v}


def run_files(
    client,
    files,
    workspace,
    ruleset,
    *,
    report=None,
    on_result=None,
    api="v1",
    selectors=None,
):
    """Validate each file once, through V1 or V2, recording every outcome.

    ``selectors`` are the V2 family, variant and scope; V1 takes none.
    """
    report = report if report is not None else empty_report(api)
    limit = MAX_PDF if api == "v2" else MAX_XML
    for path in files:
        item = {"file": path.relative_to(workspace).as_posix()}
        try:
            with path.open("rb") as source:
                raw = source.read(limit + 1)
            if len(raw) <= limit:
                item["sha256"] = hashlib.sha256(raw).hexdigest()
            if api == "v2":
                result = client.validate_v2(raw, ruleset=ruleset, **(selectors or {}))
            else:
                result = client.validate(raw, ruleset=ruleset)
            item.update(outcome=result["outcome"], result=result)
        except FinancewolfError as exc:
            item.update(outcome="error", error=exc.code)
            if exc.status:
                item["http_status"] = exc.status
            if exc.problem:
                item["problem"] = exc.problem
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
        f"Ironfang Finance: {report['total']} documents, {report['valid']} valid, "
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
