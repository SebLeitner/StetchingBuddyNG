"""Tests for the Polly Lambda handler without AWS dependencies."""

from __future__ import annotations

import sys
import types
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

# Provide lightweight stubs for boto3 and botocore so the module under test can
# be imported without the real AWS SDK.


class _FakeBoto3Module(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("boto3")
        self._client = None

    def set_client(self, client: Any) -> None:
        self._client = client

    def client(self, service_name: str) -> Any:  # pragma: no cover - import hook
        if self._client is None:
            raise RuntimeError("Fake boto3 client not configured")
        if service_name != "polly":
            raise ValueError(f"Unexpected service: {service_name}")
        return self._client


class _FakeBotocoreExceptions(types.ModuleType):
    class BotoCoreError(Exception):
        """Replacement for botocore.exceptions.BotoCoreError."""

    class ClientError(Exception):
        """Replacement for botocore.exceptions.ClientError."""


boto3_stub = _FakeBoto3Module()
botocore_exceptions_stub = _FakeBotocoreExceptions("botocore.exceptions")
botocore_module_stub = types.ModuleType("botocore")
botocore_module_stub.exceptions = botocore_exceptions_stub


class _PlaceholderClient:
    def describe_voices(self, **_: Any) -> Dict[str, Any]:  # pragma: no cover - safety net
        raise RuntimeError("Placeholder client should be replaced in tests")

    def synthesize_speech(self, **_: Any) -> Dict[str, Any]:  # pragma: no cover - safety net
        raise RuntimeError("Placeholder client should be replaced in tests")


boto3_stub.set_client(_PlaceholderClient())

sys.modules.setdefault("boto3", boto3_stub)
sys.modules.setdefault("botocore", botocore_module_stub)
sys.modules.setdefault("botocore.exceptions", botocore_exceptions_stub)

# Import the module under test after stubbing dependencies.
ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "infra" / "lambda"))

import polly_handler  # type: ignore  # noqa: E402


@dataclass
class FakePollyClient:
    describe_calls: List[Dict[str, Any]] = field(default_factory=list)
    synthesize_calls: List[Dict[str, Any]] = field(default_factory=list)
    describe_responses: List[Dict[str, Any]] = field(default_factory=list)
    synthesize_responses: List[Dict[str, Any]] = field(default_factory=list)

    def queue_describe(self, params: Dict[str, Any], response: Dict[str, Any]) -> None:
        self.describe_responses.append({"params": params, "response": response})

    def queue_synthesize(self, params: Dict[str, Any], response: Dict[str, Any]) -> None:
        self.synthesize_responses.append({"params": params, "response": response})

    def describe_voices(self, **kwargs: Any) -> Dict[str, Any]:
        if not self.describe_responses:
            raise AssertionError("Unexpected describe_voices call")
        expected = self.describe_responses.pop(0)
        assert kwargs == expected["params"], (kwargs, expected["params"])
        self.describe_calls.append(kwargs)
        return expected["response"]

    def synthesize_speech(self, **kwargs: Any) -> Dict[str, Any]:
        if not self.synthesize_responses:
            raise AssertionError("Unexpected synthesize_speech call")
        expected = self.synthesize_responses.pop(0)
        assert kwargs == expected["params"], (kwargs, expected["params"])
        self.synthesize_calls.append(kwargs)
        return expected["response"]


class FakeAudioStream:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data


def setup_function(_: object) -> None:
    polly_handler._supported_engines_for_voice.cache_clear()


def teardown_function(_: object) -> None:
    polly_handler._supported_engines_for_voice.cache_clear()


def test_synthesize_speech_uses_neural_engine_for_neural_only_voice() -> None:
    fake_client = FakePollyClient()
    fake_client.queue_describe({"VoiceId": "Daniel"}, {"Voices": [{"Id": "Daniel", "SupportedEngines": ["neural"]}]})
    fake_client.queue_synthesize(
        {
            "Text": "Hallo",
            "OutputFormat": "mp3",
            "VoiceId": "Daniel",
            "LanguageCode": "de-DE",
            "Engine": "neural",
        },
        {"AudioStream": FakeAudioStream(b"fake audio")},
    )

    polly_handler.polly = fake_client
    boto3_stub.set_client(fake_client)

    result = polly_handler._synthesize_speech("Hallo", "de-DE", "Daniel")

    assert result == b"fake audio"


def test_synthesize_speech_keeps_standard_for_standard_voice() -> None:
    fake_client = FakePollyClient()
    fake_client.queue_describe({"VoiceId": "Vicki"}, {"Voices": [{"Id": "Vicki", "SupportedEngines": ["standard"]}]})
    fake_client.queue_synthesize(
        {
            "Text": "Hi",
            "OutputFormat": "mp3",
            "VoiceId": "Vicki",
            "LanguageCode": "de-DE",
        },
        {"AudioStream": FakeAudioStream(b"standard audio")},
    )

    polly_handler.polly = fake_client
    boto3_stub.set_client(fake_client)

    result = polly_handler._synthesize_speech("Hi", "de-DE", "Vicki")

    assert result == b"standard audio"
