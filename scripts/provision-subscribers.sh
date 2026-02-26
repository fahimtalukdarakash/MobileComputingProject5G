#!/bin/bash
# =============================================================================
# Auto-provision UERANSIM subscribers in Open5GS MongoDB
# Run this after 'docker compose up' if subscribers are missing.
# Safe to run multiple times (uses upsert).
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INIT_JS="$SCRIPT_DIR/configs/network-slicing/mongo-init.js"

if [ ! -f "$INIT_JS" ]; then
    echo "ERROR: Cannot find $INIT_JS"
    echo "Run this script from the project root directory."
    exit 1
fi

echo "=== Open5GS Subscriber Auto-Provisioning ==="
echo ""

# Wait for MongoDB
echo "Checking MongoDB..."
for i in $(seq 1 10); do
    docker exec db mongosh --quiet --eval "db.runCommand({ping:1})" >/dev/null 2>&1 && break
    echo "  Attempt $i/10 - waiting for MongoDB..."
    sleep 2
done

# Run init script
echo "Provisioning subscribers..."
docker exec -i db mongosh --quiet < "$INIT_JS"

echo ""
echo "=== Done ==="
echo "You can verify in Open5GS WebUI at http://localhost:9999"
echo "  - UE1 (IoT):       imsi-001010000000004  → Slice 1"
echo "  - UE2 (Vehicle):   imsi-001010000000002  → Slice 2"
echo "  - UE3 (Restricted): imsi-001010000000001 → Slice 3"