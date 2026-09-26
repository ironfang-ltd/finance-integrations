"""Ironfang Finance V2: XRechnung, ZUGFeRD / Factur-X and Peppol BIS Billing 3.

V2 validates an invoice XML, or a ZUGFeRD / Factur-X PDF with its embedded
XML, and reads results, jobs, batches and deliveries made through V1 or V2.
Ironfang Finance alone decides validity; these methods check that a response
is the complete answer for the exact bytes and selection sent.
"""

import base64
import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from .errors import VERSION, FinancewolfError

API_V2 = "https://api.ironfang.uk/finance/v2/einvoices"
MAX_XML = 5 << 20
MAX_PDF = 20 << 20
MAX_RESPONSE = 4 << 20
MAX_PROBLEM = 64 << 10
# The server's hybrid PDF deadline is 30 seconds.
PDF_TIMEOUT = 45

FAMILIES = ("peppol-bis-billing-3", "xrechnung", "zugferd-facturx")
VARIANTS = (
    "core",
    "extension",
    "cvd",
    "minimum",
    "basic-wl",
    "basic",
    "en16931",
    "extended",
    "xrechnung",
)
SCOPES = ("xml", "hybrid_pdf")
DOCUMENT_TYPES = ("invoice", "credit_note", "auto")
LAYERS_V2 = [
    "input",
    "pdfa",
    "hybrid_binding",
    "xml",
    "xsd",
    "en16931",
    "peppol",
    "xrechnung",
    "zugferd_profile",
]
GROUPS = ("pdfa", "attachment_metadata", "invoice_xml")
LOCATIONS = ("none", "xpath", "line-column", "pdf")
API_VERSIONS = ("v1", "v2")

SCHEMA_VERDICT = "ironfang/finance/einvoice/validation-result/v2"
RESULT_SCHEMAS = (
    SCHEMA_VERDICT,
    "financewolf/einvoice/validation-result/v1",
    "financewolf/einvoice/generation-result/v1",
)
SCHEMA_RESULT_LIST = "ironfang/finance/einvoice/result-list/v2"
SCHEMA_RULESET_LIST = "ironfang/finance/einvoice/ruleset-list/v2"
SCHEMA_JOB = "ironfang/finance/einvoice/job/v2"
SCHEMA_JOB_LIST = "ironfang/finance/einvoice/job-list/v2"
SCHEMA_BATCH = "ironfang/finance/einvoice/batch/v2"
SCHEMA_BATCH_LIST = "ironfang/finance/einvoice/batch-list/v2"
SCHEMA_DELIVERY = "ironfang/finance/einvoice/delivery/v2"
SCHEMA_DELIVERY_LIST = "ironfang/finance/einvoice/delivery-list/v2"

JOB_TERMINAL = ("completed", "failed", "cancelled")

_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_RULESET_ID = re.compile(r"fwrs_[a-z0-9_]{1,80}")
_SELECTOR = re.compile(r"latest|fwrs_[a-z0-9_]{1,80}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_IDEMPOTENCY = re.compile(r"[A-Za-z0-9_-]{8,128}")
_PROBLEM_CODE = re.compile(r"[a-z_]{1,64}")
_REQUEST_ID = re.compile(r"[A-Za-z0-9_-]{8,64}")


def media_type_of(document, media_type=None):
    """``application/pdf`` or ``application/xml``: as given, else from the bytes.

    The API inspects the content itself and refuses a mismatch; this only
    chooses the Content-Type and the size limit.
    """
    if media_type is None:
        return "application/pdf" if b"%PDF-" in document[:1024] else "application/xml"
    if media_type in ("application/xml", "text/xml"):
        return "application/xml"
    if media_type == "application/pdf":
        return media_type
    raise FinancewolfError("invalid_media_type")


def _check_document(document, media_type):
    if not isinstance(document, bytes) or not document:
        raise FinancewolfError("empty_or_oversized_input")
    media = media_type_of(document, media_type)
    if len(document) > (MAX_PDF if media == "application/pdf" else MAX_XML):
        raise FinancewolfError("empty_or_oversized_input")
    return media


def _options(ruleset, family, variant, document_type, scope):
    """The selectors that are set, each checked against the contract."""
    checks = [
        ("ruleset", ruleset, lambda v: isinstance(v, str) and _SELECTOR.fullmatch(v)),
        ("family", family, lambda v: v in FAMILIES),
        ("variant", variant, lambda v: v in VARIANTS),
        ("document_type", document_type, lambda v: v in DOCUMENT_TYPES),
        ("scope", scope, lambda v: v in SCOPES),
    ]
    options = {}
    for name, value, ok in checks:
        if value is None:
            continue
        if not ok(value):
            raise FinancewolfError("invalid_" + name)
        options[name] = value
    return options


def _check_id(value):
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise FinancewolfError("invalid_id")
    return value


def _is_int(value, minimum=0):
    return type(value) is int and value >= minimum


def check_v2_verdict(result, raw, media_type, options):
    """Check that a V2 verdict is complete and answers exactly what was sent.

    It checks integrity, not invoice rules: the hash and length of the bytes,
    the media type and scope they imply, the selection asked for, and a
    verdict consistent with its own layers.
    """
    pdf = media_type == "application/pdf"
    try:
        inp, rs = result["input"], result["ruleset"]
        layers, groups = result["layers"], result["groups"]
        order = [LAYERS_V2.index(layer["layer"]) for layer in layers]
        embedded = inp.get("embedded_xml")
        ruleset = options.get("ruleset", "latest")
        valid = (
            result["schema"] == SCHEMA_VERDICT
            and result["status"] == "completed"
            and result["outcome"] in ("valid", "invalid")
            and inp["media_type"] == media_type
            and inp["sha256"] == hashlib.sha256(raw).hexdigest()
            and _is_int(inp["bytes"])
            and inp["bytes"] == len(raw)
            and inp["document_type"] in ("invoice", "credit_note", "unknown")
            and (
                isinstance(embedded, dict)
                and isinstance(embedded.get("sha256"), str)
                and _SHA256.fullmatch(embedded["sha256"])
                and _is_int(embedded.get("bytes"), 1)
                if pdf
                else embedded is None
            )
            and isinstance(rs["id"], str)
            and _RULESET_ID.fullmatch(rs["id"])
            and rs["family"] in FAMILIES
            and rs["scope"] == ("hybrid_pdf" if pdf else "xml")
            and rs["requested"] == ruleset
            and (ruleset == "latest" or rs["id"] == ruleset)
            and all(
                rs.get(name) == options[name]
                for name in ("family", "variant", "scope")
                if name in options
            )
            and order
            and order[0] == 0
            and order == sorted(set(order))
            and all(
                layer["status"] in ("passed", "failed", "skipped")
                and _is_int(layer["fatal"])
                for layer in layers
            )
            and (result["outcome"] == "invalid")
            == any(layer["status"] == "failed" for layer in layers)
            and isinstance(groups, list)
            and groups
            and all(
                group["group"] in GROUPS
                and group["status"] in ("passed", "failed", "skipped")
                and isinstance(group["layers"], list)
                for group in groups
            )
            and isinstance(result["findings"], list)
            and all(
                isinstance(f, dict)
                and all(
                    isinstance(f.get(field), str)
                    for field in ("layer", "severity", "rule_id", "message")
                )
                and isinstance(f.get("location"), dict)
                and f["location"].get("kind") in LOCATIONS
                for f in result["findings"]
            )
            and [engine["role"] for engine in result["engines"]]
            == (["xml", "pdf"] if pdf else ["xml"])
            and isinstance(result["coverage"]["not_checked"], list)
        )
    except (KeyError, TypeError, ValueError, AttributeError):
        valid = False
    if not valid:
        raise FinancewolfError("invalid_api_response")
    return result


def _check_schema(result, schema, *, key=None, id_value=None):
    try:
        valid = result["schema"] in (
            schema if isinstance(schema, tuple) else (schema,)
        ) and (key is None or isinstance(result[key], list))
        if id_value is not None:
            valid = valid and result["id"] == id_value
    except (KeyError, TypeError):
        valid = False
    if not valid:
        raise FinancewolfError("invalid_api_response")
    return result


def _check_job(job, job_id=None):
    try:
        valid = (
            job["schema"] == SCHEMA_JOB
            and isinstance(job["id"], str)
            and _ID.fullmatch(job["id"])
            and job["status"] in ("queued", "running", *JOB_TERMINAL)
            and (job_id is None or job["id"] == job_id)
        )
    except (KeyError, TypeError):
        valid = False
    if not valid:
        raise FinancewolfError("invalid_api_response")
    return job


def _filters(**values):
    """List filters that are set, each bounded before it reaches a URL."""
    rules = {
        "cursor": lambda v: isinstance(v, str) and 1 <= len(v) <= 256,
        "limit": lambda v: type(v) is int and 1 <= v <= 100,
        "kind": lambda v: v in ("validate", "generate"),
        "outcome": lambda v: v in ("valid", "invalid"),
        "family": lambda v: v in FAMILIES,
        "variant": lambda v: v in VARIANTS,
        "api_version": lambda v: v in API_VERSIONS,
        "ruleset": lambda v: isinstance(v, str) and _RULESET_ID.fullmatch(v),
        "q": lambda v: isinstance(v, str) and 1 <= len(v) <= 255,
        "operation_id": lambda v: isinstance(v, str) and _ID.fullmatch(v),
        "destination": lambda v: isinstance(v, str) and _ID.fullmatch(v),
        "job_status": lambda v: v in ("queued", "running", *JOB_TERMINAL),
        "delivery_status": lambda v: v
        in ("pending", "retrying", "delivering", "delivered", "failed"),
        "document_type": lambda v: v in ("invoice", "credit_note"),
        "scope": lambda v: v in SCOPES,
        "operation": lambda v: v in ("validate", "generate"),
        "state": lambda v: v in ("scheduled", "sendable", "historical"),
    }
    query = {}
    for name, value in values.items():
        if value is None:
            continue
        if not rules[name](value):
            raise FinancewolfError("invalid_" + name)
        query[name.removeprefix("job_").removeprefix("delivery_")] = str(value)
    return query


class V2Methods:
    """The V2 API. Every method sends one request and never retries it.

    Validation and job submission can create billable operations; pass an
    ``idempotency_key`` to make a retry after a lost response safe.
    """

    def _v2(
        self,
        method,
        path,
        *,
        query=None,
        body=None,
        content_type=None,
        idempotency_key=None,
        expect=(200,),
        timeout=None,
    ):
        url = API_V2 + path
        if query:
            url += "?" + urllib.parse.urlencode(query)
        headers = {
            "Authorization": "Bearer " + self._key,
            "User-Agent": "Financewolf-Python/" + VERSION,
            "Accept": "application/json",
        }
        if content_type:
            headers["Content-Type"] = content_type
        if idempotency_key is not None:
            if not isinstance(idempotency_key, str) or not _IDEMPOTENCY.fullmatch(
                idempotency_key
            ):
                raise FinancewolfError("invalid_idempotency_key")
            headers["Idempotency-Key"] = idempotency_key
        request = urllib.request.Request(url, data=body, method=method, headers=headers)
        try:
            with self._opener.open(request, timeout=timeout or self._timeout) as response:
                raw = response.read(MAX_RESPONSE + 1)
                if response.status not in expect or len(raw) > MAX_RESPONSE:
                    raise FinancewolfError("invalid_api_response")
                if response.status == 204:
                    return None
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            raise _http_error(exc) from None
        except (OSError, ValueError, TypeError, RecursionError):
            raise FinancewolfError("api_request_failed") from None

    # -- validation ---------------------------------------------------------

    def validate_v2(
        self,
        document,
        *,
        media_type=None,
        ruleset="latest",
        family=None,
        variant=None,
        document_type=None,
        scope=None,
        idempotency_key=None,
    ):
        """Validate an invoice XML, or a ZUGFeRD / Factur-X PDF, through V2.

        Returns the verdict (``valid`` or ``invalid``) for these exact bytes.
        A refusal (for example ``family_mismatch`` or ``no_embedded_invoice``)
        or an indeterminate answer raises ``FinancewolfError`` with the API's
        ``problem`` code. Without ``family``, V2 detects the family from the
        document's own declaration.
        """
        media = _check_document(document, media_type)
        options = _options(ruleset, family, variant, document_type, scope)
        pdf = media == "application/pdf"
        result = self._v2(
            "POST",
            "/validate",
            query=options,
            body=document,
            content_type=media,
            idempotency_key=idempotency_key,
            timeout=None if self._timeout_explicit or not pdf else PDF_TIMEOUT,
        )
        return check_v2_verdict(result, document, media, {"ruleset": "latest", **options})

    def rulesets_v2(
        self,
        *,
        family=None,
        variant=None,
        document_type=None,
        scope=None,
        operation=None,
        state=None,
    ):
        """The releases V2 validates against, with their family, variant and scope."""
        query = _filters(
            family=family,
            variant=variant,
            document_type=document_type,
            scope=scope,
            operation=operation,
            state=state,
        )
        result = self._v2("GET", "/rulesets", query=query)
        return _check_schema(result, SCHEMA_RULESET_LIST, key="rulesets")

    # -- results ------------------------------------------------------------

    def results_v2(
        self,
        *,
        cursor=None,
        limit=None,
        kind=None,
        outcome=None,
        family=None,
        api_version=None,
        ruleset=None,
        q=None,
        operation_id=None,
    ):
        """One page of retained results, V1 and V2 together, newest first."""
        query = _filters(
            cursor=cursor,
            limit=limit,
            kind=kind,
            outcome=outcome,
            family=family,
            api_version=api_version,
            ruleset=ruleset,
            q=q,
            operation_id=operation_id,
        )
        result = self._v2("GET", "/results", query=query)
        return _check_schema(result, SCHEMA_RESULT_LIST, key="results")

    def result_v2(self, operation_id):
        """One retained result, in the schema it was made under (V1 or V2)."""
        result = self._v2("GET", "/results/" + _check_id(operation_id))
        return _check_schema(result, RESULT_SCHEMAS)

    def delete_result_v2(self, operation_id):
        """Erase a retained result. Deleting one already gone succeeds."""
        self._v2("DELETE", "/results/" + _check_id(operation_id), expect=(204,))

    # -- jobs and batches ---------------------------------------------------

    def submit_job_v2(
        self,
        document,
        *,
        media_type=None,
        ruleset="latest",
        family=None,
        variant=None,
        document_type=None,
        scope=None,
        idempotency_key=None,
    ):
        """Queue one durable validation. Returns the job (``queued`` at first)."""
        body = _job_body(document, media_type, ruleset, family, variant, document_type, scope)
        job = self._v2(
            "POST",
            "/jobs",
            body=json.dumps(body).encode(),
            content_type="application/json",
            idempotency_key=idempotency_key,
            expect=(200, 202),
            timeout=None if self._timeout_explicit else PDF_TIMEOUT,
        )
        return _check_job(job)

    def job_v2(self, job_id):
        return _check_job(self._v2("GET", "/jobs/" + _check_id(job_id)), job_id)

    def jobs_v2(self, *, cursor=None, limit=None, status=None, api_version=None):
        """One page of jobs, V1 and V2 together."""
        query = _filters(
            cursor=cursor, limit=limit, job_status=status, api_version=api_version
        )
        return _check_schema(self._v2("GET", "/jobs", query=query), SCHEMA_JOB_LIST, key="jobs")

    def cancel_job_v2(self, job_id):
        return _check_job(
            self._v2("POST", "/jobs/" + _check_id(job_id) + "/cancel"), job_id
        )

    def wait_for_job_v2(
        self, job_id, *, timeout=300, interval=2, sleep=time.sleep, clock=time.monotonic
    ):
        """Poll a job until it is completed, failed or cancelled.

        Raises ``FinancewolfError("job_wait_timeout")`` when ``timeout``
        seconds pass first; the job carries on. Its verdict is then read
        with ``result_v2(job["operation_id"])``.
        """
        deadline = clock() + timeout
        while True:
            job = self.job_v2(job_id)
            if job["status"] in JOB_TERMINAL:
                return job
            if clock() + interval > deadline:
                raise FinancewolfError("job_wait_timeout")
            sleep(interval)

    def submit_batch_v2(self, documents, *, idempotency_key=None):
        """Queue up to 100 validations as one batch.

        ``documents`` is a list of dicts: ``document`` (bytes) and any of
        ``media_type``, ``ruleset``, ``family``, ``variant``,
        ``document_type`` and ``scope``.
        """
        if not isinstance(documents, list) or not 1 <= len(documents) <= 100:
            raise FinancewolfError("invalid_batch")
        jobs = []
        for item in documents:
            if not isinstance(item, dict) or "document" not in item:
                raise FinancewolfError("invalid_batch")
            unknown = set(item) - {
                "document",
                "media_type",
                "ruleset",
                "family",
                "variant",
                "document_type",
                "scope",
            }
            if unknown:
                raise FinancewolfError("invalid_batch")
            jobs.append(
                _job_body(
                    item["document"],
                    item.get("media_type"),
                    item.get("ruleset", "latest"),
                    item.get("family"),
                    item.get("variant"),
                    item.get("document_type"),
                    item.get("scope"),
                )
            )
        batch = self._v2(
            "POST",
            "/batches",
            body=json.dumps({"jobs": jobs}).encode(),
            content_type="application/json",
            idempotency_key=idempotency_key,
            expect=(200, 202),
            timeout=None if self._timeout_explicit else PDF_TIMEOUT,
        )
        return _check_schema(batch, SCHEMA_BATCH, key="jobs")

    def batch_v2(self, batch_id):
        return _check_schema(
            self._v2("GET", "/batches/" + _check_id(batch_id)),
            SCHEMA_BATCH,
            key="jobs",
            id_value=batch_id,
        )

    def batches_v2(self, *, cursor=None, limit=None, api_version=None):
        query = _filters(cursor=cursor, limit=limit, api_version=api_version)
        return _check_schema(
            self._v2("GET", "/batches", query=query), SCHEMA_BATCH_LIST, key="batches"
        )

    def cancel_batch_v2(self, batch_id):
        return _check_schema(
            self._v2("POST", "/batches/" + _check_id(batch_id) + "/cancel"),
            SCHEMA_BATCH,
            key="jobs",
            id_value=batch_id,
        )

    # -- deliveries ---------------------------------------------------------

    def deliveries_v2(
        self,
        *,
        cursor=None,
        limit=None,
        destination=None,
        operation_id=None,
        status=None,
        api_version=None,
    ):
        """One page of webhook and S3 deliveries of V1 and V2 events."""
        query = _filters(
            cursor=cursor,
            limit=limit,
            destination=destination,
            operation_id=operation_id,
            delivery_status=status,
            api_version=api_version,
        )
        result = self._v2("GET", "/deliveries", query=query)
        return _check_schema(result, SCHEMA_DELIVERY_LIST, key="deliveries")

    def delivery_v2(self, delivery_id):
        """One delivery with its event as queued and every attempt made."""
        result = self._v2("GET", "/deliveries/" + _check_id(delivery_id))
        return _check_schema(result, SCHEMA_DELIVERY, key="history")

    def retry_delivery_v2(self, delivery_id):
        """Retry a failed delivery (needs finance:einvoices:destinations:manage)."""
        result = self._v2("POST", "/deliveries/" + _check_id(delivery_id) + "/retry")
        return _check_schema(result, SCHEMA_DELIVERY, key="history")


def _job_body(document, media_type, ruleset, family, variant, document_type, scope):
    media = _check_document(document, media_type)
    body = {
        "document_base64": base64.b64encode(document).decode("ascii"),
        "media_type": media,
    }
    options = _options(ruleset, family, variant, document_type, scope)
    if options:
        body["options"] = options
    return body


def _http_error(exc):
    """The API's problem code and request id, when both are well formed.

    Nothing else from the response is kept: a body can quote the request.
    """
    problem = request_id = None
    try:
        if (exc.headers.get("Content-Type") or "").split(";")[0].strip() == (
            "application/problem+json"
        ):
            raw = exc.read(MAX_PROBLEM + 1)
            doc = json.loads(raw) if len(raw) <= MAX_PROBLEM else {}
            code, rid = doc.get("code"), doc.get("request_id")
            if isinstance(code, str) and _PROBLEM_CODE.fullmatch(code):
                problem = code
            if isinstance(rid, str) and _REQUEST_ID.fullmatch(rid):
                request_id = rid
    except (OSError, ValueError, TypeError, AttributeError, RecursionError):
        pass
    finally:
        exc.close()
    return FinancewolfError(
        "api_http_error", status=exc.code, problem=problem, request_id=request_id
    )
