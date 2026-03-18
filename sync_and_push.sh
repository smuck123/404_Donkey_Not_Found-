#!/usr/bin/env bash
set -euo pipefail

GIT_DIR="/opt/git/404_Donkey_Not_Found"
TMP_EXCLUDES="/tmp/404donkey_rsync_excludes.txt"
BRANCH="${1:-main}"
MSG="${2:-sync update $(date '+%Y-%m-%d %H:%M:%S')}"

SOURCES=(
  "/opt/chat_admin_webgui"
)

mkdir -p "$GIT_DIR"

cat > "$TMP_EXCLUDES" <<'EXCLUDES'
.git
__pycache__
*.pyc
*.pyo
*.swp
*.tmp
*.log
node_modules
venv
.venv
dist
build
.env
*.sqlite
*.db
data/chats
backups
EXCLUDES

echo "=============================="
echo " 404DonkeyNotFound SYNC+PUSH "
echo "=============================="
echo "[*] Branch: $BRANCH"
echo "[*] Message: $MSG"
echo

for SRC in "${SOURCES[@]}"; do
    if [ ! -d "$SRC" ]; then
        echo "[!] Source missing, skipping: $SRC"
        continue
    fi

    NAME="$(basename "$SRC")"
    DEST="$GIT_DIR/$NAME"

    echo "[*] Syncing $SRC -> $DEST"
    mkdir -p "$DEST"

    rsync -a --delete \
      --exclude-from="$TMP_EXCLUDES" \
      "$SRC/" "$DEST/"
done

cd "$GIT_DIR"

if [ ! -d ".git" ]; then
    echo "[!] Not a git repo"
    exit 1
fi

if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
    git checkout "$BRANCH"
else
    git checkout -b "$BRANCH"
fi

find "$GIT_DIR" -maxdepth 1 -type f -name "*.sh" -exec chmod 755 {} \;

echo "[*] Git status"
git status || true

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
