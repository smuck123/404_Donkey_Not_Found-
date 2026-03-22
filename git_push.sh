#!/usr/bin/env bash
set -euo pipefail

PROJECT="/opt/git/404_Donkey_Not_Found"
DEFAULT_FILE="$PROJECT/.default_branch"

if [ -f "$DEFAULT_FILE" ]; then
    DEFAULT_BRANCH=$(cat "$DEFAULT_FILE")
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
    git remote add origin git@github.com:smuck123/404_Donkey_Not_Found-.git
fi

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

git fetch origin

if git ls-remote --exit-code --heads origin "$BRANCH" >/dev/null 2>&1; then
    git pull --rebase origin "$BRANCH"
fi

git push -u origin "$BRANCH"

echo "[+] Done"
