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
# Pin setuptools<81: setuptools 81 (2025) removed pkg_resources, which dtool-cli still
# imports unconditionally (dtool_cli.cli) — without this, the `dtool` CLI fails to start.
pip install --upgrade pip wheel "setuptools<81"

echo "==> Installing dtoolcore..."
pip install -e /app/dtoolcore

echo "==> Installing dtool-s3..."
pip install -e /app/dtool-s3

echo "==> Installing dtool-cli and dtool-info (from PyPI)..."
pip install dtool-cli dtool-info

# dtool dataset-creation client (provides create/freeze/cp commands) so datasets can be
# created/pushed from inside the container (e.g. create-test-dataset.sh). Installed
# --no-deps to avoid pip pulling a pinned dtoolcore over the editable one above; the
# remaining runtime dep (ruamel.yaml) is added explicitly.
echo "==> Installing dtool dataset-creation client (create/freeze/cp)..."
pip install --no-deps dtool-create dtool-symlink dtool-http
pip install "ruamel.yaml"

echo "==> Installing dservercore..."
pip install -e /app/dservercore

echo "==> Installing dserver-search-plugin-mongo (from PyPI)..."
pip install dserver-search-plugin-mongo

echo "==> Installing dserver-retrieve-plugin-mongo..."
pip install -e /app/dserver-retrieve-plugin-mongo

echo "==> Installing dserver-dependency-graph-plugin..."
pip install -e /app/dserver-dependency-graph-plugin

echo "==> Installing dserver-direct-mongo-plugin..."
pip install -e /app/dserver-direct-mongo-plugin

echo "==> Installing dserver-signed-url-plugin..."
pip install -e /app/dserver-signed-url-plugin

echo "==> Installing dserver-token-generator-plugin-oauth2..."
pip install -e /app/dserver-token-generator-plugin-oauth2

# LDAP token generator: install ONLY when the site asks for it. Sites that authenticate
# via ORCID OAuth2 only (e.g. zhanglab-data) leave INSTALL_LDAP_PLUGIN unset/false, so no
# /auth/ldap blueprint is registered (no second token issuer). Sites that want the
# username/password path (e.g. the demo) set INSTALL_LDAP_PLUGIN=true in their
# docker-compose.override.yml's dserver-build-venv environment. The submodule is always
# checked out either way.
if [ "${INSTALL_LDAP_PLUGIN:-false}" = "true" ]; then
    echo "==> Installing dserver-token-generator-plugin-ldap (INSTALL_LDAP_PLUGIN=true)..."
    pip install -e /app/dserver-token-generator-plugin-ldap
else
    echo "==> Skipping LDAP token generator (INSTALL_LDAP_PLUGIN != true)"
fi

# SAML token generator (pysaml2-based SP). Install only when the site opts in. pysaml2
# needs the system xmlsec1 binary + libxmlsec1 (provided by the Dockerfile). The editable
# install pulls pysaml2>=7.4 et al. as declared in the plugin's pyproject.toml.
if [ "${INSTALL_SAML_PLUGIN:-false}" = "true" ]; then
    echo "==> Installing dserver-token-generator-plugin-saml (INSTALL_SAML_PLUGIN=true)..."
    pip install -e /app/dserver-token-generator-plugin-saml
else
    echo "==> Skipping SAML token generator (INSTALL_SAML_PLUGIN != true)"
fi

echo "==> Installing additional dependencies..."
pip install gunicorn psycopg2-binary PyJWT requests authlib httpx python-dotenv ldap3

echo "==> Virtual environment setup complete!"
pip list

touch /venv/VENV-READY

exit 0
