#!/usr/bin/env bash
set -euo pipefail

# ==================================================
# Environment Loader for Frontend Deployments
# ==================================================
# Lädt Variablen aus einer .env-Datei im Projektverzeichnis
# und exportiert sie für deploy.sh oder andere Skripte.
# Beispiel-Aufruf:
#   source ./env-set.sh   oder   ./env-set.sh && ./frontend/deploy.sh
# ==================================================

ENV_FILE="${1:-.env}"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "❌ Keine ${ENV_FILE} gefunden. Bitte Datei mit Key=Value Zeilen erstellen."
  echo "   Beispiel:"
  echo "     AWS_REGION=eu-west-1"
  echo "     S3_BUCKET=sbuddy.leitnersoft.com"
  echo "     CLOUDFRONT_DISTRIBUTION_ID=E300U192H6ZHKW"
  exit 1
fi

echo "=== 🔧 Lade Umgebungsvariablen aus ${ENV_FILE} ==="

# shellcheck disable=SC2163
export $(grep -v '^#' "${ENV_FILE}" | xargs)

echo "✅ Folgende Variablen sind nun aktiv:"
echo "  AWS_REGION=${AWS_REGION}"
echo "  S3_BUCKET=${S3_BUCKET}"
echo "  CLOUDFRONT_DISTRIBUTION_ID=${CLOUDFRONT_DISTRIBUTION_ID}"
echo "  SOURCE_DIR=${SOURCE_DIR:-frontend}"
echo
echo "💡 Tipp: Du kannst nun einfach 'bash frontend/deploy.sh' ausführen."
