"""Lambda handler für Stretch Coach Sprachsynthese."""
from __future__ import annotations

import logging
import os
from typing import Any, Dict

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from lambda_utils import HttpError, binary_response, parse_json_body, with_error_handling

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)

polly = boto3.client("polly")

DEFAULT_LANGUAGE = os.environ.get("DEFAULT_LANGUAGE", "de-DE")
DEFAULT_VOICE = os.environ.get("DEFAULT_VOICE", "Vicki")
MAX_TEXT_LENGTH = int(os.environ.get("MAX_TEXT_LENGTH", "1500"))


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
    except (BotoCoreError, ClientError) as exc:  # pragma: no cover - AWS client errors
        LOGGER.exception("Polly request failed")
        raise HttpError(502, "Fehler bei der Sprachsynthese") from exc

    audio_stream = response.get("AudioStream")
    if audio_stream is None:
        raise HttpError(502, "Polly lieferte keinen Audiostream")

    return audio_stream.read()


@with_error_handling
def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    LOGGER.debug("Event received: %s", event)

    payload = parse_json_body(event)

    text = (payload.get("text") or "").strip()
    if not text:
        raise HttpError(400, "Das Feld 'text' darf nicht leer sein.")

    if len(text) > MAX_TEXT_LENGTH:
        raise HttpError(400, f"Text ist zu lang (maximal {MAX_TEXT_LENGTH} Zeichen).")

    language = (payload.get("language") or DEFAULT_LANGUAGE).strip() or DEFAULT_LANGUAGE
    voice = (payload.get("voice") or DEFAULT_VOICE).strip() or DEFAULT_VOICE

    audio_bytes = _synthesize_speech(text, language, voice)

    return binary_response(200, audio_bytes, mime_type="audio/mpeg")
