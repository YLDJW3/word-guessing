#!/usr/bin/env bash
# Download Chinese Word Vectors (Mixed-large, Word only, 300-dim).
# Source: https://github.com/Embedding/Chinese-Word-Vectors
#
# The file is in word2vec text format (first line: count dim, then word + floats).
# Hosted on Google Drive — no login required.
#
# Usage:
#   bash download_vectors.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DATA_DIR="${SCRIPT_DIR}/data"
mkdir -p "$DATA_DIR"

FILE_ID="1Zh9ZCEu8_eSQ-qkYVQufQDNKPC4mtEKR"
OUTPUT="sgns.merge.word"
TARGET="${DATA_DIR}/${OUTPUT}"

echo ""
echo "=== Chinese Word Vectors (Mixed-large, 300-dim) ==="
echo "Source: https://github.com/Embedding/Chinese-Word-Vectors"
echo ""

# --- Skip if already downloaded ---
if [[ -f "$TARGET" ]]; then
    echo ">>> Vectors already exist: ${TARGET}"
    echo "    Skipping download."
    echo ""
    echo "Run the game with:"
    echo "  python game.py --vectors '${TARGET}'"
    exit 0
fi

echo ">>> Downloading from Google Drive..."
echo "    File: ${OUTPUT} (~1.5GB)"
echo ""

# Google Drive direct download URL for large files requires confirm token.
# First attempt a direct download; if we get a virus-scan warning page,
# extract the confirm token and retry.
COOKIES="${DATA_DIR}/.gdrive_cookies"

curl -sc "$COOKIES" "https://drive.google.com/uc?export=download&id=${FILE_ID}" -o "$TARGET" -L

# Check if we got an HTML page (virus scan warning) instead of the real file.
if head -c 100 "$TARGET" | grep -qi "html"; then
    echo ">>> Large file confirmation required, retrying..."
    CONFIRM=$(grep -o 'confirm=[^&]*' "$COOKIES" | head -1 | cut -d= -f2)
    if [[ -z "$CONFIRM" ]]; then
        # Newer Google Drive: extract token from the HTML page
        CONFIRM=$(grep -oP 'confirm=([0-9A-Za-z_-]+)' "$TARGET" | head -1 | cut -d= -f2)
    fi
    if [[ -z "$CONFIRM" ]]; then
        CONFIRM="t"
    fi
    curl -Lb "$COOKIES" \
        "https://drive.google.com/uc?export=download&confirm=${CONFIRM}&id=${FILE_ID}" \
        -o "$TARGET"
fi
rm -f "$COOKIES"

# Verify we got a real file (should start with a number like "352217 300")
if head -c 100 "$TARGET" | grep -qP '^\d+ \d+'; then
    echo ">>> Download complete: ${TARGET}"
    echo ""
    echo "Run the game with:"
    echo "  python game.py --vectors '${TARGET}'"
else
    echo ""
    echo "!!! Download may have failed (file doesn't look like word2vec format)."
    echo ""
    echo "Please download manually:"
    echo "  1. Open: https://drive.google.com/open?id=${FILE_ID}"
    echo "  2. Save the file as: ${TARGET}"
    echo ""
    echo "Or use gdown:"
    echo "  pip install gdown"
    echo "  gdown ${FILE_ID} -O '${TARGET}'"
fi
