# Copyright 2023 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

"""Base class for FocusNFE NFSe operations."""

import json
import logging

import requests

from odoo import _, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

_MAX_LOG_BODY = 16000


class FocusnfeNfseBase(models.AbstractModel):
    """Base class for FocusNFE NFSe operations with shared HTTP request logic."""

    _name = "focusnfe.nfse.base"
    _description = "FocusNFE NFSE Base"

    def _focus_nfse_parse_error_response(self, response):
        """Return a readable message from Focus API error bodies (JSON or plain text)."""
        text = (response.text or "").strip()
        try:
            payload = response.json()
        except ValueError:
            return text[:8000] if text else ""

        if not isinstance(payload, dict):
            return str(payload)[:8000]

        parts = []
        codigo = payload.get("codigo")
        msg = payload.get("mensagem") or payload.get("message")
        if msg:
            parts.append(str(msg))

        for key in ("erro", "error", "detail"):
            val = payload.get(key)
            if val is not None and str(val) not in parts:
                parts.append(str(val))

        errs = payload.get("errors") or payload.get("erros")
        if isinstance(errs, list):
            for err in errs:
                if isinstance(err, dict):
                    sub = (
                        err.get("mensagem")
                        or err.get("message")
                        or err.get("description")
                    )
                    if sub:
                        parts.append(str(sub))
                elif err:
                    parts.append(str(err))

        out = " | ".join(parts) if parts else ""
        if codigo:
            out = f"{out} (codigo={codigo})" if out else f"(codigo={codigo})"

        if out:
            return out[:8000]
        try:
            return json.dumps(payload, ensure_ascii=False)[:8000]
        except (TypeError, ValueError):
            return text[:8000]

    def _focus_nfse_log_request(self, method, url, params, data):
        """Log outgoing request; token is only in HTTP Basic auth, not logged here."""
        if isinstance(data, str) and len(data) > _MAX_LOG_BODY:
            body = data[:_MAX_LOG_BODY] + "... [truncated]"
        else:
            body = data
        _logger.info(
            "FocusNFe %s %s | params=%s | body=%s",
            method,
            url,
            params,
            body,
        )

    def _make_focus_nfse_http_request(
        self, method, url, token, data=None, params=None, service_name="NFSe"
    ):
        """Perform a generic HTTP request.

        Args:
            method (str): The HTTP method to use (e.g., 'GET', 'POST').
            url (str): The URL to which the request is sent.
            token (str): The authentication token for the service.
            data (dict, optional): The payload to send in the request body.
                Defaults to None.
            params (dict, optional): The URL parameters to append to the URL.
                Defaults to None.
            service_name (str): Name of the service for error messages.

        Returns:
            requests.Response: The response object from the requests library.

        Raises:
            UserError: If the HTTP request fails with a 4xx/5xx response.
        """
        auth = (token, "")
        self._focus_nfse_log_request(method, url, params, data)
        try:
            response = requests.request(  # pylint: disable=external-request-timeout
                method,
                url,
                data=data,
                params=params,
                auth=auth,
            )
        except requests.RequestException as exc:
            _logger.exception("FocusNFe request failed: %s %s", method, url)
            raise UserError(
                _("Error communicating with %(service)s service: %(error)s")
                % {"service": service_name, "error": str(exc)}
            ) from exc

        if response.status_code < 400:
            return response

        focus_msg = self._focus_nfse_parse_error_response(response)
        _logger.warning(
            "FocusNFe HTTP %s %s | response_body=%s",
            response.status_code,
            url,
            focus_msg[:4000] if focus_msg else "(empty)",
        )

        if response.status_code == 422:
            raise UserError(
                _("Error communicating with %(service)s service: %(msg)s")
                % {"service": service_name, "msg": focus_msg}
            ) from None

        raise UserError(
            _(
                "Error communicating with %(service)s service "
                "(HTTP %(code)s): %(msg)s"
            )
            % {
                "service": service_name,
                "code": response.status_code,
                "msg": focus_msg or response.reason or "",
            }
        ) from None
