#!/bin/bash
# gen-tls-certs.sh — generate the local CA + server certificate for the HTTPS
# deployment. One CA signs one SAN cert for the deployment FQDN; that cert is
# served by BOTH Caddy (:443, webapp + API) and MinIO (:9000, native TLS).
# Clients trust ./certs/ca.crt.
#
# The FQDN comes from $DEPLOY_FQDN — set it in .env (alongside compose) or
# export it in the shell. There is no built-in fallback so a misconfigured host
# fails loudly here rather than silently producing certs for the wrong name.
#
# Output (in ./certs, git-ignored):
#   ca.crt / ca.key        - the local certificate authority (ca.key is the secret root)
#   server.crt / server.key - leaf cert for the FQDN (+ minio/localhost SANs), served by
#                             Caddy and MinIO; boto/dserver verify it against ca.crt.
#
# Re-run is a no-op if certs already exist; delete ./certs/*.crt to regenerate.
set -o errexit -o pipefail -o nounset

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Pick up DEPLOY_FQDN from .env if the shell doesn't already have it. Compose
# reads .env automatically; this script doesn't, so source it ourselves.
if [ -z "${DEPLOY_FQDN:-}" ] && [ -f "$SCRIPT_DIR/.env" ]; then
    # shellcheck disable=SC1091
    set -o allexport; . "$SCRIPT_DIR/.env"; set +o allexport
fi
: "${DEPLOY_FQDN:?DEPLOY_FQDN must be set (in .env or the shell environment)}"

FQDN="$DEPLOY_FQDN"
CERT_DIR="$SCRIPT_DIR/certs"
mkdir -p "$CERT_DIR"
cd "$CERT_DIR"

if [ -f ca.crt ] && [ -f server.crt ]; then
    echo "Certs already present in $CERT_DIR — delete them to regenerate."
    exit 0
fi

echo "==> Generating local CA for $FQDN..."
openssl genrsa -out ca.key 4096
openssl req -x509 -new -nodes -key ca.key -sha256 -days 3650 \
    -subj "/CN=$FQDN local CA" -out ca.crt

echo "==> Generating server key + CSR for $FQDN..."
openssl genrsa -out server.key 2048
openssl req -new -key server.key -subj "/CN=$FQDN" -out server.csr

cat > san.ext <<EOF
subjectAltName = DNS:$FQDN, DNS:minio, DNS:localhost, IP:127.0.0.1
extendedKeyUsage = serverAuth
EOF

echo "==> Signing server cert with the CA..."
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
    -out server.crt -days 825 -sha256 -extfile san.ext

rm -f server.csr san.ext ca.srl
# ca.key is the sensitive root; server.key is 644 so all container users (Caddy/MinIO,
# which may run as different uids) can read it.
chmod 600 ca.key
chmod 644 ca.crt server.crt server.key

echo "==> Done. CA + server cert written to $CERT_DIR"
ls -l "$CERT_DIR"
