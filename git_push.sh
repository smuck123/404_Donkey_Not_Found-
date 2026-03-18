#!/usr/bin/env bash
set -euo pipefail

PROJECT="/opt/git/404_Donkey_Not_Found"
BRANCH="${1:-main}"
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

# create branch locally if missing
if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
    git checkout "$BRANCH"
else
    git checkout -b "$BRANCH"
fi

echo "[*] Git status"
git status

echo "[*] Add files"
git add .

if git diff --cached --quiet; then
    echo "[*] No changes to commit"
else
    git commit -m "$MSG"
fi

echo "[*] Pull latest from origin/$BRANCH"
git pull origin "$BRANCH" --rebase || true

echo "[*] Push to origin/$BRANCH"
git push -u origin "$BRANCH"

echo "[+] Done"
