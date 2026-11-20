#!/bin/sh
# Lancé par cron toutes les 2 heures sur le mini PC (voir installer.sh).
# Lit le webhook dans ~/.config/joybuy-bot/env et garde l'historique dans ~/.local/share/joybuy-bot/.
set -eu

DOSSIER="$(cd "$(dirname "$0")" && pwd)"
CONFIG="${JOYBUY_CONFIG:-$HOME/.config/joybuy-bot/env}"
if [ ! -f "$CONFIG" ]; then
    echo "Configuration introuvable : $CONFIG (lance installer.sh)" >&2
    exit 1
fi
set -a
. "$CONFIG"
set +a

export JOYBUY_ETAT="${JOYBUY_ETAT:-$HOME/.local/share/joybuy-bot/etat.json}"
mkdir -p "$(dirname "$JOYBUY_ETAT")"
JOURNAL="$(dirname "$JOYBUY_ETAT")/joybuy.log"

# Délai aléatoire de 0 à 10 minutes, pour ne pas toujours passer à la même seconde.
if [ "${1:-}" != "--maintenant" ]; then
    sleep $(( $(od -An -N2 -tu2 /dev/urandom) % 600 ))
fi

echo "=== $(date '+%Y-%m-%d %H:%M:%S') ===" >>"$JOURNAL"
# Récupère la wishlist et le code à jour (modifiés depuis GitHub).
git -C "$DOSSIER" pull --ff-only -q >>"$JOURNAL" 2>&1 || echo "(git pull impossible, on continue avec la version locale)" >>"$JOURNAL"
code=0
PYTHON="$DOSSIER/.venv/bin/python"
[ -x "$PYTHON" ] || PYTHON=python3  # pas de venv : Python du système
"$PYTHON" "$DOSSIER/joybuy_bot.py" >>"$JOURNAL" 2>&1 || code=$?
[ "$code" -eq 0 ] || echo "(code de sortie : $code)" >>"$JOURNAL"

# Le journal garde seulement ses 2 000 dernières lignes.
tail -n 2000 "$JOURNAL" >"$JOURNAL.tmp" && mv "$JOURNAL.tmp" "$JOURNAL"
exit "$code"
