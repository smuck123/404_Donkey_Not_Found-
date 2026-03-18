#!/usr/bin/env bash
set -e

cd /opt/git/404_Donkey_Not_Found

echo "[*] Fetch"
git fetch origin

echo "[*] Pull"
git pull origin main

echo "[+] Done"
