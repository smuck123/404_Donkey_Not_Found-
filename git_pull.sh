#!/usr/bin/env bash
set -euo pipefail

PROJECT="/opt/git/404_Donkey_Not_Found"
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

if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "[!] Working tree is not clean. Commit or stash changes first."
    exit 1
fi

git fetch origin

if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
    git checkout "$BRANCH"
else
    git checkout -b "$BRANCH" "origin/$BRANCH" 2>/dev/null || git checkout -b "$BRANCH"
fi

git pull --rebase origin "$BRANCH"

echo "[+] Updated branch $BRANCH"
