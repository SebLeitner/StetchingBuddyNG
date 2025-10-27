"""Shared helpers for Lambda HTTP handlers with consistent CORS headers."""
from __future__ import annotations

import base64
import json
import logging
import os
from typing import Any, Callable, Dict, Iterable, Mapping, Optional

LOGGER = logging.getLogger(__name__)


class HttpError(Exception):
    """Exception indicating a handled HTTP error response."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def _cors_headers() -> Dict[str, str]:
    allowed_origin = os.environ.get("CORS_ALLOW_ORIGIN", "*")
    allowed_methods = os.environ.get(
        "CORS_ALLOW_METHODS", "OPTIONS,POST,GET,PUT,DELETE"
    )
    allowed_headers = os.environ.get(
        "CORS_ALLOW_HEADERS",
        "Content-Type,Authorization,X-Amz-Date,X-Amz-Security-Token,X-Api-Key",
    )
    return {
        "Access-Control-Allow-Origin": allowed_origin,
        "Access-Control-Allow-Headers": allowed_headers,
        "Access-Control-Allow-Methods": allowed_methods,
    }


def _merge_headers(base: Mapping[str, str], extra: Optional[Mapping[str, str]] = None) -> Dict[str, str]:
    headers: Dict[str, str] = dict(base)
    if extra:
        headers.update({k: v for k, v in extra.items() if v is not None})
    return headers


def json_response(
    status_code: int,
    body: Mapping[str, Any],
    headers: Optional[Mapping[str, str]] = None,
) -> Dict[str, Any]:
    base_headers = _cors_headers()
    base_headers.setdefault("Content-Type", "application/json")
    payload = json.dumps(body, ensure_ascii=False)
    return {
        "statusCode": status_code,
        "headers": _merge_headers(base_headers, headers),
        "body": payload,
    }


def text_response(
    status_code: int,
    body: str,
    headers: Optional[Mapping[str, str]] = None,
) -> Dict[str, Any]:
    base_headers = _cors_headers()
    base_headers.setdefault("Content-Type", "text/plain; charset=utf-8")
    return {
        "statusCode": status_code,
        "headers": _merge_headers(base_headers, headers),
        "body": body,
    }


def binary_response(
    status_code: int,
    body: bytes,
    *,
    headers: Optional[Mapping[str, str]] = None,
    mime_type: str = "application/octet-stream",
) -> Dict[str, Any]:
    base_headers = _cors_headers()
    base_headers.setdefault("Content-Type", mime_type)
    encoded_body = base64.b64encode(body).decode("utf-8") if isinstance(body, bytes) else body
    return {
        "statusCode": status_code,
        "headers": _merge_headers(base_headers, headers),
        "isBase64Encoded": True,
        "body": encoded_body,
    }


def parse_json_body(event: Mapping[str, Any]) -> Dict[str, Any]:
    """Decode the JSON body of an API Gateway event."""
    body = event.get("body") or ""
    if not body:
        return {}

    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8")

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive
        raise HttpError(400, "Ungültiges JSON im Request-Body") from exc

    if not isinstance(parsed, dict):
        raise HttpError(400, "Request-Body muss ein JSON-Objekt sein")

    return parsed


HandlerFunc = Callable[[Mapping[str, Any], Any], Dict[str, Any]]


def with_error_handling(handler: HandlerFunc) -> HandlerFunc:
    """Wrap Lambda handlers to ensure JSON error responses with CORS headers."""

    def wrapper(event: Mapping[str, Any], context: Any) -> Dict[str, Any]:
        try:
            return handler(event, context)
        except HttpError as exc:
            LOGGER.info("HttpError: %s", exc)
            return json_response(exc.status_code, {"error": exc.message})
        except Exception:  # pragma: no cover - defensive safety net
            LOGGER.exception("Unhandled error in Lambda handler")
            return json_response(500, {"error": "Interner Serverfehler"})

    return wrapper


def expect_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HttpError(400, f"'{field_name}' muss eine nicht-leere Zeichenkette sein")
    return value.strip()


def expect_positive_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise HttpError(400, f"'{field_name}' muss eine Ganzzahl sein")
    if value <= 0:
        raise HttpError(400, f"'{field_name}' muss größer als 0 sein")
    return value


def expect_non_negative_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise HttpError(400, f"'{field_name}' muss eine Ganzzahl sein")
    if value < 0:
        raise HttpError(400, f"'{field_name}' darf nicht negativ sein")
    return value
