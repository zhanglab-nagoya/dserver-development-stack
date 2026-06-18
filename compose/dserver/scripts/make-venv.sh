#!/bin/bash

set -o errexit
set -o pipefail
set -o nounset

if [ -f "/venv/VENV-READY" ]; then
    echo "Virtual environment already exists"
    exit 0
fi

echo "==> Creating Python virtual environment..."
python -m venv /venv
source /venv/bin/activate

echo "==> Upgrading pip..."
pip install --upgrade pip setuptools wheel

echo "==> Installing dtoolcore..."
pip install -e /app/dtoolcore

echo "==> Installing dtool-s3..."
pip install -e /app/dtool-s3

echo "==> Installing dtool-cli and dtool-info (from PyPI)..."
pip install dtool-cli dtool-info

echo "==> Installing dservercore..."
pip install -e /app/dservercore

echo "==> Installing dserver-search-plugin-mongo (from PyPI)..."
pip install dserver-search-plugin-mongo

echo "==> Installing dserver-retrieve-plugin-mongo..."
pip install -e /app/dserver-retrieve-plugin-mongo

echo "==> Installing dserver-dependency-graph-plugin..."
pip install -e /app/dserver-dependency-graph-plugin

echo "==> Installing dserver-signed-url-plugin..."
pip install -e /app/dserver-signed-url-plugin

echo "==> Installing dserver-token-generator-plugin-oauth2..."
pip install -e /app/dserver-token-generator-plugin-oauth2

echo "==> Installing dserver-token-generator-plugin-ldap..."
pip install -e /app/dserver-token-generator-plugin-ldap

echo "==> Installing dserver-config-generator-plugin (with minio extra)..."
pip install -e "/app/dserver-config-generator-plugin[minio]"

echo "==> Installing additional dependencies..."
pip install gunicorn psycopg2-binary PyJWT requests authlib httpx python-dotenv ldap3

echo "==> Virtual environment setup complete!"
pip list

touch /venv/VENV-READY

exit 0
