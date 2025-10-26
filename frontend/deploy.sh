#!/usr/bin/env bash
set -euo pipefail

# ============================================
# Stretch Coach Deployment Script (Bash)
# ============================================

S3_BUCKET="${S3_BUCKET:-${BUCKET_NAME:-}}"
CLOUDFRONT_DISTRIBUTION_ID="${CLOUDFRONT_DISTRIBUTION_ID:-${DISTRIBUTION_ID:-}}"
AWS_REGION="${AWS_REGION:-eu-central-1}"
SRC_DIR="${SOURCE_DIR:-$(pwd)}"

export AWS_DEFAULT_REGION="${AWS_REGION}"

if [[ -z "${S3_BUCKET}" ]]; then
  echo "❌ Bitte die Umgebungsvariable S3_BUCKET setzen." >&2
  exit 1
fi

if [[ -z "${CLOUDFRONT_DISTRIBUTION_ID}" ]]; then
  echo "❌ Bitte die Umgebungsvariable CLOUDFRONT_DISTRIBUTION_ID setzen." >&2
  exit 1
fi

echo "=== 🧘 Stretch Coach App Deployment ==="
echo "Bucket:       ${S3_BUCKET}"
echo "Distribution: ${CLOUDFRONT_DISTRIBUTION_ID}"
echo "Source:       ${SRC_DIR}"
echo

# -------------------------------------------------
# 1. HTML (no-store)
# -------------------------------------------------
echo "=== 1/4: HTML no-store ==="
aws s3 sync "${SRC_DIR}" "s3://${S3_BUCKET}" \
  --exclude "*" --include "*.html" \
  --cache-control "no-store, must-revalidate" \
  --content-type "text/html; charset=utf-8" \
  --delete

# -------------------------------------------------
# 2. CSS (no-store)
# -------------------------------------------------
echo
echo "=== 2/4: CSS no-store ==="
aws s3 sync "${SRC_DIR}" "s3://${S3_BUCKET}" \
  --exclude "*" --include "*.css" \
  --cache-control "no-store, must-revalidate" \
  --content-type "text/css; charset=utf-8"

# -------------------------------------------------
# 3. JS (no-store)
# -------------------------------------------------
echo
echo "=== 3/4: JS no-store ==="
aws s3 sync "${SRC_DIR}" "s3://${S3_BUCKET}" \
  --exclude "*" --include "*.js" \
  --cache-control "no-store, must-revalidate" \
  --content-type "application/javascript; charset=utf-8"

# -------------------------------------------------
# 4. JSON (no-store)
# -------------------------------------------------
echo
echo "=== 4/6: JSON no-store ==="
aws s3 sync "${SRC_DIR}" "s3://${S3_BUCKET}" \
  --exclude "*" --include "*.json" \
  --cache-control "no-store, must-revalidate" \
  --content-type "application/json; charset=utf-8"

# -------------------------------------------------
# 5. Manifest (no-store)
# -------------------------------------------------
echo
echo "=== 5/6: Manifest no-store ==="
aws s3 sync "${SRC_DIR}" "s3://${S3_BUCKET}" \
  --exclude "*" --include "*.webmanifest" \
  --cache-control "no-store, must-revalidate" \
  --content-type "application/manifest+json"

# -------------------------------------------------
# 6. Static Assets (long cache)
# -------------------------------------------------
echo
echo "=== 6/6: übrige Assets (Images/Fonts/Docs) lange cachen ==="
aws s3 sync "${SRC_DIR}" "s3://${S3_BUCKET}" \
  --exclude "*.html" --exclude "*.css" --exclude "*.js" --exclude "*.json" --exclude "*.webmanifest" \
  --exclude ".git/*" --exclude ".github/*" --exclude "node_modules/*" \
  --cache-control "public, max-age=31536000, immutable"

# -------------------------------------------------
# 5. CloudFront Invalidation
# -------------------------------------------------
echo
echo "=== CloudFront Invalidation (Root + HTML) ==="
aws cloudfront create-invalidation \
  --distribution-id "${CLOUDFRONT_DISTRIBUTION_ID}" \
  --paths "/index.html" "/start.html" "/manifest.webmanifest" "/service-worker.js" "/exercises.json" "/"

echo
echo "✅ Deployment abgeschlossen."
echo "   HTML/CSS/JS werden immer frisch geladen."
