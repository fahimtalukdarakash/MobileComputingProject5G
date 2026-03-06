# Framework Frontend

[← Back to Main README](../README.md)

This document describes each HTML template in `framework/templates/`. The frontend is a set of single-page applications served by FastAPI via Jinja2. Each page is a self-contained HTML file with inline CSS and JavaScript — no build step, no frameworks, no bundler. Pages communicate with the backend REST API using `fetch()` calls.

---

## Table of Contents

1. [Overview](#1-overview)
   - 1.1 [Technology Stack](#11-technology-stack)
   - 1.2 [Navigation](#12-navigation)
   - 1.3 [Design System](#13-design-system)
   - 1.4 [Template Serving](#14-template-serving)
2. [topology.html — Network Topology Visualization](#2-topologyhtml--network-topology-visualization)
3. [control.html — Container and Network Management](#3-controlhtml--container-and-network-management)
   - 3.1 [Logs Tab](#31-logs-tab)
   - 3.2 [Configuration Tab](#32-configuration-tab)
   - 3.3 [Network Summary Tab](#33-network-summary-tab)
   - 3.4 [Transport Tab](#34-transport-tab)
   - 3.5 [Priority QoS Tab](#35-priority-qos-tab)
   - 3.6 [Resilience Tab](#36-resilience-tab)
4. [usecases.html — Use Case Simulator Dashboard](#4-usecaseshtml--use-case-simulator-dashboard)
5. [verify.html — Network Verification Tests](#5-verifyhtml--network-verification-tests)
6. [monitoring.html — Real-Time Resource Monitoring](#6-monitoringhtml--real-time-resource-monitoring)
7. [loadtest.html — Load Testing and Call Simulation](#7-loadtesthtml--load-testing-and-call-simulation)
   - 7.1 [UERANSIM vs PacketRusher Comparison](#71-ueransim-vs-packetrusher-comparison)
   - 7.2 [PacketRusher Controls](#72-packetrusher-controls)
   - 7.3 [GTP Tunnel Throughput](#73-gtp-tunnel-throughput)
   - 7.4 [Multi-UE Load Test](#74-multi-ue-load-test)
   - 7.5 [PacketRusher Topology](#75-packetrusher-topology)
   - 7.6 [Call Simulation](#76-call-simulation)
8. [basic-topology.html — Basic Mode Topology](#8-basic-topologyhtml--basic-mode-topology)
9. [Template–API Mapping](#9-templateapi-mapping)

---

## 1. Overview

### 1.1 Technology Stack

All templates are plain HTML5 with inline `<style>` and `<script>` blocks. External libraries are loaded from CDNs:

| Library | CDN URL | Used In | Purpose |
|---------|---------|---------|---------|
| vis-network | unpkg.com/vis-network/standalone | topology.html, loadtest.html, basic-topology.html | Interactive network graph visualization |
| Chart.js 4 | cdn.jsdelivr.net/npm/chart.js@4 | monitoring.html | CPU and memory charts |

No other dependencies. No React, no Vue, no build tools. Each file is completely self-contained.

### 1.2 Navigation

Every page shares a consistent top navbar with the project title and navigation links:

```
┌──────────────────────────────────────────────────────────────────────────┐
│  5G Network Slicing Framework    Topology  Control  Use Cases  Verify  Monitor  Load Test  │
└──────────────────────────────────────────────────────────────────────────┘
```

The active page is highlighted with a lighter background. Navigation links and their routes:

| Link | Route | Template |
|------|-------|----------|
| Topology | `/` | topology.html |
| Control | `/control` | control.html |
| Use Cases | `/usecases` | usecases.html |
| Verify | `/verify` | verify.html |
| Monitor | `/monitoring` | monitoring.html |
| Load Test | `/loadtest` | loadtest.html |

### 1.3 Design System

All pages use a consistent dark theme:

| Element | Color | Hex |
|---------|-------|-----|
| Page background | Dark navy | `#0f172a` |
| Panel/sidebar background | Dark slate | `#1e293b` |
| Border color | Medium slate | `#334155` |
| Primary text | Light gray | `#e2e8f0` |
| Secondary text | Muted gray | `#94a3b8` |
| Accent / highlight | Sky blue | `#38bdf8` |
| Success / running | Green | `#4ade80` |
| Error / stopped | Red | `#f87171` |
| Warning | Amber | `#fbbf24` |
| Slice indicator | Purple | `#c084fc` |

Common UI patterns across all pages include toast notifications (auto-dismissing success/error messages), loading spinners (CSS-only, animated border), status badges (`running` green, `stopped` red), and action buttons with hover effects.

The font stack is `'Segoe UI', system-ui, -apple-system, sans-serif` for body text and `'JetBrains Mono', monospace` for code/IP addresses.

### 1.4 Template Serving

Templates are served by FastAPI using Jinja2. The app.py registers a route for each page:

```python
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

@app.get("/", response_class=HTMLResponse)
def page_topology(request: Request):
    return templates.TemplateResponse("topology.html", {"request": request})

@app.get("/control", response_class=HTMLResponse)
def page_control(request: Request):
    return templates.TemplateResponse("control.html", {"request": request})
# ... same pattern for /usecases, /verify, /monitoring, /loadtest
```

Each template defines `const API = ''` (empty string, same origin) and uses `fetch(`${API}/api/...`)` for all backend calls.

---

## 2. topology.html — Network Topology Visualization

**Route:** `/` (home page)
**Lines:** ~445
**External library:** vis-network
**API calls:** `GET /api/topology/full`

The topology page is the landing page of the framework. It displays an interactive graph of all Docker containers as nodes, connected by edges representing network relationships. The page has a two-column layout: a sidebar on the left and the graph canvas on the right.

**Sidebar sections:**

The sidebar contains four sections. The **Status Summary** is a 2×2 grid showing total containers, running count, stopped count, and number of slices. The **Legend** section shows color-coded categories (Core CP, Slice 1 IoT, Slice 2 Vehicle, Slice 3 Restricted, RAN, Infrastructure) as clickable filter buttons. The **Slice Cards** display each slice with its SST/SD values, subnet, and internet access status (green "🌐 Internet Access" or red "🔒 Internal Only"). The **Node Detail** panel appears when a node is clicked, showing the container name, status badge, image, and network info (IP, gateway, MAC per network).

**Graph visualization:**

The `buildGraph()` function transforms the topology API response into vis-network nodes and edges. Nodes are color-coded by category and shaped by role: the gNB uses a diamond shape, infrastructure nodes (MongoDB, MQTT) use a database shape, and all others use boxes. Each node label shows the container name and IP address. Node positions are predefined in a `POSITIONS` constant for a clean layout, with physics optionally enabled for auto-arrangement.

**Toolbar buttons** in the top-right overlay: Refresh (re-fetches topology), Fit (zoom to fit all nodes), Physics Toggle (enable/disable force-directed layout). The filter buttons in the sidebar allow hiding/showing entire categories — clicking "Slice 1" hides all IoT-related nodes.

**Auto-refresh:** The topology fetches on page load via `fetchTopology()`. Manual refresh via the toolbar button.

---

## 3. control.html — Container and Network Management

**Route:** `/control`
**Lines:** ~1014 (the largest template)
**External libraries:** none
**API calls:** 22 different endpoints

The control page is the main management interface. It has a split layout: the left panel shows a container table with action buttons, and the right panel has a tabbed interface with 6 tabs.

**Left panel — Container table:**

Shows all running containers in a table with columns for name, status, and actions. Each row has Restart and Stop buttons. Global action buttons at the top: Start All, Stop All, Restart All. The container list refreshes via `GET /api/control/containers`.

**Right panel — 6 tabs:**

### 3.1 Logs Tab

The default active tab. Provides a container log viewer with two dropdown selectors: container name and number of lines (30, 50, 100, 200). Selecting a container triggers `GET /api/control/logs/{name}?lines={n}` and displays the output in a scrollable monospace pre-formatted block. Logs auto-refresh when the container selection changes.

### 3.2 Configuration Tab

A YAML configuration editor. The left side lists available config files loaded from `GET /api/config/files`. Clicking a file loads its content via `GET /api/config/read/{filename}` into a textarea editor. The Save button sends the modified content via `POST /api/config/write` with the filename and content in the request body. This allows live editing of Open5GS and UERANSIM YAML configurations without SSH access.

### 3.3 Network Summary Tab

Displays a high-level overview of all 3 slices loaded from `GET /api/config/summary`. Shows per-slice information: SMF/UPF container names, IP subnet, S-NSSAI (SST/SD), connected UEs, and internet access status. Also shows the shared control plane NFs (AMF, NRF, AUSF, UDM, UDR, NSSF, BSF, PCF) and their configuration.

### 3.4 Transport Tab

Per-slice QoS management interface. Loads current transport status from `GET /api/transport/status`. For each slice, displays a card showing the UPF name, currently active QoS profile, and applied parameters (bandwidth ↓↑, latency, jitter, loss).

Each slice card has a profile dropdown selector (IoT Default, Vehicle/URLLC, eMBB, Emergency, Restricted, Degraded) with an "Apply" button that calls `POST /api/transport/apply/{sliceId}?profile={id}`. Custom value inputs allow setting arbitrary bandwidth, latency, jitter, and loss values. A "Clear" button per slice calls `POST /api/transport/clear/{sliceId}`.

Global controls at the top: "Auto-Configure" (calls `POST /api/transport/auto-configure`) applies the correct QoS profile per active use case, and "Clear All Rules" (calls `POST /api/transport/clear-all`) removes all tc shaping.

Raw `tc` output from each UPF and UE container is displayed in expandable sections for debugging.

### 3.5 Priority QoS Tab

Demonstrates priority-based bandwidth allocation under contention. Creates a shared bandwidth bottleneck on the Edge server where Slice 1 (IoT) and Slice 2 (Vehicle) compete simultaneously. The interface has preset buttons for different scenarios and a duration slider.

Clicking "Run Test" calls `POST /api/priority/test?duration={s}&preset={p}` and starts polling `GET /api/priority/task/{taskId}` for progress updates. Results show bandwidth allocation per slice, proving that priority classes guarantee IoT minimum bandwidth even under Vehicle traffic load.

### 3.6 Resilience Tab

Tests slice isolation under failure conditions. The automated test stops Slice 1 and Slice 2, then verifies that Slice 3 continues operating independently, and finally restarts everything and confirms recovery.

The interface shows a step-by-step timeline with status indicators per phase. Clicking "Run Test" calls `POST /api/resilience/test?stop=slice1,slice2&verify=slice3` and polls `GET /api/resilience/task/{taskId}`. Results display in a 4-column grid: Slice 1 stopped, Slice 2 stopped, Slice 3 verified, and recovery complete.

---

## 4. usecases.html — Use Case Simulator Dashboard

**Route:** `/usecases`
**Lines:** ~322
**External libraries:** none
**API calls:** `GET /api/usecases`, `POST /api/usecases/start/{id}`, `POST /api/usecases/stop/{id}`, `POST /api/usecases/start-all`, `POST /api/usecases/stop-all`, `GET /api/usecases/logs/{id}`

Displays all 5 use case simulators as cards in a grid layout. Each card shows the use case name, icon, slice assignment, protocol (MQTT or HTTP), current status (running/stopped), and Start/Stop buttons.

**Card layout per use case:**

```
┌─────────────────────────────────────┐
│  🌡 Environmental IoT               │
│  Slice 1 • MQTT • iot/ue-iot-01    │
│  ● Running                          │
│  [View Logs]  [Stop]                │
└─────────────────────────────────────┘
```

Global action bar at the top: "Start All" launches all 5 simulators plus auto-configures QoS, "Stop All" stops everything and clears QoS rules.

The "View Logs" button opens a modal overlay that loads the last 30 lines of the simulator container's logs via `GET /api/usecases/logs/{id}`. The log modal has a monospace dark background with auto-scrolling to the bottom.

The `refresh()` function polls `GET /api/usecases` and updates each card's status badge and button states. Toast notifications provide feedback for start/stop actions.

---

## 5. verify.html — Network Verification Tests

**Route:** `/verify`
**Lines:** ~323
**External libraries:** none
**API calls:** `POST /api/tests/full`, `POST /api/tests/isolation`, `POST /api/tests/health`, `POST /api/tests/throughput?client={}&server={}&duration={}`

The verification page runs automated network tests and displays results. It has two main sections: the test results area and the throughput test section.

**Test results area:**

The "Run Full Tests" button triggers `POST /api/tests/full` which runs all 7 ping tests across all 3 UEs. Results are grouped by UE and displayed as cards. Each test shows the target, result status (PASS ✅ or FAIL ❌), and raw ping output. The UE3 internet test is expected to fail (shown as a PASS in the isolation context since it proves blocking works).

Additional buttons: "Run Isolation Test" runs only the Slice 3 internet blocking test. "Run Health Check" tests basic connectivity to all services.

**Throughput test section:**

A form at the bottom with dropdowns for client UE (UE1 IoT, UE2 Vehicle, UE3 Restricted), server target (Edge Server, MQTT Broker, Internet 8.8.8.8), and duration (5, 10, 30 seconds). Clicking "Run" triggers `POST /api/tests/throughput` and displays upload/download Mbps results with a summary card. This uses iperf3 internally and reflects any active QoS rules (bandwidth limits from the Transport tab).

---

## 6. monitoring.html — Real-Time Resource Monitoring

**Route:** `/monitoring`
**Lines:** ~369
**External library:** Chart.js 4
**API calls:** `GET /api/monitoring/dashboard`, `GET /api/monitoring/mqtt`

The monitoring page provides real-time visibility into container resource usage and MQTT message flow. It auto-refreshes every 5 seconds via `setInterval(fetchAll, 5000)`.

**Charts row (top):**

Two Chart.js line charts side by side. The CPU chart shows per-container CPU usage percentage over time (rolling window). The memory chart shows per-container memory consumption in MB. Both charts use the dark theme colors and update incrementally — new data points are pushed while old ones shift off the left edge.

The `initCharts()` function creates the Chart.js instances on page load. `updateCpuChart()` and `updateMemChart()` append new data points from each API poll.

**Resource table:**

Below the charts, a table lists all containers with their current CPU%, memory usage (MB), network I/O (bytes in/out), and PIDs. Data comes from `GET /api/monitoring/dashboard` which runs `docker stats` internally.

**UE status cards:**

Cards for each UE showing their tunnel interface status, IP address, and real-time traffic counters. Each card displays the UE name, assigned slice, tunnel IP (from uesimtun0), and bytes sent/received through the GTP tunnel.

**MQTT activity:**

A separate section showing recent MQTT messages fetched from `GET /api/monitoring/mqtt`. Displays the topic, payload preview, and timestamp for the most recent messages across all subscribed topics (iot/*, veh/*).

**Pause/resume:** A toggle button pauses the auto-refresh interval for inspecting a snapshot without it scrolling away.

---

## 7. loadtest.html — Load Testing and Call Simulation

**Route:** `/loadtest`
**Lines:** ~874 (second largest template)
**External library:** vis-network
**API calls:** 10 different endpoints

The most feature-rich page, combining PacketRusher load testing, GTP throughput measurement, multi-UE stress testing, a topology diagram, and call simulation. The page is divided into panels arranged in a grid layout.

### 7.1 UERANSIM vs PacketRusher Comparison

An informational panel at the top explaining the difference between the two RAN simulators:

| | UERANSIM | PacketRusher |
|--|----------|--------------|
| Purpose | Functional testing | Performance testing |
| UEs | 3 (one per slice) | N (configurable) |
| Focus | Slicing, PDU sessions, use cases | Multi-UE load, registration stress |
| Throughput | Per-slice via UPF | GTP tunnel via UPF |

### 7.2 PacketRusher Controls

A control panel showing PacketRusher status (running/stopped), iperf-server status, and provisioned subscriber count. Action buttons: "Provision Subscribers" (calls `POST /api/loadtest/provision?count={n}`), "Start PacketRusher" (`POST /api/loadtest/start`), "Stop" (`POST /api/loadtest/stop`). Status refreshes via `GET /api/loadtest/status`.

### 7.3 GTP Tunnel Throughput

A test panel with a duration input and "Run" button. Calls `POST /api/loadtest/gtp-throughput?duration={s}` which is a long-running task. The UI polls `GET /api/loadtest/task/{taskId}` for progress using `pollTask()`. Results display upload and download Mbps in highlighted result cards, with a note explaining that traffic flows through the real GTP-U tunnel via UPF.

### 7.4 Multi-UE Load Test

A stress test panel with a UE count input (default: 5). Calls `POST /api/loadtest/multi-ue?count={n}`. Polls for completion and displays results: total elapsed time, number of successful registrations, errors detected, and average registration time per UE in milliseconds. The raw PacketRusher output is shown in a scrollable log area.

### 7.5 PacketRusher Topology

An embedded vis-network graph (smaller than the main topology page) showing the PacketRusher-specific network: PacketRusher gNB, connected UEs, AMF, SMF1, UPF1, and the iperf-server. Uses the same vis-network rendering approach as the main topology page but with a focused subset of nodes. The `showTopology()` function creates this diagram.

### 7.6 Call Simulation

A call simulation panel that is initially disabled (grayed out with `opacity: 0.4; pointer-events: none`). It becomes active after a successful multi-UE load test via the `enableCallSim()` function.

Once enabled, the panel provides dropdowns for caller UE, callee UE, and call type (Voice 📞, Video 📹, Emergency 112 🚨). The "Initiate Call" button calls `POST /api/call/initiate?caller={}&callee={}&call_type={}`.

During an active call, the UI shows a live signaling log with color-coded entries (NAS=blue, SMF=green, SIP=purple, RTP=cyan, EMERGENCY=red). A data flow visualization at the top shows: `caller · · · · · callee` with the MQTT topic displayed below.

The call status is polled every second via `GET /api/call/status`, updating live packet counters (sent/received), byte counters, and call duration. The "Terminate Call" button calls `POST /api/calls/terminate`.

The UE dropdowns are dynamically populated by `populateUEDropdowns()` which creates options for all available UEs across all slices, including both UERANSIM UEs and PacketRusher UEs. The `getUEInfo()` helper returns metadata (slice, IP, type) for display in the call flow.

---

## 8. basic-topology.html — Basic Mode Topology

**Route:** served separately for the basic (non-slicing) deployment
**Lines:** ~438
**External library:** vis-network
**API calls:** `GET /api/topology/full`

A variant of the main topology page designed for the basic Open5GS deployment (single SMF, single UPF, no slicing). It shares the same codebase structure as topology.html — sidebar with status summary and node details, vis-network graph with the same dark theme, toolbar buttons for refresh/fit/physics.

The key difference is the simplified network: instead of 3 slices with separate SMF/UPF pairs, it shows a single SMF and single UPF. The slice cards section shows only one slice. This page is used during the presentation to demonstrate the basic 5G architecture before switching to the full network slicing setup.

---

## 9. Template–API Mapping

Summary of which templates call which API endpoints:

| Template | API Endpoints Used |
|----------|-------------------|
| **topology.html** | `GET /api/topology/full` |
| **control.html** | `GET /api/control/containers`, `POST /api/control/{action}`, `POST /api/control/{action}/{name}`, `GET /api/control/logs/{name}`, `GET /api/config/files`, `GET /api/config/read/{file}`, `POST /api/config/write`, `GET /api/config/summary`, `GET /api/transport/status`, `POST /api/transport/apply/{slice}`, `POST /api/transport/clear/{slice}`, `POST /api/transport/clear-all`, `POST /api/transport/auto-configure`, `GET /api/slice/status`, `POST /api/slice/{action}/{slice}`, `POST /api/priority/test`, `GET /api/priority/task/{id}`, `POST /api/priority/clear`, `POST /api/resilience/test`, `GET /api/resilience/task/{id}` |
| **usecases.html** | `GET /api/usecases`, `POST /api/usecases/start/{id}`, `POST /api/usecases/stop/{id}`, `POST /api/usecases/start-all`, `POST /api/usecases/stop-all`, `GET /api/usecases/logs/{id}` |
| **verify.html** | `POST /api/tests/full`, `POST /api/tests/isolation`, `POST /api/tests/health`, `POST /api/tests/throughput` |
| **monitoring.html** | `GET /api/monitoring/dashboard`, `GET /api/monitoring/mqtt` |
| **loadtest.html** | `GET /api/loadtest/status`, `POST /api/loadtest/provision`, `POST /api/loadtest/start`, `POST /api/loadtest/stop`, `POST /api/loadtest/gtp-throughput`, `POST /api/loadtest/multi-ue`, `GET /api/loadtest/task/{id}`, `POST /api/call/initiate`, `POST /api/call/terminate`, `GET /api/call/status` |
| **basic-topology.html** | `GET /api/topology/full` |

---

## File Sizes

| Template | Lines | Size | Key Feature |
|----------|-------|------|-------------|
| control.html | ~1014 | 59 KB | 6-tab management interface |
| loadtest.html | ~874 | 46 KB | Load test + call simulation |
| topology.html | ~445 | 20 KB | vis-network interactive graph |
| basic-topology.html | ~438 | 20 KB | Basic mode graph variant |
| monitoring.html | ~369 | 17 KB | Chart.js real-time dashboards |
| verify.html | ~323 | 18 KB | Automated test runner + iperf3 |
| usecases.html | ~322 | 15 KB | Simulator card grid + log modal |