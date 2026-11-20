#!/bin/sh
# Installe le bot pour l'utilisateur courant, sans sudo : environnement Python, configuration, tâche cron.
# Peut être relancé sans risque (après un `git pull`, par exemple).
set -eu

DOSSIER="$(cd "$(dirname "$0")" && pwd)"
CONFIG_DIR="$HOME/.config/joybuy-bot"
ETAT_DIR="$HOME/.local/share/joybuy-bot"

# 1. Environnement Python isolé (il faut le paquet python3-venv).
if ! python3 -m venv "$DOSSIER/.venv" 2>/dev/null; then
    echo "❌ python3-venv manque. Installe-le une fois : sudo apt install python3-venv" >&2
    exit 1
fi
"$DOSSIER/.venv/bin/pip" install -q --upgrade pip
"$DOSSIER/.venv/bin/pip" install -q -r "$DOSSIER/requirements.txt"
chmod +x "$DOSSIER/lancer.sh"

# 2. Configuration : le webhook reste hors du dépôt, lisible par toi seul.
mkdir -p "$CONFIG_DIR" "$ETAT_DIR"
chmod 700 "$CONFIG_DIR"
if [ ! -f "$CONFIG_DIR/env" ]; then
    umask 077
    cat >"$CONFIG_DIR/env" <<'FIN'
# Webhook(s) Discord, séparés par des espaces s'il y en a plusieurs.
DISCORD_WEBHOOK_URL=
# Baisse minimale (en %) qui déclenche une alerte.
BAISSE_MIN_PCT=5
FIN
    echo "➡️  Mets l'URL du webhook dans $CONFIG_DIR/env (nano $CONFIG_DIR/env)."
fi

# 3. Reprend l'historique du dépôt la première fois (il retient les annonces déjà postées).
if [ ! -f "$ETAT_DIR/etat.json" ] && [ -f "$DOSSIER/etat.json" ]; then
    cp "$DOSSIER/etat.json" "$ETAT_DIR/etat.json"
fi

# 4. Tâche cron toutes les 2 heures (remplace l'ancienne ligne si elle existe).
LIGNE="17 */2 * * * $DOSSIER/lancer.sh"
( crontab -l 2>/dev/null | grep -v "joybuy\|$DOSSIER/lancer.sh" || true; echo "$LIGNE # joybuy-bot" ) | crontab -
echo "✅ Installé. Tâche cron : $LIGNE"
echo "   Tester tout de suite : $DOSSIER/lancer.sh --maintenant ; puis : tail -n 50 $ETAT_DIR/joybuy.log"
