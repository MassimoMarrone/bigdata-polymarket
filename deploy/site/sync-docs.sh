#!/usr/bin/env bash
# Copia i documenti che vivono fuori dal repo dentro site/content/.
# Da eseguire IN LOCALE quando Relazione/Decisioni cambiano, prima del commit.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$HERE/../../.."   # cartella Progetto/
cp "$SRC/Relazione.md"  "$HERE/content/relazione.md"
cp "$SRC/Decisioni.md"  "$HERE/content/decisioni.md"
cp "$HERE/../../README.md" "$HERE/content/setup.md"
mkdir -p "$HERE/content/shots"
cp "$SRC/screenshots/"tab*.png "$HERE/content/shots/"
echo "content/ aggiornato"
