"""Errors and transport pieces shared by the V1 and V2 clients."""

import urllib.request

VERSION = "2.1.0"


class IronfangFinanceError(Exception):
    """A client/service failure, never an invalid invoice verdict.

    ``problem`` and ``request_id`` are set when the API answered with an
    RFC 9457 problem whose code and request id are well formed. A billing
    refusal (for example ``free_allowance_exhausted``) also sets ``product``,
    ``meter`` and, for a free allowance, ``reset_at`` (RFC 3339).
    ``retry_after`` is the wait in seconds the API asked for, when it said.
    """

    def __init__(
        self,
        code,
        *,
        status=0,
        problem=None,
        request_id=None,
        product=None,
        meter=None,
        reset_at=None,
        retry_after=None,
    ):
        self.code = code
        self.status = status
        self.problem = problem
        self.request_id = request_id
        self.product = product
        self.meter = meter
        self.reset_at = reset_at
        self.retry_after = retry_after
        detail = ", ".join(
            part for part in (f"HTTP {status}" if status else "", problem or "") if part
        )
        super().__init__(f"Ironfang Finance: {code}" + (f" ({detail})" if detail else ""))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None
