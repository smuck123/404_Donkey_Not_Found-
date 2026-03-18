#!/usr/bin/env bash
set -e

PROJECT_DIR="/opt/git/404_Donkey_Not_Found"
SSH_KEY="$HOME/.ssh/github_404donkey"
SSH_CONFIG="$HOME/.ssh/config"

sudo apt update
sudo apt install -y git openssh-client

mkdir -p "$HOME/.ssh"
chmod 700 "$HOME/.ssh"

if [ ! -f "$SSH_KEY" ]; then
    ssh-keygen -t ed25519 -C "404DonkeyNotFound-GitHub" -f "$SSH_KEY" -N ""
fi

chmod 600 "$SSH_KEY"
chmod 644 "${SSH_KEY}.pub"

if ! grep -q "Host github-404donkey" "$SSH_CONFIG" 2>/dev/null; then
cat >> "$SSH_CONFIG" <<'CFG'

Host github-404donkey
    HostName github.com
    User git
    IdentityFile ~/.ssh/github_404donkey
    IdentitiesOnly yes
CFG
fi

chmod 600 "$SSH_CONFIG"

cd "$PROJECT_DIR"

rm -rf .git
git init
git branch -M main

if [ ! -f .gitignore ]; then
cat > .gitignore <<'GITEOF'
__pycache__/
*.pyc
*.pyo
*.swp
*.tmp
*.log
.env
.venv/
venv/
node_modules/
dist/
build/
GITEOF
fi

git remote remove origin 2>/dev/null || true
git remote add origin git@github-404donkey:smuck123/404_Donkey_Not_Found.git

cat > git_push.sh <<'PUSHEOF'
#!/usr/bin/env bash
set -e
cd /opt/git/404_Donkey_Not_Found
MSG="${1:-update}"
git add .
if git diff --cached --quiet; then
    echo "[*] No changes to commit"
else
    git commit -m "$MSG"
fi
git push origin main
PUSHEOF

cat > git_pull.sh <<'PULLEOF'
#!/usr/bin/env bash
set -e
cd /opt/git/404_Donkey_Not_Found
git fetch origin
git pull origin main
PULLEOF

cat > fix_permissions.sh <<'PERMEOF'
#!/usr/bin/env bash
set -e
PROJECT_DIR="/opt/git/404_Donkey_Not_Found"
OWNER="${SUDO_USER:-$USER}"
sudo chown -R "$OWNER":"$OWNER" "$PROJECT_DIR"
find "$PROJECT_DIR" -type d -exec chmod 755 {} \;
find "$PROJECT_DIR" -type f -exec chmod 644 {} \;
find "$PROJECT_DIR" -maxdepth 1 -type f -name "*.sh" -exec chmod 755 {} \;
echo "[+] Permissions fixed"
PERMEOF

chmod +x git_push.sh git_pull.sh fix_permissions.sh

echo
echo "[+] Setup complete"
echo
echo "[!] Add this SSH public key to GitHub:"
cat "${SSH_KEY}.pub"
echo
echo "[!] Then test:"
echo "ssh -T github-404donkey"
echo
echo "[!] Then first push:"
echo "cd $PROJECT_DIR && git add . && git commit -m 'Initial clean import' && git push -u origin main"
