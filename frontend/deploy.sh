#!/usr/bin/env bash
set -euo pipefail

# ============================================
# Stretch Coach Deployment Script (Bash)
# ============================================

BUCKET_NAME="sbuddy.leitnersoft.com"
DISTRIBUTION_ID="d1spztj11put9r.cloudfront.net"  # CloudFront domain
SRC_DIR="$(pwd)"

echo "=== 🧘 Stretch Coach App Deployment ==="
echo "Bucket:       ${BUCKET_NAME}"
echo "Distribution: ${DISTRIBUTION_ID}"
echo "Source:       ${SRC_DIR}"
echo

# -------------------------------------------------
# 1. HTML (no-store)
# -------------------------------------------------
echo "=== 1/4: HTML no-store ==="
aws s3 sync "${SRC_DIR}" "s3://${BUCKET_NAME}" \
  --exclude "*" --include "*.html" \
  --cache-control "no-store, must-revalidate" \
  --content-type "text/html; charset=utf-8" \
  --delete

# -------------------------------------------------
# 2. CSS (no-store)
# -------------------------------------------------
echo
echo "=== 2/4: CSS no-store ==="
aws s3 sync "${SRC_DIR}" "s3://${BUCKET_NAME}" \
  --exclude "*" --include "*.css" \
  --cache-control "no-store, must-revalidate" \
  --content-type "text/css; charset=utf-8"

# -------------------------------------------------
# 3. JS (no-store)
# -------------------------------------------------
echo
echo "=== 3/4: JS no-store ==="
aws s3 sync "${SRC_DIR}" "s3://${BUCKET_NAME}" \
  --exclude "*" --include "*.js" \
  --cache-control "no-store, must-revalidate" \
  --content-type "application/javascript; charset=utf-8"

# -------------------------------------------------
# 4. Static Assets (long cache)
# -------------------------------------------------
echo
echo "=== 4/4: übrige Assets (Images/Fonts/Docs) lange cachen ==="
aws s3 sync "${SRC_DIR}" "s3://${BUCKET_NAME}" \
  --exclude "*.html" --exclude "*.css" --exclude "*.js" \
  --exclude ".git/*" --exclude ".github/*" --exclude "node_modules/*" \
  --cache-control "public, max-age=31536000, immutable"

# -------------------------------------------------
# 5. CloudFront Invalidation
# -------------------------------------------------
echo
echo "=== CloudFront Invalidation (Root + HTML) ==="
aws cloudfront create-invalidation \
  --distribution-id "${DISTRIBUTION_ID}" \
  --paths "/index.html" "/start.html" "/"

echo
echo "✅ Deployment abgeschlossen."
echo "   HTML/CSS/JS werden immer frisch geladen."
