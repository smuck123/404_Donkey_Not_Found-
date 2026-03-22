#!/usr/bin/env bash
set -euo pipefail

PROJECT="/opt/git/404_Donkey_Not_Found"
LIVE="/opt/404_donkey_not_found"
DEFAULT_FILE="$PROJECT/.default_branch"

if [ -f "$DEFAULT_FILE" ]; then
    DEFAULT_BRANCH=$(cat "$DEFAULT_FILE")
else
    DEFAULT_BRANCH="test"
fi

BRANCH="${1:-$DEFAULT_BRANCH}"

cd "$PROJECT"

echo "=============================="
echo " 404DonkeyNotFound PULL TOOL "
echo "=============================="
echo "[*] Branch: $BRANCH"

if [ ! -d ".git" ]; then
    echo "[!] Not a git repo"
    exit 1
fi

if ! git remote get-url origin >/dev/null 2>&1; then
    git remote add origin git@github.com:smuck123/404_Donkey_Not_Found-.git
fi

if [ -n "$(git status --porcelain)" ]; then
    echo "[!] Working tree is not clean. Commit, stash, or discard changes first."
    exit 1
fi

git fetch origin

if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
    git checkout "$BRANCH"
else
    git checkout -b "$BRANCH" "origin/$BRANCH" 2>/dev/null || git checkout -b "$BRANCH"
fi

git pull --rebase origin "$BRANCH"

echo "[*] Syncing git workspace to live platform"

mkdir -p "$LIVE/apps" "$LIVE/deploy" "$LIVE/docs"

rsync -aHAX --delete \
  --exclude '.git/' \
  --exclude 'venv/' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  --exclude '.env' \
  --exclude 'telegram_chats.json' \
  --exclude 'pending_fortigate_actions.json' \
  --exclude 'openclaw/' \
  "$PROJECT/apps/openclaw_zabbix_mcp/" "$LIVE/apps/openclaw_zabbix_mcp/"

rsync -aHAX --delete \
  --exclude '.git/' \
  --exclude 'venv/' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  --exclude 'cache/' \
  --exclude 'data/' \
  --exclude 'indexes/' \
  --exclude 'models/' \
  "$PROJECT/apps/404donkey_rag/" "$LIVE/apps/404donkey_rag/"

rsync -aHAX --delete \
  --exclude '.git/' \
  --exclude 'venv/' \
  --exclude 'node_modules/' \
  --exclude '__pycache__/' \
  --exclude '.env' \
  --exclude 'data/' \
  --exclude 'downloads/' \
  --exclude 'exports/' \
  --exclude 'backups/' \
  --exclude 'repos/' \
  --exclude 'shared_folders/' \
  "$PROJECT/apps/chat_admin_webgui/" "$LIVE/apps/chat_admin_webgui/"

rsync -aHAX --delete \
  --exclude '.git/' \
  --exclude 'venv/' \
  --exclude 'node_modules/' \
  --exclude '__pycache__/' \
  "$PROJECT/apps/ollama_webgui/" "$LIVE/apps/ollama_webgui/"

rsync -aHAX --delete \
  "$PROJECT/deploy/" "$LIVE/deploy/"

rsync -aHAX --delete \
  "$PROJECT/docs/" "$LIVE/docs/"

echo "[*] Restarting services"
systemctl restart openclaw-zabbix-mcp
systemctl restart telegram-zabbix-router

echo "[+] Updated branch $BRANCH and deployed to $LIVE"
