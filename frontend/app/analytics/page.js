'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Navbar from '../components/Navbar';
import styles from './page.module.css';
import { API_URL } from '../lib/api';

const SEV_LABEL = { critical: 'Critical', high: 'High', medium: 'Medium', low: 'Low' };

function Donut({ segments, size = 168, thickness = 24 }) {
  const r = (size - thickness) / 2;
  const c = 2 * Math.PI * r;
  const total = segments.reduce((a, s) => a + s.value, 0) || 1;
  let offset = 0;
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      <g transform={`rotate(-90 ${size / 2} ${size / 2})`}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth={thickness} />
        {segments.map((s, i) => {
          const len = (s.value / total) * c;
          const el = (
            <circle
              key={i} cx={size / 2} cy={size / 2} r={r} fill="none"
              stroke={s.color} strokeWidth={thickness}
              strokeDasharray={`${len} ${c - len}`} strokeDashoffset={-offset}
              strokeLinecap="butt"
            />
          );
          offset += len;
          return el;
        })}
      </g>
    </svg>
  );
}

function AreaChart({ values, height = 200, color = '#818cf8' }) {
  const W = 640, H = height, pad = 10;
  if (!values.length) return null;
  const max = Math.max(...values, 1);
  const min = Math.min(...values, 0);
  const range = max - min || 1;
  const stepX = (W - 2 * pad) / Math.max(values.length - 1, 1);
  const pts = values.map((v, i) => [
    pad + i * stepX,
    H - pad - ((v - min) / range) * (H - 2 * pad),
  ]);
  const line = pts.map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' ');
  const area = `${line} L${pts[pts.length - 1][0].toFixed(1)},${H - pad} L${pts[0][0].toFixed(1)},${H - pad} Z`;
  const gid = `areaFill-${color.replace('#', '')}`;
  return (
    <svg className={styles.areaSvg} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.35" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#${gid})`} />
      <path d={line} fill="none" stroke={color} strokeWidth="2.5" strokeLinejoin="round" />
    </svg>
  );
}

function aggregateForecast(d) {
  const devices = d.per_device || (d.points ? [d] : []);
  const byTime = new Map();
  const methods = new Set();
  devices.forEach((dev) => {
    methods.add(dev.method);
    (dev.points || []).forEach((p) => {
      byTime.set(p.interval_start, (byTime.get(p.interval_start) || 0) + p.predicted_kWh);
    });
  });
  const dayMap = new Map();
  [...byTime.keys()].sort().forEach((t) => {
    const day = t.slice(0, 10);
    dayMap.set(day, (dayMap.get(day) || 0) + byTime.get(t));
  });
  const days = [...dayMap.keys()];
  return {
    days,
    dailyKwh:  days.map((day) => dayMap.get(day)),
    totalKwh:  d.total_predicted_kWh ?? 0,
    totalCost: d.total_predicted_cost_EGP ?? 0,
    methods:   [...methods],
  };
}

export default function AnalyticsPage() {
  const router = useRouter();
  const [data, setData]       = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(null);
  const [forecast, setForecast]       = useState(null);
  const [horizonDays, setHorizonDays] = useState(7);

  const token   = () => localStorage.getItem('token');
  const headers = () => ({ 'Content-Type': 'application/json', Authorization: `Bearer ${token()}` });

  const fetchData = async () => {
    try {
      const res = await fetch(`${API_URL}/api/ui/dashboard`, { headers: headers() });
      if (res.status === 401) { localStorage.removeItem('token'); router.replace('/auth'); return; }
      const json = await res.json();
      if (!res.ok) throw new Error(json.message || `HTTP ${res.status}`);
      setData(json.data);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const fetchForecast = async (days) => {
    setForecast(null);
    try {
      const res = await fetch(`${API_URL}/api/analytics/all/forecast?hours=${days * 24}`, { headers: headers() });
      const json = await res.json();
      if (!res.ok) throw new Error(json.message || `HTTP ${res.status}`);
      setForecast(aggregateForecast(json.data));
    } catch (err) {
      setForecast({ error: err.message });
    }
  };

  useEffect(() => {
    if (!token()) { router.replace('/auth'); return; }
    fetchData();
    fetchForecast(horizonDays);
  }, []);

  const fmt = (n) => Number(n).toLocaleString(undefined, { maximumFractionDigits: 2 });

  return (
    <div className={styles.page}>
      <Navbar activePage="analytics" variant="dark" />

      <div className={styles.content}>
        <div className={styles.pageHeader}>
          <div>
            <h1 className={styles.pageTitle}>Analytics</h1>
            <p className={styles.pageSubtitle}>Energy, cost, and anomaly insights across your home</p>
          </div>
          {!loading && (
            <button className={styles.refreshBtn} onClick={() => { setLoading(true); fetchData(); fetchForecast(horizonDays); }}>
              ↻ Refresh
            </button>
          )}
        </div>

        {error && <div className={styles.error}>⚠ {error}</div>}

        {loading ? (
          <div className={styles.loading}><div className={styles.spinner} /><div>Loading analytics…</div></div>
        ) : !data ? null : (
          <>
            {data.device_status?.length > 0 && (
              <div className={styles.readinessBar}>
                <span className={styles.readinessLabel}>Anomaly models</span>
                {data.device_status.map((d) => (
                  <span
                    key={d.device_name}
                    className={`${styles.deviceChip} ${d.status === 'ready' ? styles.chipReady : styles.chipLearning}`}
                    title={d.status === 'ready' ? 'Trained & monitoring' : `Learning — ${d.progress_pct}% ready`}
                  >
                    <span className={styles.chipDot} />
                    {d.device_name}
                    {d.status === 'ready' ? ' · ready' : ` · learning ${d.progress_pct}%`}
                  </span>
                ))}
              </div>
            )}

            <div className={styles.kpiGrid}>
              {data.kpi_cards?.map((k) => (
                <div key={k.id} className={styles.kpiCard}>
                  <div className={styles.kpiBody}>
                    <div className={styles.kpiValue}>
                      {fmt(k.value)} <span className={styles.kpiUnit}>{k.unit}</span>
                    </div>
                    <div className={styles.kpiLabel}>{k.label}</div>
                    {k.sub_label && <div className={styles.kpiSub}>{k.sub_label}</div>}
                  </div>
                </div>
              ))}
            </div>

            <div className={styles.card}>
              <div className={styles.cardHead}>
                <h2 className={styles.cardTitle}>Energy Trend</h2>
                <span className={styles.cardHint}>Daily consumption (kWh)</span>
              </div>
              {(() => {
                const vals = data.energy_trend?.datasets?.[0]?.data || [];
                const labels = data.energy_trend?.labels || [];
                if (!vals.length) return <div className={styles.emptyMini}>No data yet</div>;
                const ticks = labels.filter((_, i) => i % Math.ceil(labels.length / 6) === 0);
                return (
                  <>
                    <AreaChart values={vals} />
                    <div className={styles.axisRow}>
                      {ticks.map((t) => <span key={t}>{t.slice(5)}</span>)}
                    </div>
                  </>
                );
              })()}
            </div>

            <div className={styles.card}>
              <div className={styles.cardHead}>
                <h2 className={styles.cardTitle}>Energy Forecast</h2>
                <div className={styles.forecastToggle}>
                  {[7, 30].map((d) => (
                    <button
                      key={d}
                      className={`${styles.toggleBtn} ${horizonDays === d ? styles.toggleActive : ''}`}
                      onClick={() => { setHorizonDays(d); fetchForecast(d); }}
                    >
                      {d}d
                    </button>
                  ))}
                </div>
              </div>
              {!forecast ? (
                <div className={styles.emptyMini}>Forecasting…</div>
              ) : forecast.error ? (
                <div className={styles.emptyMini}>Forecast unavailable — models still learning</div>
              ) : !forecast.dailyKwh.length ? (
                <div className={styles.emptyMini}>No forecast yet</div>
              ) : (
                <>
                  <div className={styles.forecastStats}>
                    <div className={styles.forecastStat}>
                      <div className={styles.forecastStatValue}>
                        {fmt(forecast.totalCost)} <span className={styles.kpiUnit}>EGP</span>
                      </div>
                      <div className={styles.forecastStatLabel}>Projected cost · next {horizonDays} days</div>
                    </div>
                    <div className={styles.forecastStat}>
                      <div className={styles.forecastStatValue}>
                        {fmt(forecast.totalKwh)} <span className={styles.kpiUnit}>kWh</span>
                      </div>
                      <div className={styles.forecastStatLabel}>Projected energy</div>
                    </div>
                    <div className={styles.forecastStat}>
                      <span className={styles.methodTag}>
                        {forecast.methods.includes('ridge') ? 'Linear regression' : 'Profile baseline'}
                      </span>
                    </div>
                  </div>
                  <AreaChart values={forecast.dailyKwh} color="#10b981" />
                  <div className={styles.axisRow}>
                    {forecast.days
                      .filter((_, i) => i % Math.ceil(forecast.days.length / 6) === 0)
                      .map((d) => <span key={d}>{d.slice(5)}</span>)}
                  </div>
                </>
              )}
            </div>

            <div className={styles.twoCol}>
              <div className={styles.card}>
                <div className={styles.cardHead}>
                  <h2 className={styles.cardTitle}>Cost by Device</h2>
                </div>
                {(() => {
                  const meta = data.cost_donut?.meta || [];
                  if (!meta.length) return <div className={styles.emptyMini}>No data yet</div>;
                  const segments = meta.map((m) => ({ value: m.cost_EGP, color: m.color }));
                  const total = meta.reduce((a, m) => a + m.cost_EGP, 0);
                  return (
                    <div className={styles.donutWrap}>
                      <div className={styles.donutChart}>
                        <Donut segments={segments} />
                        <div className={styles.donutCenter}>
                          <div className={styles.donutTotal}>{fmt(total)}</div>
                          <div className={styles.donutTotalUnit}>EGP total</div>
                        </div>
                      </div>
                      <div className={styles.legend}>
                        {meta.map((m) => (
                          <div key={m.device} className={styles.legendRow}>
                            <span className={styles.legendDot} style={{ background: m.color }} />
                            <span className={styles.legendName}>{m.device}</span>
                            <span className={styles.legendVal}>{fmt(m.cost_EGP)} EGP</span>
                            <span className={styles.legendPct}>{m.share_pct}%</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  );
                })()}
              </div>

              <div className={styles.card}>
                <div className={styles.cardHead}>
                  <h2 className={styles.cardTitle}>Peak Hours</h2>
                  {data.peak_hours?.peak_hour_label && (
                    <span className={styles.cardHint}>Busiest at {data.peak_hours.peak_hour_label}</span>
                  )}
                </div>
                {(() => {
                  const vals = data.peak_hours?.datasets?.[0]?.data || [];
                  const colors = data.peak_hours?.datasets?.[0]?.backgroundColor || [];
                  if (!vals.length) return <div className={styles.emptyMini}>No data yet</div>;
                  const max = Math.max(...vals, 0.0001);
                  return (
                    <>
                      <div className={styles.bars}>
                        {vals.map((v, h) => (
                          <div
                            key={h} className={styles.barTrack}
                            title={`${String(h).padStart(2, '0')}:00 — ${fmt(v)} kWh`}
                          >
                            <div
                              className={styles.bar}
                              style={{ height: `${(v / max) * 100}%`, background: colors[h] || '#a5b4fc' }}
                            />
                          </div>
                        ))}
                      </div>
                      <div className={styles.axisRow}>
                        {[0, 6, 12, 18, 23].map((h) => <span key={h}>{String(h).padStart(2, '0')}:00</span>)}
                      </div>
                    </>
                  );
                })()}
              </div>
            </div>

            <div className={styles.card}>
              <div className={styles.cardHead}>
                <h2 className={styles.cardTitle}>Anomalies</h2>
                <span className={styles.cardHint}>
                  {data.anomaly_summary?.total || 0} detected · {data.anomaly_summary?.rate_pct ?? 0}% rate
                </span>
              </div>

              <div className={styles.sevRow}>
                {data.anomaly_summary?.by_severity?.map((s) => (
                  <div key={s.severity} className={styles.sevPill} style={{ background: `${s.color}14`, color: s.color }}>
                    <strong>{s.count}</strong> {SEV_LABEL[s.severity]}
                  </div>
                ))}
              </div>

              {data.recent_alerts?.length ? (
                <div className={styles.alertList}>
                  {data.recent_alerts.map((a, i) => (
                    <div key={i} className={styles.alertRow}>
                      <span className={styles.alertDot} style={{ background: a.severity_color }} />
                      <div className={styles.alertMain}>
                        <div className={styles.alertDevice}>{a.device}</div>
                        <div className={styles.alertMeta}>
                          {a.label?.replace?.(/_/g, ' ') || 'anomaly'} · {fmt(a.avg_power_W)} W
                        </div>
                      </div>
                      <span className={styles.alertBadge} style={{ background: `${a.severity_color}18`, color: a.severity_color }}>
                        {SEV_LABEL[a.severity]}
                      </span>
                      <span className={styles.alertTime}>{a.time?.slice(5, 16).replace('T', ' ')}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <div className={styles.emptyMini}>No anomalies detected</div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
