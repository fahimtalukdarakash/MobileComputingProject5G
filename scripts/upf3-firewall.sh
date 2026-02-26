#!/bin/bash
# =============================================================================
# UPF3 Firewall Entrypoint - Blocks internet for Slice 3 (10.47.0.0/16)
# =============================================================================
# Uses POLICY-BASED ROUTING to block internet access for UE3.
#
# Why not iptables? The UPF's GTP decapsulation + TUN forwarding path
# can bypass the container's iptables FORWARD chain. Policy routing works
# at the kernel routing level — it cannot be bypassed.
#
# How it works:
#   1. Create a custom routing table (table 100) with ONLY internal routes
#   2. Add a blackhole default in that table (drops everything else)
#   3. Use "ip rule" to force all traffic from 10.47.0.0/16 through table 100
# =============================================================================

UE3_SUBNET="10.47.0.0/16"
DOCKER_NET="10.33.33.0/24"

# --- Step 1: Run the original network setup (creates ogstun, NAT, etc.) -----
source /usr/local/bin/helper_functions.sh
setup_container_interfaces "${@}"

echo "[upf3-firewall] Network setup complete. Applying internet-block rules..."

# --- Step 2: Identify the eth0 gateway for internal routing ------------------
ETH0_GW=$(ip route | grep "^default" | awk '{print $3}')
ETH0_DEV=$(ip route | grep "^default" | awk '{print $5}')
echo "[upf3-firewall] Detected gateway: ${ETH0_GW} via ${ETH0_DEV}"

# --- Step 3: Create custom routing table 100 (internal-only) ----------------
# Route to Docker internal network (mqtt, nodered, edge, core NFs)
ip route add ${DOCKER_NET} via ${ETH0_GW} dev ${ETH0_DEV} table 100

# Blackhole everything else — this is what blocks internet
ip route add blackhole default table 100

echo "[upf3-firewall] Routing table 100 created (internal-only + blackhole)"

# --- Step 4: Policy rule — force UE3 subnet traffic through table 100 -------
# Priority 100 ensures this is checked before the main table
ip rule add from ${UE3_SUBNET} lookup 100 priority 100

echo "[upf3-firewall] Policy rule applied: from ${UE3_SUBNET} → lookup table 100"

# --- Step 5: Also remove the blanket NAT as extra safety --------------------
iptables -t nat -D POSTROUTING -s ${UE3_SUBNET} ! -o ogstun -j MASQUERADE 2>/dev/null
# Add NAT only for internal traffic
iptables -t nat -A POSTROUTING -s ${UE3_SUBNET} -d ${DOCKER_NET} -j MASQUERADE

# --- Step 6: Print final state for verification -----------------------------
echo ""
echo "[upf3-firewall] === Policy rules ==="
ip rule show
echo ""
echo "[upf3-firewall] === Routing table 100 (UE3 traffic) ==="
ip route show table 100
echo ""
echo "[upf3-firewall] === Main routing table ==="
ip route show
echo ""
echo "[upf3-firewall] RESULT:"
echo "  UE3 (${UE3_SUBNET}) -> ${DOCKER_NET}  : ALLOWED (mqtt, nodered, edge)"
echo "  UE3 (${UE3_SUBNET}) -> internet       : BLOCKED (blackhole)"
echo "  UE1, UE2                               : NOT AFFECTED"
echo ""

# --- Step 7: Start the UPF daemon -------------------------------------------
exec open5gs-upfd "${@}"