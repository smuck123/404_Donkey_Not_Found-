#!/usr/bin/env bash
set -e

cd /opt/git/404_Donkey_Not_Found

MSG="${1:-update}"

echo "[*] Git status"
git status

echo "[*] Adding files"
git add .

if git diff --cached --quiet; then
    echo "[*] No changes to commit"
else
    echo "[*] Commit"
    git commit -m "$MSG"
fi

echo "[*] Push"
git push origin main

echo "[+] Done"
