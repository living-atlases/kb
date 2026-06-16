#!/bin/bash
# Deploy hook: copy the KB cert to the VM's nginx after renewal.
# Install at: /etc/letsencrypt/renewal-hooks/deploy/copy-kb-cert.sh
# chmod 700 /etc/letsencrypt/renewal-hooks/deploy/copy-kb-cert.sh
#
# Configure for your deployment via environment variables (defaults shown):
#   KB_DOMAIN  - the certificate domain        (default: kb.l-a.site)
#   KB_VM_SSH  - ssh host/alias of the target  (default: la-toolkit-kb)

set -euo pipefail

DOMAIN="${KB_DOMAIN:-kb.l-a.site}"
VM_SSH="${KB_VM_SSH:-la-toolkit-kb}"
VM_CERT_DIR="/etc/letsencrypt/live/${DOMAIN}"
CERT_DIR="/etc/letsencrypt/live/${DOMAIN}"

# Only run for the configured domain's renewal
if [[ ! " ${RENEWED_DOMAINS} " =~ " ${DOMAIN} " ]]; then
    exit 0
fi

echo "[copy-kb-cert] Copying certs for ${DOMAIN} to ${VM_SSH}:${VM_CERT_DIR}"

# Ensure target dir exists on VM
ssh "${VM_SSH}" "mkdir -p ${VM_CERT_DIR} && chmod 755 ${VM_CERT_DIR}"

# Copy cert files
scp "${CERT_DIR}/fullchain.pem" "${VM_SSH}:${VM_CERT_DIR}/fullchain.pem"
scp "${CERT_DIR}/privkey.pem"   "${VM_SSH}:${VM_CERT_DIR}/privkey.pem"

# Set permissions on VM
ssh "${VM_SSH}" "chmod 644 ${VM_CERT_DIR}/fullchain.pem && chmod 600 ${VM_CERT_DIR}/privkey.pem"

# Reload nginx on VM
ssh "${VM_SSH}" "nginx -t && systemctl reload nginx"

echo "[copy-kb-cert] Done."
