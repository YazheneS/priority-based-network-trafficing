import React, { useEffect, useState, useRef } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from "recharts";

const WS_URL = `ws://${window.location.hostname}:4000/ws`;
const API_URL = `http://${window.location.hostname}:4000/api`;
const TIER_COLORS = { realtime: "#e74c3c", besteffort: "#f1c40f", bulk: "#2980b9" };
const MAX_POINTS = 60;

export default function App() {
  const [engineOn, setEngineOn] = useState(true);
  const [series, setSeries] = useState([]); // [{ t, realtime_jitter, besteffort_jitter, bulk_jitter }]
  const [controllerStatus, setControllerStatus] = useState(null);
  const wsRef = useRef(null);

  useEffect(() => {
    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onmessage = (msg) => {
      const parsed = JSON.parse(msg.data);
      if (parsed.type === "metrics") {
        applyMetrics(parsed.data);
      } else if (parsed.type === "toggle") {
        setEngineOn(parsed.enabled);
      }
    };

    return () => ws.close();
  }, []);

  function applyMetrics(data) {
    if (data.controller_status) {
      setControllerStatus(data.controller_status);
      setEngineOn(!!data.controller_status.priority_engine_on);
    }
    const events = data.events || [];
    // Bucket the most recent events into a rolling per-tier jitter series
    // for the chart (last MAX_POINTS events).
    const recent = events.slice(-MAX_POINTS);
    const points = recent.map((e, i) => ({
      idx: i,
      time: new Date(e.ts * 1000).toLocaleTimeString(),
      [`${e.tier}_jitter`]: e.jitter_ms,
    }));
    setSeries(points);
  }

  async function handleToggle() {
    const next = !engineOn;
    setEngineOn(next); // optimistic
    try {
      await fetch(`${API_URL}/toggle`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: next }),
      });
    } catch (e) {
      setEngineOn(!next); // revert on failure
      console.error("Toggle failed:", e);
    }
  }

  return (
    <div style={{ fontFamily: "system-ui, sans-serif", padding: "24px", maxWidth: 900, margin: "0 auto" }}>
      <h1 style={{ marginBottom: 4 }}>Campus Network Priority Dashboard</h1>
      <p style={{ color: "#666", marginTop: 0 }}>
        Live latency / jitter per traffic tier — real-time (video), best-effort (browsing), bulk (downloads).
      </p>

      <div style={{
        display: "flex", alignItems: "center", gap: 12, padding: "12px 16px",
        border: "1px solid #ddd", borderRadius: 8, marginBottom: 24, background: engineOn ? "#eafbea" : "#fdecea",
      }}>
        <strong>Priority Engine:</strong>
        <span style={{ fontWeight: 600, color: engineOn ? "#27ae60" : "#c0392b" }}>
          {engineOn ? "ON" : "OFF"}
        </span>
        <button
          onClick={handleToggle}
          style={{
            marginLeft: "auto", padding: "8px 16px", borderRadius: 6, border: "none",
            background: engineOn ? "#c0392b" : "#27ae60", color: "white", cursor: "pointer",
          }}
        >
          Turn {engineOn ? "OFF" : "ON"}
        </button>
      </div>

      <ResponsiveContainer width="100%" height={360}>
        <LineChart data={series}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="time" tick={{ fontSize: 10 }} minTickGap={30} />
          <YAxis label={{ value: "Jitter (ms)", angle: -90, position: "insideLeft" }} />
          <Tooltip />
          <Legend />
          <Line type="monotone" dataKey="realtime_jitter" name="Real-time (video)" stroke={TIER_COLORS.realtime} dot={false} connectNulls />
          <Line type="monotone" dataKey="besteffort_jitter" name="Best-effort (browsing)" stroke={TIER_COLORS.besteffort} dot={false} connectNulls />
          <Line type="monotone" dataKey="bulk_jitter" name="Bulk (downloads)" stroke={TIER_COLORS.bulk} dot={false} connectNulls />
        </LineChart>
      </ResponsiveContainer>

      {controllerStatus && (
        <div style={{ marginTop: 24, fontSize: 13, color: "#666" }}>
          <p>Connected switches (dpid): {controllerStatus.datapaths?.join(", ") || "none"}</p>
          <p>Flows installed recently: {controllerStatus.recent_flows?.length || 0}</p>
        </div>
      )}
    </div>
  );
}
