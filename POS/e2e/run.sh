#!/usr/bin/env bash
# Run the UIT e2e specs. Reads the uit-* passwords from the site's private TSV into env vars (never echoed).
set -euo pipefail
cd "$(dirname "$0")/.."
TSV="${UIT_PASSWORDS_TSV:-$(pwd)/../../../sites/pos-dev/private/uit-passwords.tsv}"
pw() { awk -F'\t' -v u="$1" '$1==u{print $2}' "$TSV"; }
export UIT_BASE_URL="${UIT_BASE_URL:-http://pos-dev.localhost:8000}"
export UIT_ARTIFACTS="${UIT_ARTIFACTS:-$(pwd)/e2e/artifacts}"
export UIT_CHANGE_LOG="${UIT_CHANGE_LOG:-$UIT_ARTIFACTS/changes.log}"
export UIT_USER=uit-cashier@uit-pos.example UIT_USER2=uit-cashier2@uit-pos.example UIT_MANAGER=uit-manager@uit-pos.example
UIT_PASSWORD="$(pw "$UIT_USER")"; UIT_PASSWORD2="$(pw "$UIT_USER2")"; UIT_MANAGER_PASSWORD="$(pw "$UIT_MANAGER")"
export UIT_PASSWORD UIT_PASSWORD2 UIT_MANAGER_PASSWORD
exec yarn -s playwright test -c e2e "$@"
