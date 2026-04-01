#!/bin/bash
set -e

# 1. Safety check: Is 'uv' installed?
if ! command -v uv &> /dev/null; then
    echo "Error: 'uv' is not installed. Please install it first."
    exit 1
fi

# 2. Install python dependecies
uv sync

# 3. Guardrail check: Don't overwrite existing files
if [ -f .env ]; then
    echo ".env already exists — delete it first if you want to regenerate it."
    exit 1
fi

# 4. Securely read the password (it won't echo to the screen or process list)
read -s -p "Enter admin password: " PASSWORD
echo # Moves to a new line after the hidden input

# 5. Create an empty .env and lock down permissions immediately (chmod 600)
# This prevents other users on the system from reading your secrets.
touch .env
chmod 600 .env

# 6. Export the password temporarily to the environment so Python can read it safely
export TEMP_PASS="$PASSWORD"

# 7. Populate .env file with secrets
echo "Generating secure environment file..."
uv run --with bcrypt python -c "
import os, secrets, bcrypt

secret_key = secrets.token_hex(32)
# Fetching from the environment prevents shell injection
plain_pass = os.environ.get('TEMP_PASS', '').encode('utf-8')
pw_hash = bcrypt.hashpw(plain_pass, bcrypt.gensalt()).decode()

print(f'SECRET_KEY={secret_key}')
print('ADMIN_USERNAME=admin')
print(f'ADMIN_PASSWORD_HASH={pw_hash}')
print('HTTPS_ONLY=false')
" > .env

echo ".env created successfully with restricted file permissions."

# 8. Clean up memory
unset TEMP_PASS
unset PASSWORD

echo "Setup completed successfully."
