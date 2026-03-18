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

cd "$PROJECT"

echo "=============================="
echo " 404DonkeyNotFound PULL TOOL "
echo "=============================="
echo "[*] Branch: $BRANCH"

git remote remove origin 2>/dev/null || true
git remote add origin git@github.com:smuck123/404_Donkey_Not_Found-.git

if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
    git checkout "$BRANCH"
else
    git checkout -b "$BRANCH"
fi

git fetch origin
git pull origin "$BRANCH"

echo "[+] Updated branch $BRANCH"
