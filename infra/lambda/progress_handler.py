"""Lambda-Handler zum Verarbeiten von Stretch-Coach-Übungsfortschritten."""
from __future__ import annotations

import datetime as dt
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

_TABLE_NAME = os.environ.get("PROGRESS_TABLE_NAME")
if not _TABLE_NAME:
    raise RuntimeError("PROGRESS_TABLE_NAME ist nicht konfiguriert")

dynamodb = boto3.resource("dynamodb")
progress_table = dynamodb.Table(_TABLE_NAME)

DEFAULT_LIST_LIMIT = 250
MAX_LIST_LIMIT = 500


def _normalize_optional_string(value: Any, field_name: str) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise HttpError(400, f"'{field_name}' muss eine Zeichenkette sein")
    stripped = value.strip()
    return stripped or None


def _parse_iso_timestamp(value: Any, field_name: str) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise HttpError(400, f"'{field_name}' muss ein ISO-8601 String sein")
    trimmed = value.strip()
    if not trimmed:
        return None
    try:
        # Unterstützt sowohl "...Z" als auch Offsets
        parsed = dt.datetime.fromisoformat(trimmed.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HttpError(400, f"'{field_name}' ist kein gültiger ISO-8601 Zeitstempel") from exc
    return parsed.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _utc_now_iso() -> str:
    return dt.datetime.now(tz=dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _extract_duration(payload: Dict[str, Any]) -> Optional[int]:
    if "durationMs" not in payload:
        return None
    duration = payload.get("durationMs")
    if duration is None:
        return None
    if isinstance(duration, bool) or not isinstance(duration, int):
        raise HttpError(400, "'durationMs' muss eine Ganzzahl sein")
    if duration < 0:
        raise HttpError(400, "'durationMs' darf nicht negativ sein")
    return duration


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
    return [
        {key: _coerce_dynamodb_value(value) for key, value in item.items()}
        for item in items
    ]


def _parse_limit(event: Mapping[str, Any]) -> int:
    params = event.get("queryStringParameters") or {}
    raw_limit = params.get("limit") if isinstance(params, dict) else None
    if raw_limit in (None, ""):
        return DEFAULT_LIST_LIMIT
    try:
        limit = int(raw_limit)
    except (TypeError, ValueError):
        raise HttpError(400, "'limit' muss eine Ganzzahl sein")
    if limit <= 0:
        raise HttpError(400, "'limit' muss größer als 0 sein")
    return min(limit, MAX_LIST_LIMIT)


def _list_progress_entries(event: Mapping[str, Any]) -> Dict[str, Any]:
    limit = _parse_limit(event)
    items: List[Dict[str, Any]] = []
    exclusive_start_key = None

    while len(items) < limit:
        page_size = max(1, min(limit - len(items), 100))
        scan_kwargs: Dict[str, Any] = {"Limit": page_size}
        if exclusive_start_key:
            scan_kwargs["ExclusiveStartKey"] = exclusive_start_key

        response = progress_table.scan(**scan_kwargs)
        page_items = response.get("Items", [])
        items.extend(_sanitize_items(page_items))

        exclusive_start_key = response.get("LastEvaluatedKey")
        if not exclusive_start_key:
            break

    items.sort(key=lambda item: item.get("completed_at") or "", reverse=True)
    return json_response(200, {"items": items[:limit]})


def _store_progress_entry(event: Mapping[str, Any]) -> Dict[str, Any]:
    payload = parse_json_body(event)
    client_id = expect_string(payload.get("clientId"), "clientId")
    exercise_id = expect_string(payload.get("exerciseId"), "exerciseId")
    total_sets = expect_positive_int(payload.get("totalSets"), "totalSets")
    sets_completed = expect_positive_int(payload.get("setsCompleted"), "setsCompleted")

    if sets_completed < total_sets:
        raise HttpError(400, "Die Übung wurde nicht vollständig abgeschlossen")

    duration_ms = _extract_duration(payload)
    exercise_name = _normalize_optional_string(payload.get("exerciseName"), "exerciseName")
    rep_time = payload.get("repTime")
    rest_time = payload.get("restTime")
    prep_time = payload.get("prepTime")
    if rep_time is not None:
        rep_time = expect_positive_int(rep_time, "repTime")
    if rest_time is not None:
        rest_time = expect_non_negative_int(rest_time, "restTime")
    if prep_time is not None:
        prep_time = expect_non_negative_int(prep_time, "prepTime")

    started_at = _parse_iso_timestamp(payload.get("startedAt"), "startedAt")
    finished_at = _parse_iso_timestamp(payload.get("finishedAt"), "finishedAt")

    item: Dict[str, Any] = {
        "client_id": client_id,
        "completed_at": _utc_now_iso(),
        "exercise_id": exercise_id,
        "total_sets": total_sets,
        "sets_completed": sets_completed,
    }

    if exercise_name:
        item["exercise_name"] = exercise_name
    if duration_ms is not None:
        item["duration_ms"] = duration_ms
    if rep_time is not None:
        item["rep_time_seconds"] = rep_time
    if rest_time is not None:
        item["rest_time_seconds"] = rest_time
    if prep_time is not None:
        item["prep_time_seconds"] = prep_time
    if started_at is not None:
        item["started_at"] = started_at
    if finished_at is not None:
        item["finished_at"] = finished_at

    try:
        progress_table.put_item(Item=item)
    except (BotoCoreError, ClientError) as exc:  # pragma: no cover - AWS client errors
        LOGGER.exception("Speichern des Übungsfortschritts fehlgeschlagen")
        raise HttpError(502, "Übungsfortschritt konnte nicht gespeichert werden") from exc

    return json_response(201, {"status": "stored", "completedAt": item["completed_at"]})


@with_error_handling
def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    method = (
        event.get("requestContext", {})
        .get("http", {})
        .get("method", "")
        .upper()
    )
    if method == "OPTIONS":
        return json_response(200, {"status": "ok"})
    if method == "GET":
        return _list_progress_entries(event)
    if method == "POST":
        return _store_progress_entry(event)

    raise HttpError(405, "Methode wird nicht unterstützt")
