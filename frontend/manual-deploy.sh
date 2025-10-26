#!/usr/bin/env bash
set -euo pipefail

# ============================================
# Manual Deployment Helper for Stretch Coach
# ============================================
# Lädt Umgebungsvariablen aus .env (via env-set.sh)
# und ruft dann das eigentliche Deploy-Skript auf.
# ============================================

ENV_FILE="${1:-.env}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🚀 Starte manuelles Deployment ..."
echo "📄 Verwende Env-Datei: ${ENV_FILE}"
echo

# 1. Environment laden
if ! "${SCRIPT_DIR}/env-set.sh" "${ENV_FILE}"; then
  echo "❌ Fehler beim Laden der Umgebungsvariablen."
  exit 1
fi

# 2. Deployment starten
echo
echo "=== 📦 Starte Upload & Invalidation ==="
if bash "${SCRIPT_DIR}/frontend/deploy.sh"; then
  echo
  echo "✅ Deployment erfolgreich abgeschlossen!"
  echo "   App-URL: https://${S3_BUCKET}/"
else
  echo
  echo "❌ Deployment fehlge
