"""Bounded HTTPS client. Ironfang Finance/PHIVE alone determines invoice validity."""

import hashlib
import json
import math
import re
import urllib.error
import urllib.parse
import urllib.request

from .errors import VERSION, IronfangFinanceError, NoRedirect
from .v2 import MAX_RESPONSE, MAX_XML, V2Methods, _http_error

API = "https://api.ironfang.com/finance/v1/einvoices"
LAYERS = ["input", "xml", "xsd", "en16931", "peppol"]


def check_ruleset(ruleset):
    if not isinstance(ruleset, str) or not re.fullmatch(
        r"latest|fwrs_[a-z0-9_]{1,150}", ruleset
    ):
        raise IronfangFinanceError("invalid_ruleset")


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
        raise IronfangFinanceError("invalid_api_response")
    return result


class IronfangFinance(V2Methods):
    """The V1 methods are unchanged; ``V2Methods`` adds the ``*_v2`` ones.

    ``timeout`` applies to every request. Left unset, it is 30 seconds, and
    45 for a V2 PDF validation, whose server-side deadline is 30 seconds.
    """

    def __init__(self, api_key, *, timeout=None, opener=None):
        self._timeout_explicit = timeout is not None
        timeout = 30 if timeout is None else timeout
        if (
            not isinstance(api_key, str)
            or not api_key
            or any(ord(c) < 33 or ord(c) > 126 for c in api_key)
        ):
            raise IronfangFinanceError("invalid_api_key")
        if (
            not isinstance(timeout, (int, float))
            or not math.isfinite(timeout)
            or timeout <= 0
        ):
            raise IronfangFinanceError("invalid_timeout")
        self._key = api_key
        self._timeout = timeout
        self._opener = opener or urllib.request.build_opener(NoRedirect())

    def validate(self, xml, *, ruleset="latest"):
        """Submit exact bytes once. Return valid/invalid; raise on service failure.

        No automatic retry: a new call can create another billable operation.
        Pin an immutable, type-specific ruleset for reproducible CI.
        """
        if not isinstance(xml, bytes) or not xml or len(xml) > MAX_XML:
            raise IronfangFinanceError("empty_or_oversized_input")
        check_ruleset(ruleset)
        request = urllib.request.Request(
            API + "/validate?" + urllib.parse.urlencode({"ruleset": ruleset}),
            data=xml,
            method="POST",
            headers={
                "Authorization": "Bearer " + self._key,
                "Content-Type": "application/xml",
                "User-Agent": "Ironfang-Finance-Python/" + VERSION,
                "Accept": "application/json",
            },
        )
        try:
            with self._opener.open(request, timeout=self._timeout) as response:
                body = response.read(MAX_RESPONSE + 1)
                if response.status != 200 or len(body) > MAX_RESPONSE:
                    raise IronfangFinanceError("invalid_api_response")
                result = json.loads(body)
        except urllib.error.HTTPError as exc:
            raise _http_error(exc) from None
        except (OSError, ValueError, TypeError, RecursionError):
            raise IronfangFinanceError("api_request_failed") from None
        return check_result(result, xml, ruleset)
