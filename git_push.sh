#!/usr/bin/env bash
set -e

PROJECT="/opt/git/404_Donkey_Not_Found"

cd "$PROJECT"

echo "=============================="
echo " 404DonkeyNotFound PUSH TOOL "
echo "=============================="

# check repo
if [ ! -d ".git" ]; then
    echo "[!] Not a git repo"
    exit 1
fi

# show status
echo "[*] Status:"
git status

# add all changes
echo "[*] Adding files..."
git add .

# commit if needed
if git diff --cached --quiet; then
    echo "[*] Nothing to commit"
else
    MSG="${1:-Auto update $(date '+%Y-%m-%d %H:%M:%S')}"
    echo "[*] Commit: $MSG"
    git commit -m "$MSG"
fi

# pull before push (avoid conflicts)
echo "[*] Pull latest..."
git pull origin main --rebase || true

# push
echo "[*] Pushing to GitHub..."
git push origin main

echo "[+] DONE 🚀"
