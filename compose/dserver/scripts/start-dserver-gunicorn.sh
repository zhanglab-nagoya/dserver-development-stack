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

echo "==> Waiting for database to be ready..."
sleep 2

echo "==> Running database migrations..."
flask db init || true          # May already be initialized
flask db migrate -m "Auto migration" || true  # May have nothing to migrate
flask db upgrade

echo "==> Creating default admin user if not exists..."
flask user add --is_admin admin || echo "    User 'admin' may already exist"

echo "==> Registering S3 base URI..."
flask base_uri add s3://dtool-bucket || echo "    Base URI may already exist"

echo "==> Granting admin access to S3 bucket..."
flask user search_permission admin s3://dtool-bucket || echo "    Permission may already exist"
flask user register_permission admin s3://dtool-bucket || echo "    Permission may already exist"

echo "==> Starting dserver under gunicorn (SCRIPT_NAME=${SCRIPT_NAME:-/}) on :5000..."
echo "    Reachable through Caddy at https://${DEPLOY_FQDN:-localhost}${SCRIPT_NAME:-}"
# -w 1 / --threads 4: one core, so a single worker with threads for I/O concurrency
#   (the signed-url path does blocking S3 reads).
# --forwarded-allow-ips="*": trust Caddy's X-Forwarded-Proto so Flask builds https URLs.
# Add `--reload` below if you want Python hot-reload (heavier on this box).
exec gunicorn \
    --bind 0.0.0.0:5000 \
    --workers 1 \
    --threads 4 \
    --timeout 120 \
    --forwarded-allow-ips="*" \
    --access-logfile - \
    --error-logfile - \
    "dservercore:create_app()"
