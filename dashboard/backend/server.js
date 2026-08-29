/**
 * server.js
 * ----------
 * Week 8 deliverable: live monitoring dashboard backend.
 *
 * Responsibilities:
 *   1. Watch metrics_store.json (written by integration/bridge.py) and
 *      push updates to connected dashboard clients over WebSocket, so the
 *      frontend chart updates live as traffic flows.
 *   2. Proxy the ON/OFF toggle to the os-ken controller's REST API
 *      (POST /toggle), so flipping the switch in the UI immediately
 *      changes how the controller installs flows (Week 5's
 *      set_priority_engine hook).
 *
 * Run:
 *   cd dashboard/backend
 *   npm install express ws chokidar node-fetch
 *   node server.js
 */

const express = require("express");
const http = require("http");
const WebSocket = require("ws");
const fs = require("fs");
const path = require("path");
const chokidar = require("chokidar");
const fetch = require("node-fetch");

const PORT = process.env.PORT || 4000;
const CONTROLLER_URL = process.env.CONTROLLER_URL || "http://127.0.0.1:8080";
const METRICS_PATH = path.join(__dirname, "metrics_store.json");

const app = express();
app.use(express.json());
app.use(express.static(path.join(__dirname, "..", "frontend", "build"))); // serves the built React app

const server = http.createServer(app);
const wss = new WebSocket.Server({ server, path: "/ws" });

function readMetrics() {
  try {
    const raw = fs.readFileSync(METRICS_PATH, "utf-8");
    return JSON.parse(raw);
  } catch (err) {
    return { events: [], controller_status: null };
  }
}

function broadcast(data) {
  const payload = JSON.stringify(data);
  wss.clients.forEach((client) => {
    if (client.readyState === WebSocket.OPEN) client.send(payload);
  });
}

// Push fresh metrics to every connected client whenever the store file changes.
chokidar.watch(METRICS_PATH).on("change", () => {
  broadcast({ type: "metrics", data: readMetrics() });
});

wss.on("connection", (ws) => {
  ws.send(JSON.stringify({ type: "metrics", data: readMetrics() }));
});

// --- REST endpoints (also usable without the WebSocket, e.g. curl/testing) ---

app.get("/api/metrics", (req, res) => {
  res.json(readMetrics());
});

app.post("/api/toggle", async (req, res) => {
  const enabled = !!req.body.enabled;
  try {
    const r = await fetch(`${CONTROLLER_URL}/toggle`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled }),
    });
    const data = await r.json();
    broadcast({ type: "toggle", enabled });
    res.json(data);
  } catch (err) {
    res.status(502).json({ ok: false, msg: String(err) });
  }
});

server.listen(PORT, () => {
  console.log(`Dashboard backend listening on http://localhost:${PORT}`);
  console.log(`Proxying priority-engine toggle to controller at ${CONTROLLER_URL}`);
});
