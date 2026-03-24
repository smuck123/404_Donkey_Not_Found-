#!/usr/bin/env bash
set -euo pipefail

PROJECT="/opt/git/404_Donkey_Not_Found"
LIVE="/opt/404_donkey_not_found"
DEFAULT_FILE="$PROJECT/.default_branch"
REMOTE_URL="git@github.com:smuck123/404_Donkey_Not_Found-.git"

if [ -f "$DEFAULT_FILE" ]; then
    DEFAULT_BRANCH=$(tr -d '[:space:]' < "$DEFAULT_FILE")
else
    DEFAULT_BRANCH="main"
fi

BRANCH="${1:-$DEFAULT_BRANCH}"
MSG="${2:-Auto update $(date '+%Y-%m-%d %H:%M:%S')}"

cd "$PROJECT"

echo "=============================="
echo " 404DonkeyNotFound PUSH TOOL "
echo "=============================="
echo "[*] Branch: $BRANCH"
echo "[*] Message: $MSG"

if [ ! -d ".git" ]; then
    echo "[!] Not a git repo"
    exit 1
fi

if ! git remote get-url origin >/dev/null 2>&1; then
    git remote add origin "$REMOTE_URL"
fi

echo "[*] Fetching remote"
git fetch origin --prune

echo "[*] Aborting unfinished git operations if present"
git rebase --abort 2>/dev/null || true
git merge --abort 2>/dev/null || true

echo "[*] Checking out target branch"
if git ls-remote --exit-code --heads origin "$BRANCH" >/dev/null 2>&1; then
    git checkout -B "$BRANCH" "origin/$BRANCH"
else
    git checkout -B "$BRANCH"
fi

echo "[*] Syncing live platform to git workspace"

mkdir -p "$PROJECT/apps/openclaw_zabbix_mcp" \
         "$PROJECT/apps/404donkey_rag" \
         "$PROJECT/apps/chat_admin_webgui" \
         "$PROJECT/apps/ollama_webgui" \
         "$PROJECT/deploy"

rm -rf "$PROJECT/apps/openclaw_zabbix_mcp/openclaw"

rsync -aHAX --delete \
  --exclude openclaw \
  --exclude venv/ \
  --exclude __pycache__/ \
  --exclude '*.pyc' \
  --exclude '.env' \
  --exclude 'telegram_chats.json' \
  --exclude 'pending_fortigate_actions.json' \
  "$LIVE/apps/openclaw_zabbix_mcp/" "$PROJECT/apps/openclaw_zabbix_mcp/"

rsync -aHAX --delete \
  --exclude venv/ \
  --exclude __pycache__/ \
  --exclude '*.pyc' \
  --exclude cache/ \
  --exclude data/ \
  --exclude indexes/ \
  --exclude models/ \
  "$LIVE/apps/404donkey_rag/" "$PROJECT/apps/404donkey_rag/"

rsync -aHAX --delete \
  --exclude venv/ \
  --exclude node_modules/ \
  --exclude __pycache__/ \
  --exclude '.env' \
  --exclude data/ \
  --exclude downloads/ \
  --exclude exports/ \
  --exclude backups/ \
  --exclude repos/ \
  --exclude shared_folders/ \
  "$LIVE/apps/chat_admin_webgui/" "$PROJECT/apps/chat_admin_webgui/"

rsync -aHAX --delete \
  --exclude venv/ \
  --exclude node_modules/ \
  --exclude __pycache__/ \
  "$LIVE/apps/ollama_webgui/" "$PROJECT/apps/ollama_webgui/"

if [ -d "$LIVE/deploy" ]; then
    rsync -aHAX --delete "$LIVE/deploy/" "$PROJECT/deploy/"
fi

git add .

if git diff --cached --quiet; then
    echo "[*] No changes to commit"
else
    git commit -m "$MSG"
fi

git fetch origin --prune

if git ls-remote --exit-code --heads origin "$BRANCH" >/dev/null 2>&1; then
    git pull --rebase origin "$BRANCH"
fi

git push -u origin "$BRANCH"

echo "[+] Pushed live state to origin/$BRANCH"
