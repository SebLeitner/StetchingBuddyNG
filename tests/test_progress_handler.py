import importlib
import json
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAMBDA_DIR = ROOT / "infra" / "lambda"
if str(LAMBDA_DIR) not in sys.path:
    sys.path.append(str(LAMBDA_DIR))


class FakeProgressTable:
    def __init__(self) -> None:
        self.put_calls = []
        self.delete_calls = []

    def put_item(self, Item):  # noqa: N802 - match boto3 signature
        self.put_calls.append(Item)

    def delete_item(self, **kwargs):  # noqa: ANN003 - boto3 style kwargs
        self.delete_calls.append(kwargs)


class FakeDynamoResource:
    def __init__(self, table: FakeProgressTable) -> None:
        self.table = table
        self.last_table_name = None

    def Table(self, name: str):  # noqa: N802 - match boto3 signature
        self.last_table_name = name
        return self.table


class FakeClientError(Exception):
    def __init__(self, response=None):
        super().__init__("client error")
        self.response = response or {}


def _install_boto_stubs(table: FakeProgressTable, monkeypatch) -> None:
    dynamo_resource = FakeDynamoResource(table)
    boto3_stub = types.ModuleType("boto3")
    boto3_stub.resource = lambda service: dynamo_resource if service == "dynamodb" else None

    botocore_exceptions = types.ModuleType("botocore.exceptions")
    botocore_exceptions.BotoCoreError = Exception
    botocore_exceptions.ClientError = FakeClientError

    botocore_module = types.ModuleType("botocore")
    botocore_module.exceptions = botocore_exceptions

    sys.modules["boto3"] = boto3_stub
    sys.modules["botocore"] = botocore_module
    sys.modules["botocore.exceptions"] = botocore_exceptions


def _reload_progress_handler(table: FakeProgressTable, monkeypatch):
    _install_boto_stubs(table, monkeypatch)
    monkeypatch.setenv("PROGRESS_TABLE_NAME", "test-table")
    sys.modules.pop("progress_handler", None)
    return importlib.import_module("progress_handler")


def test_store_progress_uses_finished_time_for_completion(monkeypatch):
    table = FakeProgressTable()
    module = _reload_progress_handler(table, monkeypatch)

    payload = {
        "clientId": "user-1",
        "exerciseId": "kieser-training",
        "totalSets": 1,
        "setsCompleted": 1,
        "durationMs": 45 * 60 * 1000,
        "startedAt": "2024-07-09T12:00:00+02:00",
        "finishedAt": "2024-07-09T12:45:00+02:00",
    }

    event = {
        "requestContext": {"http": {"method": "POST"}},
        "body": json.dumps(payload),
    }

    response = module.lambda_handler(event, None)

    assert response["statusCode"] == 201
    assert len(table.put_calls) == 1
    stored = table.put_calls[0]
    assert stored["completed_at"] == "2024-07-09T10:45:00Z"
    assert stored["finished_at"] == "2024-07-09T10:45:00Z"


def test_delete_progress_accepts_query_parameters(monkeypatch):
    table = FakeProgressTable()
    module = _reload_progress_handler(table, monkeypatch)

    event = {
        "requestContext": {"http": {"method": "DELETE"}},
        "queryStringParameters": {
            "clientId": "user-1",
            "completedAt": "2024-07-09T10:45:00Z",
        },
    }

    response = module.lambda_handler(event, None)

    assert response["statusCode"] == 200
    assert table.delete_calls == [
        {
            "Key": {"client_id": "user-1", "completed_at": "2024-07-09T10:45:00Z"},
            "ConditionExpression": "attribute_exists(client_id) AND attribute_exists(completed_at)",
        }
    ]
