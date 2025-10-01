# lumen/infra/vault/init-transit.sh
# Idempotent init: enable Transit (if not yet) and create a couple of example keys.
# This runs ONCE automatically after the vault container becomes healthy.

set -euo pipefail

echo "[vault-init] Checking Vault status..."
vault status

echo "[vault-init] Logging in with provided token..."
vault login -no-print "${VAULT_TOKEN}"

echo "[vault-init] Enabling Transit secrets engine if missing..."
if ! vault secrets list -format=json | grep -q '"transit/"'; then
  vault secrets enable transit
else
  echo "[vault-init] Transit already enabled."
fi

# Create a reusable template key (you can ignore it, it's just an example)
if ! vault list -format=json transit/keys 2>/dev/null | grep -q '"mem_template"'; then
  echo "[vault-init] Creating transit key: mem_template"
  vault write -f transit/keys/mem_template
fi

# Create a dev member key to test end-to-end encryption from the API later
if ! vault list -format=json transit/keys 2>/dev/null | grep -q '"dev_member"'; then
  echo "[vault-init] Creating transit key: dev_member"
  vault write -f transit/keys/dev_member
fi

echo "[vault-init] Done."
