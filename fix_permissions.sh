#!/usr/bin/env bash
set -e

PROJECT_DIR="/opt/git/404_Donkey_Not_Found"
OWNER="${SUDO_USER:-$USER}"

sudo chown -R "$OWNER":"$OWNER" "$PROJECT_DIR"
find "$PROJECT_DIR" -type d -exec chmod 755 {} \;
find "$PROJECT_DIR" -type f -exec chmod 644 {} \;

find "$PROJECT_DIR" -maxdepth 1 -type f -name "*.sh" -exec chmod 755 {} \;

echo "[+] Permissions fixed for $PROJECT_DIR"
