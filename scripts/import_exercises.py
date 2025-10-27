#!/usr/bin/env python3
"""Hilfsskript zum Importieren der Übungen aus der historischen JSON-Datei."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List

import boto3

DEFAULT_SOURCE = Path(__file__).resolve().parents[1] / "frontend" / "exercises.json"


def _is_test_exercise(exercise_id: str) -> bool:
    normalized = exercise_id.strip().lower()
    return normalized in {"test", "test übung", "testübung"}


def _load_exercises(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError("Die Quelldatei enthält kein JSON-Array")
    return [entry for entry in data if isinstance(entry, dict)]


def _prepare_item(entry: Dict[str, Any]) -> Dict[str, Any]:
    exercise_id = str(entry.get("id", "")).strip()
    if not exercise_id:
        raise ValueError("Eintrag ohne 'id' gefunden")
    if _is_test_exercise(exercise_id):
        raise ValueError("Test-Übungen dürfen nicht importiert werden")

    item: Dict[str, Any] = {"exercise_id": exercise_id, "id": exercise_id}
    for key, value in entry.items():
        if key in {"exercise_id", "id"}:
            continue
        if value is None:
            continue
        item[key] = value
    return item


def _chunk(entries: Iterable[Dict[str, Any]], size: int = 25) -> Iterable[List[Dict[str, Any]]]:
    chunk: List[Dict[str, Any]] = []
    for entry in entries:
        chunk.append(entry)
        if len(chunk) >= size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "source",
        nargs="?",
        type=Path,
        default=DEFAULT_SOURCE,
        help="Pfad zur exercises.json (Standard: frontend/exercises.json)",
    )
    parser.add_argument(
        "--table",
        dest="table_name",
        default=os.environ.get("EXERCISES_TABLE_NAME"),
        help="Name der DynamoDB-Tabelle (Standard: Umgebungsvariable EXERCISES_TABLE_NAME)",
    )
    parser.add_argument(
        "--region",
        default=os.environ.get("AWS_REGION"),
        help="AWS-Region (optional)",
    )

    args = parser.parse_args()

    if not args.table_name:
        raise SystemExit("Bitte den Tabellennamen via --table oder EXERCISES_TABLE_NAME angeben.")

    source_path: Path = args.source
    if not source_path.exists():
        raise SystemExit(f"Quelldatei {source_path} wurde nicht gefunden.")

    raw_entries = _load_exercises(source_path)
    items = [_prepare_item(entry) for entry in raw_entries if not _is_test_exercise(str(entry.get("id", "")))]

    session_kwargs = {}
    if args.region:
        session_kwargs["region_name"] = args.region
    dynamodb = boto3.resource("dynamodb", **session_kwargs)
    table = dynamodb.Table(args.table_name)

    imported = 0
    for batch in _chunk(items):
        with table.batch_writer(overwrite_by_pkeys=["exercise_id"]) as writer:
            for item in batch:
                writer.put_item(Item=item)
                imported += 1

    print(f"✅ {imported} Übungen importiert.")


if __name__ == "__main__":
    main()
