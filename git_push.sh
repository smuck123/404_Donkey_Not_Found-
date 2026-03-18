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

git remote remove origin 2>/dev/null || true
git remote add origin git@github.com:smuck123/404_Donkey_Not_Found-.git

if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
    git checkout "$BRANCH"
else
    git checkout -b "$BRANCH"
fi

git add .

if git diff --cached --quiet; then
    echo "[*] No changes to commit"
else
    git commit -m "$MSG"
fi

git pull origin "$BRANCH" --rebase || true
git push -u origin "$BRANCH"

echo "[+] Done"
