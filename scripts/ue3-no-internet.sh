#!/bin/bash
# =============================================================================
# UE3 Internet Block - Removes default route, adds blackhole
# =============================================================================
# UE3 has two paths to the internet:
#   1. uesimtun0 → UPF3 (blocked by UPF3 blackhole) ✓
#   2. eth0 → Docker bridge → host → internet (THIS is the leak)
#
# This script:
#   1. Starts UERANSIM UE in the background
#   2. Waits for uesimtun0 to come up (GTP tunnel established)
#   3. Replaces default route with blackhole (blocks eth0 internet)
#   4. Keeps 10.33.33.0/24 route (internal services still work)
#
# Result:
#   10.33.33.0/24 via eth0  → mqtt, nodered, edge, core NFs  ✓ WORKS
#   10.47.0.0/16 via tun    → slice-internal                  ✓ WORKS
#   everything else          → blackhole                       ✗ DROPPED
# =============================================================================

echo "[ue3-no-internet] Starting UERANSIM UE in background..."

# Step 1: Start the original UERANSIM UE process in background
/UERANSIM/nr-ue "$@" &
UE_PID=$!

# Step 2: Wait for uesimtun0 to be created (GTP tunnel established)
echo "[ue3-no-internet] Waiting for uesimtun0 (GTP tunnel)..."
MAX_WAIT=60
WAITED=0
while ! ip link show uesimtun0 &>/dev/null; do
    sleep 1
    WAITED=$((WAITED + 1))
    if [ $WAITED -ge $MAX_WAIT ]; then
        echo "[ue3-no-internet] ERROR: uesimtun0 did not appear after ${MAX_WAIT}s"
        echo "[ue3-no-internet] Continuing without internet block"
        wait $UE_PID
        exit $?
    fi
done
echo "[ue3-no-internet] uesimtun0 is UP after ${WAITED}s"

# Step 3: Show routing BEFORE changes
echo "[ue3-no-internet] Routing BEFORE:"
ip route show

# Step 4: Remove the default route via eth0 (this is the internet leak)
ip route del default via 10.33.33.1 dev eth0 2>/dev/null || \
ip route del default dev eth0 2>/dev/null || \
echo "[ue3-no-internet] WARNING: Could not remove default route"

# Step 5: Add blackhole default (drops all non-matched traffic)
ip route add blackhole default 2>/dev/null

# Step 6: Show routing AFTER changes
echo ""
echo "[ue3-no-internet] Routing AFTER:"
ip route show
echo ""
echo "[ue3-no-internet] RESULT:"
echo "  10.33.33.0/24 via eth0     → internal services  ✓ ALLOWED"
echo "  10.47.0.0/16  via uesimtun0 → slice traffic     ✓ ALLOWED"
echo "  everything else             → blackhole          ✗ DROPPED"

# Step 7: Wait for the UERANSIM process (keeps container alive)
wait $UE_PID