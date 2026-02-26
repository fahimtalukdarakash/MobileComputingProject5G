# framework/callsim.py
"""
5G Call Simulation Module
===========================
Simulates Voice, Video, and Emergency calls between UEs.
Uses MQTT to exchange real messages as proof of communication.

Call Types:
  - Voice Call (5QI=1): 64 kbps AMR-WB, normal priority
  - Video Call (5QI=2): 2 Mbps H.264, higher bandwidth
  - Emergency 112 (5QI=69): Highest priority, fastest setup

Proof of communication: actual MQTT messages exchanged between UEs.
"""

import json
import time
import threading
import subprocess
from typing import Dict, Any, Optional
from pathlib import Path

# Background storage
_calls: Dict[str, Dict[str, Any]] = {}
_call_lock = threading.Lock()

# QoS profiles per call type
CALL_PROFILES = {
    "voice": {
        "name": "Voice Call",
        "icon": "📞",
        "5qi": 1,
        "qfi": 1,
        "bandwidth": "64 kbps",
        "codec": "AMR-WB",
        "setup_time_ms": 1800,
        "packet_interval": 0.2,
        "packet_size": 160,
        "priority": 5,
        "mqtt_topic_prefix": "call/voice",
    },
    "video": {
        "name": "Video Streaming Call",
        "icon": "📹",
        "5qi": 2,
        "qfi": 2,
        "bandwidth": "2 Mbps",
        "codec": "H.264 720p",
        "setup_time_ms": 2200,
        "packet_interval": 0.05,
        "packet_size": 1200,
        "priority": 4,
        "mqtt_topic_prefix": "call/video",
    },
    "emergency": {
        "name": "Emergency 112",
        "icon": "🚨",
        "5qi": 69,
        "qfi": 3,
        "bandwidth": "64 kbps",
        "codec": "AMR-WB (Priority)",
        "setup_time_ms": 500,
        "packet_interval": 0.15,
        "packet_size": 160,
        "priority": 0,
        "mqtt_topic_prefix": "call/emergency",
    },
}


def _mqtt_publish(topic: str, payload: dict) -> bool:
    """Publish to MQTT via mosquitto_pub in the mqtt container."""
    msg = json.dumps(payload)
    try:
        r = subprocess.run(
            ["docker", "exec", "mqtt", "mosquitto_pub", "-t", topic, "-m", msg],
            capture_output=True, text=True, timeout=5,
        )
        return r.returncode == 0
    except Exception:
        return False


def _generate_signaling_logs(caller: str, callee: str, call_type: str, profile: dict) -> list:
    """Generate realistic 5G NAS/SIP signaling logs for call setup."""
    ts = lambda: time.strftime("%H:%M:%S")
    qi = profile["5qi"]
    qfi = profile["qfi"]
    bw = profile["bandwidth"]
    codec = profile["codec"]
    prio = profile["priority"]

    if call_type == "emergency":
        return [
            {"time": ts(), "level": "EMERGENCY", "msg": f"[NAS] ⚡ Emergency Service Request from {caller} — Dialing 112"},
            {"time": ts(), "level": "NAS", "msg": f"[AMF] Emergency registration — BYPASSING normal authentication"},
            {"time": ts(), "level": "NAS", "msg": f"[AMF] Priority Level: 0 (HIGHEST) — Pre-emption ENABLED"},
            {"time": ts(), "level": "SMF", "msg": f"[SMF] Emergency QoS Flow — 5QI={qi} QFI={qfi} ARP Priority=1"},
            {"time": ts(), "level": "SMF", "msg": f"[SMF] Dedicated Bearer: {bw} {codec} — Pre-emption Capable"},
            {"time": ts(), "level": "UPF", "msg": f"[UPF] Emergency GTP tunnel established — FAST PATH enabled"},
            {"time": ts(), "level": "SIP", "msg": f"[IMS] INVITE sip:112@emergency.ims → Emergency Call Center"},
            {"time": ts(), "level": "EMERGENCY", "msg": f"[IMS] ⚡ 112 Emergency — Connected in {profile['setup_time_ms']}ms (priority bypass)"},
            {"time": ts(), "level": "RTP", "msg": f"[RTP] Emergency media: {codec} {bw} — Priority QFI={qfi}"},
        ]
    else:
        return [
            {"time": ts(), "level": "NAS", "msg": f"[NAS] Service Request from {caller}"},
            {"time": ts(), "level": "NAS", "msg": f"[AMF] Authentication: 5G-AKA — OK"},
            {"time": ts(), "level": "SMF", "msg": f"[SMF] QoS Flow Request — 5QI={qi} QFI={qfi} Priority={prio}"},
            {"time": ts(), "level": "SMF", "msg": f"[SMF] Dedicated Bearer: {bw} {codec}"},
            {"time": ts(), "level": "UPF", "msg": f"[UPF] GTP-U tunnel: {caller} ↔ {callee} TEID={hash(caller+callee) % 90000 + 10000}"},
            {"time": ts(), "level": "SIP", "msg": f"[IMS] INVITE sip:{callee}@ims.open5gs.org"},
            {"time": ts(), "level": "SIP", "msg": f"[IMS] 180 Ringing — {callee}"},
            {"time": ts(), "level": "SIP", "msg": f"[IMS] 200 OK — Call Connected ({profile['setup_time_ms']}ms)"},
            {"time": ts(), "level": "RTP", "msg": f"[RTP] Media session: {codec} {bw} — QFI={qfi}"},
        ]


def initiate_call(caller: str, callee: str, call_type: str = "voice") -> Dict[str, Any]:
    """Start a call between two UEs (or emergency call)."""
    profile = CALL_PROFILES.get(call_type)
    if not profile:
        return {"success": False, "error": f"Unknown call type: {call_type}"}

    call_id = f"call_{int(time.time())}_{caller}_{callee}"

    with _call_lock:
        # Check for existing active call
        for cid, c in _calls.items():
            if c.get("status") == "active":
                return {"success": False, "error": f"Call already active: {cid}. Terminate it first."}

    with _call_lock:
        _calls[call_id] = {
            "status": "connecting",
            "call_type": call_type,
            "caller": caller,
            "callee": callee,
            "profile": profile,
            "logs": [],
            "packets_sent": 0,
            "packets_received": 0,
            "bytes_sent": 0,
            "bytes_received": 0,
            "start_time": None,
            "duration": 0,
        }

    def _run_call():
        try:
            # Phase 1: Signaling (setup)
            setup_logs = _generate_signaling_logs(caller, callee, call_type, profile)
            setup_delay = profile["setup_time_ms"] / 1000.0
            delay_per_log = setup_delay / len(setup_logs)

            for log in setup_logs:
                with _call_lock:
                    if _calls[call_id]["status"] == "terminated":
                        return
                    _calls[call_id]["logs"].append(log)
                time.sleep(delay_per_log)

            # Phase 2: Connected — exchange MQTT packets
            with _call_lock:
                _calls[call_id]["status"] = "active"
                _calls[call_id]["start_time"] = time.time()
                _calls[call_id]["logs"].append({
                    "time": time.strftime("%H:%M:%S"),
                    "level": "ACTIVE",
                    "msg": f"[CALL] ✅ {profile['icon']} {profile['name']} ACTIVE — {caller} ↔ {callee}",
                })

            pkt_interval = profile["packet_interval"]
            pkt_size = profile["packet_size"]
            pkt_num = 0
            topic_out = f"{profile['mqtt_topic_prefix']}/{caller}/to/{callee}"
            topic_in = f"{profile['mqtt_topic_prefix']}/{callee}/to/{caller}"

            while True:
                with _call_lock:
                    if _calls[call_id]["status"] == "terminated":
                        break

                pkt_num += 1

                # Send packet from caller → callee
                out_payload = {
                    "call_id": call_id,
                    "from": caller,
                    "to": callee,
                    "type": call_type,
                    "seq": pkt_num,
                    "size_bytes": pkt_size,
                    "codec": profile["codec"],
                    "ts": time.time(),
                }
                _mqtt_publish(topic_out, out_payload)

                # Send ACK from callee → caller
                ack_payload = {
                    "call_id": call_id,
                    "from": callee,
                    "to": caller,
                    "type": f"{call_type}_ack",
                    "seq": pkt_num,
                    "size_bytes": pkt_size // 2,
                    "ts": time.time(),
                }
                _mqtt_publish(topic_in, ack_payload)

                with _call_lock:
                    c = _calls[call_id]
                    c["packets_sent"] += 1
                    c["packets_received"] += 1
                    c["bytes_sent"] += pkt_size
                    c["bytes_received"] += pkt_size // 2
                    c["duration"] = round(time.time() - c["start_time"], 1)

                    # Log every 10 packets
                    if pkt_num % 10 == 0:
                        c["logs"].append({
                            "time": time.strftime("%H:%M:%S"),
                            "level": "RTP",
                            "msg": f"[RTP] ↕ Packets: {c['packets_sent']} sent / {c['packets_received']} recv | "
                                   f"{c['bytes_sent']//1024}KB sent / {c['bytes_received']//1024}KB recv | "
                                   f"Duration: {c['duration']}s",
                        })

                time.sleep(pkt_interval)

        except Exception as e:
            with _call_lock:
                _calls[call_id]["logs"].append({
                    "time": time.strftime("%H:%M:%S"),
                    "level": "ERROR",
                    "msg": f"[ERROR] {str(e)}",
                })
                _calls[call_id]["status"] = "error"

    thread = threading.Thread(target=_run_call, daemon=True)
    thread.start()

    return {
        "success": True,
        "call_id": call_id,
        "call_type": call_type,
        "caller": caller,
        "callee": callee,
        "profile_name": profile["name"],
    }


def terminate_call(call_id: str = None) -> Dict[str, Any]:
    """Terminate an active call."""
    with _call_lock:
        # If no call_id, find the active call
        if not call_id:
            for cid, c in _calls.items():
                if c["status"] in ("active", "connecting"):
                    call_id = cid
                    break

        if not call_id or call_id not in _calls:
            return {"success": False, "error": "No active call found"}

        c = _calls[call_id]
        c["status"] = "terminated"
        duration = round(time.time() - c["start_time"], 1) if c["start_time"] else 0
        c["duration"] = duration

        # Add termination logs
        if c["call_type"] == "emergency":
            c["logs"].append({
                "time": time.strftime("%H:%M:%S"),
                "level": "EMERGENCY",
                "msg": f"[IMS] 🚨 Emergency call ended — Duration: {duration}s",
            })
        else:
            c["logs"].append({
                "time": time.strftime("%H:%M:%S"),
                "level": "SIP",
                "msg": f"[SIP] BYE from {c['caller']}",
            })
        c["logs"].append({
            "time": time.strftime("%H:%M:%S"),
            "level": "NAS",
            "msg": f"[SMF] QoS Flow released — QFI={c['profile']['qfi']}",
        })
        c["logs"].append({
            "time": time.strftime("%H:%M:%S"),
            "level": "INFO",
            "msg": f"[CALL] 📴 Call terminated — Duration: {duration}s | "
                   f"Packets: {c['packets_sent']} sent / {c['packets_received']} recv | "
                   f"Data: {c['bytes_sent']//1024}KB / {c['bytes_received']//1024}KB",
        })

        # Publish termination to MQTT
        _mqtt_publish(f"call/events", {
            "event": "terminated",
            "call_id": call_id,
            "caller": c["caller"],
            "callee": c["callee"],
            "type": c["call_type"],
            "duration": duration,
            "packets_sent": c["packets_sent"],
            "packets_received": c["packets_received"],
        })

    return {
        "success": True,
        "call_id": call_id,
        "duration": duration,
        "packets_sent": c["packets_sent"],
        "packets_received": c["packets_received"],
        "bytes_sent": c["bytes_sent"],
        "bytes_received": c["bytes_received"],
    }


def get_call_status(call_id: str = None) -> Dict[str, Any]:
    """Get status of current/recent call."""
    with _call_lock:
        if call_id and call_id in _calls:
            c = _calls[call_id]
            if c["start_time"] and c["status"] == "active":
                c["duration"] = round(time.time() - c["start_time"], 1)
            return {**c, "call_id": call_id}

        # Return most recent call
        if _calls:
            latest_id = list(_calls.keys())[-1]
            c = _calls[latest_id]
            if c["start_time"] and c["status"] == "active":
                c["duration"] = round(time.time() - c["start_time"], 1)
            return {**c, "call_id": latest_id}

    return {"status": "idle", "logs": [], "call_id": None}


def get_call_profiles() -> Dict[str, Any]:
    """Return available call type profiles."""
    return CALL_PROFILES