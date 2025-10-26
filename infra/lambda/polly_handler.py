"""Lambda handler für Stretch Coach Sprachsynthese.

Ruft Amazon Polly auf, um deutsche Sprachansagen als MP3 zu erzeugen
und liefert das Ergebnis base64-kodiert an API Gateway zurück.
"""
from __future__ import annotations

import base64
import json
import logging
import os
from typing import Any, Dict

import boto3
from botocore.exceptions import BotoCoreError, ClientError

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)

polly = boto3.client("polly")

DEFAULT_LANGUAGE = os.environ.get("DEFAULT_LANGUAGE", "de-DE")
DEFAULT_VOICE = os.environ.get("DEFAULT_VOICE", "Vicki")
MAX_TEXT_LENGTH = int(os.environ.get("MAX_TEXT_LENGTH", "1500"))


def _parse_body(event: Dict[str, Any]) -> Dict[str, Any]:
    """Extract and decode the JSON body for API Gateway REST/HTTP payloads."""
    body = event.get("body") or ""

    if not body:
        return {}

    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8")

    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise ValueError("Ungültiges JSON im Request Body") from exc


def _synthesize_speech(text: str, language: str, voice: str) -> bytes:
    """Invoke Amazon Polly and return the generated audio as bytes."""
    try:
        response = polly.synthesize_speech(
            Text=text,
            OutputFormat="mp3",
            VoiceId=voice,
            LanguageCode=language,
            Engine="standard",
        )
    except (BotoCoreError, ClientError) as exc:
        LOGGER.exception("Polly request failed")
        raise RuntimeError("Fehler bei der Sprachsynthese") from exc

    audio_stream = response.get("AudioStream")
    if audio_stream is None:
        raise RuntimeError("Polly lieferte keinen Audiostream")

    return audio_stream.read()


def _build_response(status_code: int, body: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": os.environ.get("CORS_ALLOW_ORIGIN", "*"),
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
            "Access-Control-Allow-Methods": "OPTIONS,POST",
        },
        "body": json.dumps(body, ensure_ascii=False),
    }


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    LOGGER.debug("Event received: %s", json.dumps(event))

    try:
        payload = _parse_body(event)
    except ValueError as exc:
        return _build_response(400, {"error": str(exc)})

    text = (payload.get("text") or "").strip()
    if not text:
        return _build_response(400, {"error": "Das Feld 'text' darf nicht leer sein."})

    if len(text) > MAX_TEXT_LENGTH:
        return _build_response(
            400,
            {"error": f"Text ist zu lang (maximal {MAX_TEXT_LENGTH} Zeichen)."},
        )

    language = (payload.get("language") or DEFAULT_LANGUAGE).strip() or DEFAULT_LANGUAGE
    voice = (payload.get("voice") or DEFAULT_VOICE).strip() or DEFAULT_VOICE

    try:
        audio_bytes = _synthesize_speech(text, language, voice)
    except RuntimeError as exc:
        return _build_response(502, {"error": str(exc)})

    base64_body = base64.b64encode(audio_bytes).decode("utf-8")

    return {
        "statusCode": 200,
        "isBase64Encoded": True,
        "headers": {
            "Content-Type": "audio/mpeg",
            "Access-Control-Allow-Origin": os.environ.get("CORS_ALLOW_ORIGIN", "*"),
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
            "Access-Control-Allow-Methods": "OPTIONS,POST",
        },
        "body": base64_body,
    }
