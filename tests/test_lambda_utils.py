"""Tests for shared Lambda utility helpers."""
import importlib
import sys
from pathlib import Path


MODULE_PATH = "lambda_utils"
ROOT = Path(__file__).resolve().parents[1]
LAMBDA_DIR = ROOT / "infra" / "lambda"
if str(LAMBDA_DIR) not in sys.path:
    sys.path.append(str(LAMBDA_DIR))


def _reload_lambda_utils():
    sys.modules.pop(MODULE_PATH, None)
    return importlib.import_module(MODULE_PATH)


def test_default_cors_methods_include_write_operations(monkeypatch):
    """The default CORS headers should allow all verbs used by the APIs."""
    monkeypatch.delenv("CORS_ALLOW_METHODS", raising=False)

    module = _reload_lambda_utils()
    response = module.json_response(200, {"status": "ok"})

    allowed = response["headers"].get("Access-Control-Allow-Methods")
    assert allowed is not None

    verbs = {verb.strip().upper() for verb in allowed.split(",")}
    assert {"OPTIONS", "GET", "POST", "PUT", "DELETE"}.issubset(verbs)


