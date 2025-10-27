"""Lambda handler für Stretch Coach Sprachsynthese."""
from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Any, Dict, Optional, Set

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from lambda_utils import HttpError, binary_response, parse_json_body, with_error_handling

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)

polly = boto3.client("polly")

DEFAULT_LANGUAGE = os.environ.get("DEFAULT_LANGUAGE", "de-DE")
DEFAULT_VOICE = os.environ.get("DEFAULT_VOICE", "Vicki")
MAX_TEXT_LENGTH = int(os.environ.get("MAX_TEXT_LENGTH", "1500"))


@lru_cache(maxsize=256)
def _supported_engines_for_voice(voice: str) -> Set[str]:
    """Return the supported engines for the requested voice."""
    try:
        response = polly.describe_voices(VoiceId=voice)
    except (BotoCoreError, ClientError):  # pragma: no cover - AWS client errors
        LOGGER.warning("DescribeVoices failed for voice %s", voice, exc_info=True)
        return set()

    voices = response.get("Voices") or []
    if not voices:
        LOGGER.warning("DescribeVoices returned no data for voice %s", voice)
        return set()

    supported_engines = voices[0].get("SupportedEngines") or []
    return set(supported_engines)


def _select_engine(voice: str) -> Optional[str]:
    """Determine the appropriate Polly engine for the given voice."""

    engines = _supported_engines_for_voice(voice)
    if not engines or "standard" in engines:
        return None

    if "neural" in engines:
        return "neural"

    return None


def _should_retry_with_neural(error: ClientError, voice: str) -> bool:
    """Determine whether retrying the request with the neural engine makes sense."""

    error_response = getattr(error, "response", {}) or {}
    error_info = error_response.get("Error") or {}
    error_code = str(error_info.get("Code", "")).strip().lower()
    error_message = str(error_info.get("Message", "")).strip().lower()
    normalized_voice = voice.strip().lower()

    if not normalized_voice:
        return False

    neural_hint_codes = {"invalidparametercombination", "enginenotsupportedexception"}
    if error_code in neural_hint_codes:
        return True

    if "neural" in error_message:
        return True

    # Some AWS accounts report standard support even though only neural works.
    if normalized_voice in {"daniel", "hannah", "vicki"}:
        # Vicki is kept for completeness; the retry will only trigger on failures.
        return True

    return False


def _invoke_polly(params: Dict[str, Any]) -> Dict[str, Any]:
    """Call Polly with the provided parameters."""

    return polly.synthesize_speech(**params)


def _synthesize_speech(text: str, language: str, voice: str) -> bytes:
    """Invoke Amazon Polly and return the generated audio as bytes."""

    engine = _select_engine(voice)
    base_params = {
        "Text": text,
        "OutputFormat": "mp3",
        "VoiceId": voice,
        "LanguageCode": language,
    }
    params = dict(base_params)
    if engine:
        params["Engine"] = engine

    LOGGER.debug(
        "Calling Polly: voice=%s language=%s engine=%s text_length=%d",
        voice,
        language,
        params.get("Engine", "standard"),
        len(text),
    )

    try:
        response = _invoke_polly(params)
    except ClientError as exc:  # pragma: no cover - AWS client errors
        LOGGER.debug(
            "Polly ClientError response: %s",
            getattr(exc, "response", {}),
            exc_info=True,
        )
        if not engine and _should_retry_with_neural(exc, voice):
            retry_params = dict(base_params)
            retry_params["Engine"] = "neural"
            try:
                LOGGER.info(
                    "Retrying Polly request for voice %s with neural engine after failure.",
                    voice,
                )
                response = _invoke_polly(retry_params)
            except (BotoCoreError, ClientError) as retry_exc:  # pragma: no cover - AWS client errors
                LOGGER.debug(
                    "Retry Polly error response: %s",
                    getattr(retry_exc, "response", {}),
                    exc_info=True,
                )
                LOGGER.exception("Polly retry with neural engine failed")
                raise HttpError(502, "Fehler bei der Sprachsynthese") from retry_exc
        else:
            LOGGER.exception("Polly request failed")
            raise HttpError(502, "Fehler bei der Sprachsynthese") from exc
    except BotoCoreError as exc:  # pragma: no cover - AWS client errors
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
