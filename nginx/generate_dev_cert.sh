#!/usr/bin/env bash
# Generates a self-signed TLS certificate for local development.
# DO NOT use in production — obtain a real certificate from Let's Encrypt.
#
# Usage:  bash nginx/generate_dev_cert.sh
set -e

CERT_DIR="$(dirname "$0")/certs"
mkdir -p "$CERT_DIR"

openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout "$CERT_DIR/privkey.pem" \
  -out    "$CERT_DIR/fullchain.pem" \
  -subj   "/C=PK/ST=Punjab/L=Islamabad/O=HydroGuard-Dev/CN=localhost"

echo ""
echo "Self-signed certificate created in $CERT_DIR/"
echo "  fullchain.pem  — certificate"
echo "  privkey.pem    — private key"
echo ""
echo "Start the stack with:  docker compose up --build"
echo "Accept the browser security warning for localhost."
echo ""
echo "For production: replace these files with real Let's Encrypt certificates."
echo "  certbot certonly --webroot -w /var/www/certbot -d yourdomain.com"
