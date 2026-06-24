#!/bin/bash
# start-dserver-gunicorn.sh — HTTPS deployment entrypoint for dserver.
#
# Same one-time prep as start-dserver.sh, but serves the app via gunicorn instead of
# `flask run`. Gunicorn honours the SCRIPT_NAME environment variable, which mounts the
# entire dserver app under a path prefix (SCRIPT_NAME=/lookup) so it lines up with the
# Caddy reverse proxy (`/lookup* -> dserver`) and the webapp's API base URL.
#
# Referenced from docker-compose.override.yml via the bind-mounted /app path, so no image
# rebuild is needed when this script changes.
set -o errexit
set -o pipefail
set -o nounset

echo "==> Generating JWT keys if they don't exist..."
JWT_DIR="/app/compose/dserver/jwt"
mkdir -p "$JWT_DIR"
if [ ! -f "$JWT_DIR/jwt_key" ]; then
    echo "    Generating RSA key pair..."
    openssl genrsa -out "$JWT_DIR/jwt_key" 2048
    openssl rsa -in "$JWT_DIR/jwt_key" -pubout -out "$JWT_DIR/jwt_key.pub"
    chmod 600 "$JWT_DIR/jwt_key"
    chmod 644 "$JWT_DIR/jwt_key.pub"
    echo "    JWT keys generated."
else
    echo "    JWT keys already exist."
fi

# SAML SP signing/encryption keypair — only when the SAML plugin is configured
# (SAML_SP_KEY_FILE set). Self-signed is fine: the IdP trusts the SP via the public cert
# embedded in the SP metadata we publish at <BASE_URL>/auth/saml/metadata. No-op otherwise.
if [ -n "${SAML_SP_KEY_FILE:-}" ] && [ ! -f "${SAML_SP_KEY_FILE}" ]; then
    echo "==> Generating SAML SP keypair (${SAML_SP_KEY_FILE})..."
    mkdir -p "$(dirname "${SAML_SP_KEY_FILE}")"
    openssl req -x509 -newkey rsa:2048 -nodes \
        -keyout "${SAML_SP_KEY_FILE}" \
        -out "${SAML_SP_CERT_FILE:?SAML_SP_CERT_FILE must be set when SAML_SP_KEY_FILE is}" \
        -days 1095 \
        -subj "/CN=${DEPLOY_FQDN:-localhost} dserver SAML SP" >/dev/null 2>&1
    chmod 600 "${SAML_SP_KEY_FILE}"
    chmod 644 "${SAML_SP_CERT_FILE}"
    echo "    SAML SP keypair generated (re-publish SP metadata to the IdP after this)."
fi

echo "==> Waiting for database to be ready..."
sleep 2

echo "==> Running database migrations..."
flask db init || true          # May already be initialized
flask db migrate -m "Auto migration" || true  # May have nothing to migrate
flask db upgrade

echo "==> Creating default admin user if not exists..."
flask user add --is_admin admin || echo "    User 'admin' may already exist"

# S3_BUCKET is supplied via the dserver service env (docker-compose.override.yml). Fall back
# to dtool-bucket for the plain local-minio dev path where S3_BUCKET may be unset.
BUCKET="${S3_BUCKET:-dtool-bucket}"

echo "==> Registering S3 base URI (s3://${BUCKET})..."
flask base_uri add "s3://${BUCKET}" || echo "    Base URI may already exist"

echo "==> Granting admin access to S3 bucket..."
flask user search_permission admin "s3://${BUCKET}" || echo "    Permission may already exist"
flask user register_permission admin "s3://${BUCKET}" || echo "    Permission may already exist"

echo "==> Starting dserver under gunicorn (SCRIPT_NAME=${SCRIPT_NAME:-/}) on :5000..."
echo "    Reachable through Caddy at https://${DEPLOY_FQDN:-localhost}${SCRIPT_NAME:-}"
# -w 1 / --threads 4: one core, so a single worker with threads for I/O concurrency
#   (the signed-url path does blocking S3 reads).
# --forwarded-allow-ips="*": trust Caddy's X-Forwarded-Proto so Flask builds https URLs.
# Add `--reload` below if you want Python hot-reload (heavier on this box).
#
# export-s3-env.sh injects dtool-s3's per-bucket env vars (DTOOL_S3_*_<bucket>, name contains
# the bucket so it can't be set via shell `export`) and execs gunicorn — the signed-url path
# needs them for server-side S3 reads. No-op (just execs gunicorn) when S3_BUCKET is unset.
exec "$(dirname "$0")/export-s3-env.sh" gunicorn \
    --bind 0.0.0.0:5000 \
    --workers 1 \
    --threads 4 \
    --timeout 120 \
    --forwarded-allow-ips="*" \
    --access-logfile - \
    --error-logfile - \
    "dservercore:create_app()"
