"""Lambda-Handler zum Verwalten der Stretch-Coach-Übungen."""
from __future__ import annotations

import logging
import os
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Mapping, Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from lambda_utils import (
    HttpError,
    expect_non_negative_int,
    expect_positive_int,
    expect_string,
    json_response,
    parse_json_body,
    with_error_handling,
)

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)

_TABLE_NAME = os.environ.get("EXERCISES_TABLE_NAME")
if not _TABLE_NAME:
    raise RuntimeError("EXERCISES_TABLE_NAME ist nicht konfiguriert")

dynamodb = boto3.resource("dynamodb")
exercises_table = dynamodb.Table(_TABLE_NAME)

OPTIONAL_STRING_FIELDS = ["mindfulness", "break_bell"]
OPTIONAL_INT_FIELDS = ["prep_time", "duration", "rep_time", "rest_time"]
REQUIRED_POSITIVE_INT_FIELDS = ["sets"]


def _coerce_dynamodb_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        if value % 1 == 0:
            return int(value)
        return float(value)
    if isinstance(value, list):
        return [_coerce_dynamodb_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _coerce_dynamodb_value(val) for key, val in value.items()}
    return value


def _sanitize_items(items: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    sanitized: List[Dict[str, Any]] = []
    for item in items:
        normalized = {
            key: _coerce_dynamodb_value(value)
            for key, value in item.items()
            if key != "exercise_id"
        }
        sanitized.append(normalized)
    return sanitized


def _normalize_optional_string(value: Any, field_name: str) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise HttpError(400, f"'{field_name}' muss eine Zeichenkette sein")
    stripped = value.strip()
    return stripped or None


def _parse_optional_int(value: Any, field_name: str, *, positive: bool = False) -> Optional[int]:
    if value in (None, ""):
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise HttpError(400, f"'{field_name}' muss eine Ganzzahl sein")
    if positive:
        return expect_positive_int(value, field_name)
    return expect_non_negative_int(value, field_name)


def _is_test_exercise(exercise_id: str) -> bool:
    normalized = exercise_id.strip().lower()
    return normalized in {"test", "test übung", "testübung"}


def _build_item(payload: Mapping[str, Any]) -> Dict[str, Any]:
    exercise_id = expect_string(payload.get("id"), "id")
    if _is_test_exercise(exercise_id):
        raise HttpError(400, "Test-Übungen können nicht in der Datenbank gespeichert werden")

    item: Dict[str, Any] = {
        "exercise_id": exercise_id,
        "id": exercise_id,
        "name": expect_string(payload.get("name"), "name"),
        "instruction": expect_string(payload.get("instruction"), "instruction"),
    }

    for field in OPTIONAL_STRING_FIELDS:
        normalized = _normalize_optional_string(payload.get(field), field)
        if normalized is not None:
            item[field] = normalized

    for field in OPTIONAL_INT_FIELDS:
        parsed = _parse_optional_int(payload.get(field), field)
        if parsed is not None:
            item[field] = parsed

    for field in REQUIRED_POSITIVE_INT_FIELDS:
        parsed = _parse_optional_int(payload.get(field), field, positive=True)
        if parsed is not None:
            item[field] = parsed

    if "sets" not in item:
        raise HttpError(400, "'sets' muss angegeben werden")

    return item


def _list_exercises() -> Dict[str, Any]:
    try:
        response = exercises_table.scan()
    except (BotoCoreError, ClientError) as exc:  # pragma: no cover - AWS client errors
        LOGGER.exception("Scan der Übungs-Tabelle fehlgeschlagen")
        raise HttpError(502, "Übungen konnten nicht geladen werden") from exc

    raw_items = response.get("Items", [])
    sanitized = [
        item
        for item in _sanitize_items(raw_items)
        if item.get("id") and not _is_test_exercise(str(item["id"]))
    ]
    sanitized.sort(key=lambda entry: (entry.get("name") or "").lower())
    return json_response(200, {"items": sanitized, "count": len(sanitized)})


def _get_exercise(exercise_id: str) -> Dict[str, Any]:
    try:
        response = exercises_table.get_item(Key={"exercise_id": exercise_id})
    except (BotoCoreError, ClientError) as exc:  # pragma: no cover - AWS client errors
        LOGGER.exception("Laden der Übung %s fehlgeschlagen", exercise_id)
        raise HttpError(502, "Übung konnte nicht geladen werden") from exc

    item = response.get("Item")
    if not item or _is_test_exercise(item.get("id", "")):
        raise HttpError(404, "Übung wurde nicht gefunden")

    sanitized = _sanitize_items([item])[0]
    return json_response(200, {"item": sanitized})


def _create_exercise(payload: Mapping[str, Any]) -> Dict[str, Any]:
    item = _build_item(payload)

    try:
        exercises_table.put_item(
            Item=item,
            ConditionExpression="attribute_not_exists(exercise_id)",
        )
    except ClientError as exc:  # pragma: no cover - AWS client errors
        error_code = exc.response.get("Error", {}).get("Code")
        if error_code == "ConditionalCheckFailedException":
            raise HttpError(409, "Es existiert bereits eine Übung mit dieser ID") from exc
        LOGGER.exception("Speichern der Übung %s fehlgeschlagen", item["id"])
        raise HttpError(502, "Übung konnte nicht gespeichert werden") from exc
    except BotoCoreError as exc:  # pragma: no cover - AWS client errors
        LOGGER.exception("Speichern der Übung %s fehlgeschlagen", item["id"])
        raise HttpError(502, "Übung konnte nicht gespeichert werden") from exc

    sanitized = _sanitize_items([item])[0]
    return json_response(201, {"item": sanitized})


def _update_exercise(path_id: str, payload: Mapping[str, Any]) -> Dict[str, Any]:
    item = _build_item(payload)
    previous_id = payload.get("previousId") or path_id

    try:
        exercises_table.put_item(Item=item)
    except (BotoCoreError, ClientError) as exc:  # pragma: no cover - AWS client errors
        LOGGER.exception("Aktualisierung der Übung %s fehlgeschlagen", path_id)
        raise HttpError(502, "Übung konnte nicht aktualisiert werden") from exc

    if previous_id and previous_id != item["id"]:
        try:
            exercises_table.delete_item(Key={"exercise_id": previous_id})
        except (BotoCoreError, ClientError):  # pragma: no cover - best effort cleanup
            LOGGER.warning(
                "Alte Übungs-ID %s konnte nach dem Umbenennen nicht gelöscht werden",
                previous_id,
            )

    sanitized = _sanitize_items([item])[0]
    return json_response(200, {"item": sanitized})


def _delete_exercise(exercise_id: str) -> Dict[str, Any]:
    if _is_test_exercise(exercise_id):
        raise HttpError(404, "Übung wurde nicht gefunden")

    try:
        response = exercises_table.delete_item(
            Key={"exercise_id": exercise_id},
            ReturnValues="ALL_OLD",
        )
    except (BotoCoreError, ClientError) as exc:  # pragma: no cover - AWS client errors
        LOGGER.exception("Löschen der Übung %s fehlgeschlagen", exercise_id)
        raise HttpError(502, "Übung konnte nicht gelöscht werden") from exc

    if "Attributes" not in response:
        raise HttpError(404, "Übung wurde nicht gefunden")

    return json_response(204, {"status": "deleted"})


@with_error_handling
def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    request_context = event.get("requestContext", {})
    http = request_context.get("http", {})
    method = (http.get("method") or "").upper()
    path_params = event.get("pathParameters") or {}
    exercise_id = path_params.get("exercise_id")

    if method == "OPTIONS":
        return json_response(200, {"status": "ok"})
    if method == "GET" and exercise_id:
        return _get_exercise(exercise_id)
    if method == "GET":
        return _list_exercises()
    if method == "POST":
        payload = parse_json_body(event)
        return _create_exercise(payload)
    if method == "PUT" and exercise_id:
        payload = parse_json_body(event)
        if not payload:
            raise HttpError(400, "Request-Body fehlt")
        return _update_exercise(exercise_id, payload)
    if method == "DELETE" and exercise_id:
        return _delete_exercise(exercise_id)

    raise HttpError(405, "Methode wird nicht unterstützt")
