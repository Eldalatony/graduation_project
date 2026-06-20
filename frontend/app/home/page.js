'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Navbar from '../components/Navbar';
import ApplianceCard from '../components/ApplianceCard';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:3001';

export default function Home() {
  const router = useRouter();
  const [readings, setReadings] = useState({});
  const [error, setError] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [dash, setDash] = useState(null);
  const [dashError, setDashError] = useState(null);

  // ── Live readings poll (every 1s) ───────────────────────────────────────────
  useEffect(() => {
    const token = localStorage.getItem('token');
    if (!token) {
      router.replace('/auth');
      return;
    }

    let cancelled = false;

    const fetchLive = async () => {
      const tok = localStorage.getItem('token');
      try {
        const res = await fetch(`${API_URL}/api/live`, {
          headers: { Authorization: `Bearer ${tok}` },
        });
        if (res.status === 401) {
          localStorage.removeItem('token');
          router.replace('/auth');
          return;
        }
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (cancelled) return;
        setReadings(data);
        setError(null);
        setLastUpdated(new Date());
      } catch (err) {
        if (cancelled) return;
        setError(err.message);
      }
    };

    fetchLive();
    const interval = setInterval(fetchLive, 1000);
    return () => { cancelled = true; clearInterval(interval); };
  }, [router]);

  // ── Dashboard summary poll (every 30s) ──────────────────────────────────────
  useEffect(() => {
    let cancelled = false;

    const fetchDash = async () => {
      const tok = localStorage.getItem('token');
      if (!tok) return;
      try {
        const res = await fetch(`${API_URL}/api/ui/dashboard`, {
          headers: { Authorization: `Bearer ${tok}` },
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json = await res.json();
        if (cancelled) return;
        setDash(json.data || json);
        setDashError(null);
      } catch (err) {
        if (cancelled) return;
        setDashError(err.message);
      }
    };

    fetchDash();
    const interval = setInterval(fetchDash, 30000);
    return () => { cancelled = true; clearInterval(interval); };
  }, []);

  const entries = Object.entries(readings);

  return (
    <>
      <Navbar activePage="home" />
      <main style={{ padding: 24, fontFamily: 'system-ui, sans-serif', maxWidth: 1100, margin: '0 auto' }}>
        <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
          <h1 style={{ margin: 0, fontSize: 22 }}>Live Energy Dashboard</h1>
          <div style={{ fontSize: 13, color: error ? '#c00' : '#080' }}>
            {error
              ? `● Disconnected (${error})`
              : `● Connected${lastUpdated ? ` — updated ${lastUpdated.toLocaleTimeString()}` : ''}`}
          </div>
        </header>

        <DashboardSummary dash={dash} error={dashError} />

        <h2 style={{ fontSize: 18, marginTop: 32, marginBottom: 12 }}>Live Readings</h2>
        {entries.length === 0 ? (
          <div style={{ padding: 40, textAlign: 'center', color: '#666', border: '1px dashed #ccc', borderRadius: 8 }}>
            Waiting for readings… make sure the simulator (or ESP) is publishing to <code>home/gateway/data</code>.
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: 16 }}>
            {entries.map(([key, r]) => (
              <ApplianceCard
                key={key}
                name={r.appliance_name}
                nodeKey={r.node_key}
                gatewayId={r.gateway_id}
                reading={r}
              />
            ))}
          </div>
        )}
      </main>
    </>
  );
}

// ──────────────────────────────────────────────────────────────────────────────
// DashboardSummary — real data from /api/ui/dashboard (KPIs, charts, alerts).
// ──────────────────────────────────────────────────────────────────────────────
function DashboardSummary({ dash, error }) {
  if (error) {
    return (
      <div style={{ background: '#fef2f2', padding: 12, borderRadius: 8, fontSize: 13, color: '#991b1b', marginBottom: 24, border: '1px solid #fecaca' }}>
        Could not load dashboard summary ({error}). Live readings below are unaffected.
      </div>
    );
  }
  if (!dash) {
    return (
      <div style={{ padding: 40, textAlign: 'center', color: '#94a3b8', fontSize: 14, marginBottom: 24 }}>
        Loading dashboard…
      </div>
    );
  }

  const kpis = dash.kpi_cards || [];
  const peak = dash.peak_hours || {};
  const peakValues = peak.datasets?.[0]?.data || [];
  const peakColors = peak.datasets?.[0]?.backgroundColor || [];
  const peakMax = Math.max(...peakValues, 1);
  const costMeta = dash.cost_donut?.meta || [];
  const recentAlerts = dash.recent_alerts || [];

  return (
    <>
      {/* Model readiness line */}
      {(dash.models_ready != null) && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, color: '#475569',
          background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 6, padding: '6px 12px', marginBottom: 16,
        }}>
          <span style={{ color: '#10b981' }}>●</span>
          {dash.models_ready} model{dash.models_ready === 1 ? '' : 's'} ready
          {dash.models_learning > 0 && (
            <span style={{ color: '#f59e0b' }}> · {dash.models_learning} still learning</span>
          )}
        </div>
      )}

      {/* KPI cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 16, marginBottom: 24 }}>
        {kpis.map(k => (
          <div key={k.id || k.label} style={{ border: '1px solid #e2e8f0', borderRadius: 8, padding: 16, background: '#fff', borderTop: `4px solid ${k.color}` }}>
            <div style={{ fontSize: 12, color: '#666', marginBottom: 4 }}>
              {k.label}
            </div>
            <div style={{ fontSize: 28, fontWeight: 600 }}>
              {typeof k.value === 'number' ? k.value.toLocaleString() : k.value}{' '}
              <span style={{ fontSize: 13, color: '#888' }}>{k.unit}</span>
            </div>
            {k.sub_label && <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 4 }}>{k.sub_label}</div>}
          </div>
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 16, marginBottom: 24 }}>
        {/* Peak hours bar chart */}
        <div style={{ border: '1px solid #e2e8f0', borderRadius: 8, padding: 16, background: '#fff' }}>
          <h3 style={{ fontSize: 14, margin: '0 0 12px 0' }}>
            Peak Hours (kWh by hour)
            {peak.peak_hour_label && (
              <span style={{ fontSize: 12, color: '#6366f1', fontWeight: 400 }}> · peak at {peak.peak_hour_label}</span>
            )}
          </h3>
          <div style={{ display: 'flex', alignItems: 'flex-end', gap: 3, height: 140 }}>
            {peakValues.map((v, h) => (
              <div key={h} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center' }} title={`${String(h).padStart(2, '0')}:00 — ${v} kWh`}>
                <div style={{
                  width: '100%',
                  height: `${(v / peakMax) * 100}%`,
                  background: peakColors[h] || '#a5b4fc',
                  borderRadius: '3px 3px 0 0',
                  minHeight: v > 0 ? 2 : 0,
                }} />
                {h % 4 === 0 && <div style={{ fontSize: 9, color: '#888', marginTop: 2 }}>{String(h).padStart(2, '0')}</div>}
              </div>
            ))}
          </div>
        </div>

        {/* Cost by appliance */}
        <div style={{ border: '1px solid #e2e8f0', borderRadius: 8, padding: 16, background: '#fff' }}>
          <h3 style={{ fontSize: 14, margin: '0 0 12px 0' }}>Cost by Appliance</h3>
          {costMeta.length === 0 ? (
            <div style={{ fontSize: 12, color: '#94a3b8' }}>No cost data yet.</div>
          ) : costMeta.slice(0, 6).map(d => (
            <div key={d.device} style={{ marginBottom: 8 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 2 }}>
                <span>{d.device}</span>
                <span style={{ color: '#666' }}>{d.cost_EGP} EGP</span>
              </div>
              <div style={{ background: '#f1f5f9', borderRadius: 4, height: 8, overflow: 'hidden' }}>
                <div style={{ width: `${d.share_pct}%`, height: '100%', background: d.color }} />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Recent alerts */}
      <div style={{ border: '1px solid #e2e8f0', borderRadius: 8, padding: 16, background: '#fff', marginBottom: 8 }}>
        <h3 style={{ fontSize: 14, margin: '0 0 12px 0' }}>Recent Alerts</h3>
        {recentAlerts.length === 0 ? (
          <div style={{ fontSize: 12, color: '#94a3b8' }}>No anomalies detected.</div>
        ) : recentAlerts.map((a, i) => (
          <div key={i} style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            padding: '8px 0', borderBottom: i < recentAlerts.length - 1 ? '1px solid #f0f0f0' : 'none',
          }}>
            <div>
              <span style={{
                fontSize: 10, padding: '2px 6px', borderRadius: 4,
                background: a.severity_color, color: '#fff', marginRight: 8,
              }}>
                {String(a.severity || '').toUpperCase()}
              </span>
              <strong>{a.device}</strong>
              {' — '}
              <span style={{ color: '#666' }}>{(a.label || '').replace(/_/g, ' ')}</span>
            </div>
            <span style={{ fontSize: 12, color: '#888' }}>{a.avg_power_W} W</span>
          </div>
        ))}
      </div>
    </>
  );
}
