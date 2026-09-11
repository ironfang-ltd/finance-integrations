"""Bounded HTTPS client. Financewolf/PHIVE alone determines invoice validity."""

import hashlib
import json
import math
import re
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.ironfang.uk/financewolf/v1/einvoices"
MAX_XML = 5 << 20
MAX_RESPONSE = 4 << 20
LAYERS = ["input", "xml", "xsd", "en16931", "peppol"]


class FinancewolfError(Exception):
    """A client/service failure, never an invalid invoice verdict."""

    def __init__(self, code, *, status=0):
        self.code = code
        self.status = status
        super().__init__(
            f"Financewolf: {code}" + (f" (HTTP {status})" if status else "")
        )


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def check_ruleset(ruleset):
    if not isinstance(ruleset, str) or not re.fullmatch(
        r"latest|fwrs_[a-z0-9_]{1,150}", ruleset
    ):
        raise FinancewolfError("invalid_ruleset")


def check_result(result, raw, ruleset):
    """Check response integrity and completion, not UBL or business rules."""
    try:
        valid = (
            result["schema"] == "financewolf/einvoice/validation-result/v1"
            and result["status"] == "completed"
            and result["outcome"] in ("valid", "invalid")
            and result["input"]["sha256"] == hashlib.sha256(raw).hexdigest()
            and type(result["input"]["bytes"]) is int
            and result["input"]["bytes"] == len(raw)
            and result["input"]["document_type"] in ("invoice", "credit_note")
            and re.fullmatch(r"fwrs_[a-z0-9_]{1,150}", result["ruleset"]["id"])
            and (ruleset == "latest" or result["ruleset"]["id"] == ruleset)
            and isinstance(result["findings"], list)
            and all(
                isinstance(f, dict)
                and all(
                    isinstance(f.get(field), str)
                    for field in ("layer", "severity", "rule_id", "message")
                )
                for f in result["findings"]
            )
            and isinstance(result["layers"], list)
            and [layer["layer"] for layer in result["layers"]] == LAYERS
            and all(
                layer["status"] in ("passed", "failed", "skipped")
                for layer in result["layers"]
            )
            and (
                all(layer["status"] == "passed" for layer in result["layers"])
                if result["outcome"] == "valid"
                else any(layer["status"] == "failed" for layer in result["layers"])
            )
        )
    except (KeyError, TypeError):
        valid = False
    if not valid:
        raise FinancewolfError("invalid_api_response")
    return result


class Financewolf:
    def __init__(self, api_key, *, timeout=30, opener=None):
        if (
            not isinstance(api_key, str)
            or not api_key
            or any(ord(c) < 33 or ord(c) > 126 for c in api_key)
        ):
            raise FinancewolfError("invalid_api_key")
        if (
            not isinstance(timeout, (int, float))
            or not math.isfinite(timeout)
            or timeout <= 0
        ):
            raise FinancewolfError("invalid_timeout")
        self._key = api_key
        self._timeout = timeout
        self._opener = opener or urllib.request.build_opener(NoRedirect())

    def validate(self, xml, *, ruleset="latest"):
        """Submit exact bytes once. Return valid/invalid; raise on service failure.

        No automatic retry: a new call can create another billable operation.
        Pin an immutable, type-specific ruleset for reproducible CI.
        """
        if not isinstance(xml, bytes) or not xml or len(xml) > MAX_XML:
            raise FinancewolfError("empty_or_oversized_input")
        check_ruleset(ruleset)
        request = urllib.request.Request(
            API + "/validate?" + urllib.parse.urlencode({"ruleset": ruleset}),
            data=xml,
            method="POST",
            headers={
                "Authorization": "Bearer " + self._key,
                "Content-Type": "application/xml",
                "User-Agent": "Financewolf-Python/0.1.0",
                "Accept": "application/json",
            },
        )
        try:
            with self._opener.open(request, timeout=self._timeout) as response:
                body = response.read(MAX_RESPONSE + 1)
                if response.status != 200 or len(body) > MAX_RESPONSE:
                    raise FinancewolfError("invalid_api_response")
                result = json.loads(body)
        except urllib.error.HTTPError as exc:
            exc.close()
            raise FinancewolfError("api_http_error", status=exc.code) from None
        except (OSError, ValueError, TypeError, RecursionError):
            raise FinancewolfError("api_request_failed") from None
        return check_result(result, xml, ruleset)
