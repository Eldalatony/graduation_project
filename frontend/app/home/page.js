'use client';

import { useEffect, useState, useMemo, useRef } from 'react';
import { useRouter } from 'next/navigation';
import Navbar from '../components/Navbar';
import styles from './page.module.css';
import { API_URL } from '../lib/api';

const SEV_LABEL = { critical: 'Critical', high: 'High', medium: 'Medium', low: 'Low' };
const MAX_POINTS = 40;

const ESP_GATEWAY_ID = process.env.NEXT_PUBLIC_ESP_GATEWAY_ID || 'esp32-01';

const DAY_NAMES = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
function parseCron(expr) {
  try {
    const parts = String(expr).trim().split(/\s+/);
    if (parts.length < 5) return expr;
    const [min, hour, , , daysRaw] = parts;
    const h = parseInt(hour, 10);
    const m = String(parseInt(min, 10)).padStart(2, '0');
    const ampm = h >= 12 ? 'PM' : 'AM';
    const h12 = String(h % 12 || 12);
    const timeStr = `${h12}:${m} ${ampm}`;
    if (daysRaw === '*') return `Every day · ${timeStr}`;
    const dayStr = daysRaw.split(',').map((d) => DAY_NAMES[Number(d)]).join(', ');
    return `${dayStr} · ${timeStr}`;
  } catch {
    return expr;
  }
}
function formatTimer(minutes) {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  const parts = [];
  if (h > 0) parts.push(`${h}h`);
  if (m > 0) parts.push(`${m}m`);
  return `Timer · ${parts.join(' ') || '0m'}`;
}

function Sparkline({ data, accent }) {
  if (!data || data.length < 2) {
    return <div style={{ fontSize: 11, color: '#64748b', paddingTop: 6 }}>Collecting…</div>;
  }
  const W = 240, H = 56, PAD = 4;
  const max = Math.max(...data), min = Math.min(...data);
  const range = max - min || 1;
  const n = data.length;
  const x = (i) => PAD + (i * (W - 2 * PAD)) / (n - 1);
  const y = (v) => PAD + (H - 2 * PAD) * (1 - (v - min) / range);
  const line = data.map((v, i) => `${i === 0 ? 'M' : 'L'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ');
  const area = `${line} L${x(n - 1).toFixed(1)},${H} L${x(0).toFixed(1)},${H} Z`;
  return (
    <svg className={styles.spark} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" aria-hidden="true">
      <path d={area} fill={accent} opacity="0.16" />
      <path d={line} fill="none" stroke={accent} strokeWidth="2" vectorEffect="non-scaling-stroke" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

function AreaChart({ values, color = '#818cf8' }) {
  const W = 640, H = 180, pad = 8;
  if (!values.length) return null;
  const max = Math.max(...values, 1), min = Math.min(...values, 0);
  const range = max - min || 1;
  const stepX = (W - 2 * pad) / Math.max(values.length - 1, 1);
  const pts = values.map((v, i) => [pad + i * stepX, H - pad - ((v - min) / range) * (H - 2 * pad)]);
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

function Donut({ segments, size = 150, thickness = 22 }) {
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
            <circle key={i} cx={size / 2} cy={size / 2} r={r} fill="none"
              stroke={s.color} strokeWidth={thickness}
              strokeDasharray={`${len} ${c - len}`} strokeDashoffset={-offset} strokeLinecap="butt" />
          );
          offset += len;
          return el;
        })}
      </g>
    </svg>
  );
}

const statusClass = {
  active:  { tile: styles.tileActive,  pill: styles.pillActive },
  idle:    { tile: styles.tileIdle,    pill: styles.pillIdle },
  offline: { tile: styles.tileOffline, pill: styles.pillOffline },
};
const accentColor = (s) => (s === 'active' ? '#34d399' : s === 'offline' ? '#f87171' : '#94a3b8');

export default function Home() {
  const router = useRouter();
  const [readings, setReadings]   = useState({});
  const [history, setHistory]     = useState({});
  const [error, setError]         = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [dash, setDash]           = useState(null);
  const [dashError, setDashError] = useState(null);
  const [appliances, setAppliances] = useState([]);
  const [schedules, setSchedules]   = useState([]);

  const [leftMin, setLeftMin]   = useState(false);
  const [rightMin, setRightMin] = useState(false);
  useEffect(() => {
    setLeftMin(localStorage.getItem('home_flank_left') === '1');
    setRightMin(localStorage.getItem('home_flank_right') === '1');
  }, []);
  const toggleLeft  = () => setLeftMin((v) => { localStorage.setItem('home_flank_left',  v ? '0' : '1'); return !v; });
  const toggleRight = () => setRightMin((v) => { localStorage.setItem('home_flank_right', v ? '0' : '1'); return !v; });

  const tokenRef = useRef(null);
  const headers = () => ({ 'Content-Type': 'application/json', Authorization: `Bearer ${tokenRef.current}` });

  useEffect(() => {
    const token = localStorage.getItem('token');
    if (!token) { router.replace('/auth'); return; }
    tokenRef.current = token;
    let cancelled = false;

    const fetchLive = async () => {
      tokenRef.current = localStorage.getItem('token');
      try {
        const res = await fetch(`${API_URL}/api/live`, { headers: headers() });
        if (res.status === 401) { localStorage.removeItem('token'); router.replace('/auth'); return; }
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (cancelled) return;
        setReadings(data);
        setHistory((prev) => {
          const next = { ...prev };
          for (const [key, v] of Object.entries(data || {})) {
            next[key] = (next[key] || []).concat(Number(v.power_W ?? 0)).slice(-MAX_POINTS);
          }
          return next;
        });
        setError(null);
        setLastUpdated(new Date());
      } catch (err) {
        if (!cancelled) setError(err.message);
      }
    };

    fetchLive();
    const iv = setInterval(fetchLive, 1000);
    return () => { cancelled = true; clearInterval(iv); };
  }, [router]);

  useEffect(() => {
    let cancelled = false;
    const fetchDash = async () => {
      if (!localStorage.getItem('token')) return;
      try {
        const res = await fetch(`${API_URL}/api/ui/dashboard`, { headers: headers() });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json = await res.json();
        if (cancelled) return;
        setDash(json.data || json);
        setDashError(null);
      } catch (err) {
        if (!cancelled) setDashError(err.message);
      }
    };
    fetchDash();
    const iv = setInterval(fetchDash, 30000);
    return () => { cancelled = true; clearInterval(iv); };
  }, []);

  const fetchAppliances = async () => {
    try {
      const res = await fetch(`${API_URL}/api/appliances`, { headers: headers() });
      if (!res.ok) return;
      const data = await res.json();
      setAppliances(data.appliances || []);
    } catch {}
  };
  const fetchSchedules = async () => {
    try {
      const res = await fetch(`${API_URL}/api/schedules`, { headers: headers() });
      if (!res.ok) return;
      const data = await res.json();
      setSchedules(data.schedules || []);
    } catch {}
  };
  useEffect(() => {
    if (!localStorage.getItem('token')) return;
    fetchAppliances();
    fetchSchedules();
  }, []);

  const handleControl = async (a, command) => {
    setAppliances((prev) => prev.map((x) => (x.id === a.id ? { ...x, is_active: command === 'on' } : x)));
    try {
      const res = await fetch(`${API_URL}/api/appliances/${a.id}/control`, {
        method: 'POST', headers: headers(), body: JSON.stringify({ command }),
      });
      if (!res.ok) throw new Error();
      fetchAppliances();
    } catch {
      fetchAppliances();
    }
  };

  const liveEntries = useMemo(() => {
    return Object.entries(readings)
      .map(([key, r]) => ({ key, ...r }))
      .filter((r) => r.gateway_id === ESP_GATEWAY_ID)
      .sort((a, b) => Number(b.power_W ?? 0) - Number(a.power_W ?? 0));
  }, [readings]);

  const onCount  = appliances.filter((a) => a.is_active).length;
  const offCount = appliances.length - onCount;
  const upcomingSchedules = useMemo(
    () => schedules.filter((s) => s.is_enabled).slice(0, 5),
    [schedules]
  );

  return (
    <div className={styles.page}>
      <Navbar activePage="home" variant="dark" />

      <div className={styles.content}>
        <header className={styles.header}>
          <div className={styles.headerLeft}>
            <h1 className={styles.title}>Live Energy Dashboard</h1>
          </div>
          <div className={`${styles.status} ${error ? styles.statusBad : styles.statusOk}`}>
            <span className={styles.statusDot} />
            {error
              ? `Disconnected (${error})`
              : `Live${lastUpdated ? ` · ${lastUpdated.toLocaleTimeString()}` : ''}`}
          </div>
        </header>

        <div className={styles.sectionHead}>
          <h2 className={styles.sectionTitle}>⚡ Live Monitor</h2>
          <span className={styles.sectionRule} />
          <button className={styles.linkBtn} onClick={() => router.push('/appliances')}>Manage devices →</button>
        </div>

        <div
          className={styles.spotlight}
          style={{ gridTemplateColumns: `${leftMin ? '48px' : 'minmax(230px, 300px)'} minmax(0, 1fr) ${rightMin ? '48px' : 'minmax(230px, 300px)'}` }}
        >
          {leftMin ? (
            <div className={styles.flankStrip} onClick={toggleLeft} title="Expand appliances">
              <span className={styles.flankStripIcon}>▸</span>
              <span className={styles.flankStripLabel}>Appliances</span>
            </div>
          ) : (
            <div className={styles.flankExpanded}>
              <div className={styles.flankHead}>
                <h3 className={styles.flankTitle}>Appliances</h3>
                <button className={styles.minBtn} onClick={toggleLeft} title="Minimize">−</button>
              </div>
              {appliances.length === 0 ? (
                <div className={styles.emptyMini}>No appliances yet</div>
              ) : (
                <>
                  <div className={styles.miniStat}>
                    <div className={styles.miniStatItem}>
                      <span className={`${styles.miniStatNum} ${styles.miniOn}`}>{onCount}</span>
                      <span className={styles.miniStatLabel}>On</span>
                    </div>
                    <div className={styles.miniStatItem}>
                      <span className={`${styles.miniStatNum} ${styles.miniOff}`}>{offCount}</span>
                      <span className={styles.miniStatLabel}>Off</span>
                    </div>
                  </div>
                  <div className={styles.ctrlList}>
                    {appliances.map((a) => {
                      const live = readings[`${a.gateway_id}/${a.node_key}`];
                      return (
                        <div key={a.id} className={styles.ctrlRow}>
                          <div className={styles.ctrlInfo}>
                            <div className={styles.ctrlName}>{a.name}</div>
                            <div className={styles.ctrlMeta}>
                              {live ? `${Number(live.power_W ?? 0).toFixed(0)} W` : (a.room || '—')}
                            </div>
                          </div>
                          <label className={styles.toggle} title={a.is_active ? 'Turn off' : 'Turn on'}>
                            <input
                              type="checkbox"
                              checked={!!a.is_active}
                              onChange={() => handleControl(a, a.is_active ? 'off' : 'on')}
                            />
                            <span className={styles.toggleSlider} />
                          </label>
                        </div>
                      );
                    })}
                  </div>
                </>
              )}
            </div>
          )}

          <div className={styles.spotCenter}>
            {liveEntries.length === 0 ? (
              <div className={styles.heroEmpty}>
                Waiting for the ESP device… make sure it&apos;s registered as an appliance on gateway <code>{ESP_GATEWAY_ID}</code> and publishing to <code>home/gateway/data</code>.
              </div>
            ) : (() => {
              const r = liveEntries[0];
              const status = r.status || 'idle';
              const sc = statusClass[status] || statusClass.idle;
              const glow = status === 'active' ? 'rgba(34,197,94,0.3)' : status === 'offline' ? 'rgba(239,68,68,0.28)' : 'rgba(148,163,184,0.2)';
              const rateEGP = (Number(r.cost_EGP ?? 0) * 3600).toFixed(2);
              return (
                <>
                  <div className={styles.spotMain} style={{ '--glow': glow }}>
                    <span className={`${styles.pill} ${sc.pill}`} style={{ position: 'absolute', top: 18, right: 18 }}>{status}</span>
                    <div className={styles.spotName}>{r.appliance_name || r.node_key}</div>
                    <div className={styles.spotMeta}>{r.gateway_id || '—'} / {r.node_key}</div>
                    <div className={styles.spotPower}>
                      <span className={styles.spotWatts}>{Number(r.power_W ?? 0).toFixed(0)}</span>
                      <span className={styles.spotUnit}>W</span>
                    </div>
                    <div className={styles.spotStats}>
                      <div className={styles.spotStat}>
                        <span className={styles.spotStatLabel}>Current</span>
                        <span className={styles.spotStatValue}>{Number(r.current_A ?? 0).toFixed(2)} A</span>
                      </div>
                      <div className={styles.spotStat}>
                        <span className={styles.spotStatLabel}>Voltage</span>
                        <span className={styles.spotStatValue}>{Number(r.voltage_V ?? 0).toFixed(0)} V</span>
                      </div>
                      <div className={styles.spotStat}>
                        <span className={styles.spotStatLabel}>Rate</span>
                        <span className={styles.spotStatValue}>{rateEGP} EGP/hr</span>
                      </div>
                      <div className={styles.spotStat}>
                        <span className={styles.spotStatLabel}>Energy</span>
                        <span className={styles.spotStatValue}>{Number(r.energy_kWh ?? 0).toFixed(3)} kWh</span>
                      </div>
                    </div>
                    <div className={styles.spotSpark}>
                      <Sparkline data={history[r.key]} accent={accentColor(status)} />
                    </div>
                  </div>

                  {liveEntries.length > 1 && (
                    <div className={styles.spotExtras}>
                      {liveEntries.slice(1).map((d) => {
                        const st = d.status || 'idle';
                        const dsc = statusClass[st] || statusClass.idle;
                        return (
                          <div key={d.key} className={`${styles.tile} ${dsc.tile}`}>
                            <div className={styles.tileTop}>
                              <div>
                                <div className={styles.tileName}>{d.appliance_name || d.node_key}</div>
                                <div className={styles.tileMeta}>{d.gateway_id || '—'} / {d.node_key}</div>
                              </div>
                              <span className={`${styles.pill} ${dsc.pill}`}>{st}</span>
                            </div>
                            <div className={styles.tilePower}>
                              <span className={styles.tileWatts}>{Number(d.power_W ?? 0).toFixed(0)}</span>
                              <span className={styles.tileUnit}>W</span>
                            </div>
                            <div className={styles.tileSpark}>
                              <Sparkline data={history[d.key]} accent={accentColor(st)} />
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </>
              );
            })()}
          </div>

          {rightMin ? (
            <div className={styles.flankStrip} onClick={toggleRight} title="Expand alerts">
              <span className={styles.flankStripIcon}>◂</span>
              <span className={styles.flankStripLabel}>Alerts</span>
            </div>
          ) : (
            <div className={styles.flankExpanded}>
              <div className={styles.flankHead}>
                <h3 className={styles.flankTitle}>Alerts</h3>
                <button className={styles.minBtn} onClick={toggleRight} title="Minimize">−</button>
              </div>
              {dash?.anomaly_summary?.by_severity?.length > 0 && (
                <div className={styles.sevRow}>
                  {dash.anomaly_summary.by_severity.map((s) => (
                    <span key={s.severity} className={styles.sevPill} style={{ background: `${s.color}22`, color: s.color }}>
                      <strong>{s.count}</strong> {SEV_LABEL[s.severity] || s.severity}
                    </span>
                  ))}
                </div>
              )}
              {dash?.recent_alerts?.length ? (
                <div className={styles.alertList}>
                  {dash.recent_alerts.slice(0, 5).map((a, i) => (
                    <div key={i} className={styles.alertRow}>
                      <span className={styles.alertDot} style={{ background: a.severity_color }} />
                      <div className={styles.alertMain}>
                        <div className={styles.alertDevice}>{a.device}</div>
                        <div className={styles.alertMeta}>{(a.label || 'anomaly').replace(/_/g, ' ')}</div>
                      </div>
                      <span className={styles.alertPower}>{Number(a.avg_power_W ?? 0).toFixed(0)} W</span>
                    </div>
                  ))}
                </div>
              ) : (
                <div className={styles.emptyMini}>No anomalies detected</div>
              )}
            </div>
          )}
        </div>

        {dash?.models_ready != null && (
          <div className={styles.readiness}>
            <span className={styles.readyDot}>●</span>
            {dash.models_ready} model{dash.models_ready === 1 ? '' : 's'} ready
            {dash.models_learning > 0 && (
              <span className={styles.learnAccent}> · {dash.models_learning} still learning</span>
            )}
          </div>
        )}

        {dashError ? (
          <div className={styles.banner}>Could not load summary ({dashError}). Live readings above are unaffected.</div>
        ) : dash?.kpi_cards?.length > 0 && (
          <>
            <div className={styles.sectionHead}>
              <h2 className={styles.sectionTitle}>Today at a glance</h2>
              <span className={styles.sectionRule} />
            </div>
            <div className={styles.kpiRow}>
              {dash.kpi_cards.map((k) => (
                <div key={k.id || k.label} className={styles.kpi}>
                  <span className={styles.kpiBar} style={{ background: k.color || '#6366f1' }} />
                  <div className={styles.kpiLabel}>{k.label}</div>
                  <div className={styles.kpiValue}>
                    {typeof k.value === 'number' ? k.value.toLocaleString() : k.value}{' '}
                    <span className={styles.kpiUnit}>{k.unit}</span>
                  </div>
                  {k.sub_label && <div className={styles.kpiSub}>{k.sub_label}</div>}
                </div>
              ))}
            </div>
          </>
        )}

        <div className={styles.sectionHead}>
          <h2 className={styles.sectionTitle}>Insights & Controls</h2>
          <span className={styles.sectionRule} />
        </div>

        <div className={styles.bento}>
          <div className={`${styles.panel} ${styles.span4}`}>
            <div className={styles.panelHead}>
              <h3 className={styles.panelTitle}>Energy Trend</h3>
              <button className={styles.linkBtn} onClick={() => router.push('/analytics')}>Analytics →</button>
            </div>
            {(() => {
              const vals = dash?.energy_trend?.datasets?.[0]?.data || [];
              const labels = dash?.energy_trend?.labels || [];
              if (!vals.length) return <div className={styles.emptyMini}>No data yet</div>;
              const ticks = labels.filter((_, i) => i % Math.ceil(labels.length / 6) === 0);
              return (
                <>
                  <AreaChart values={vals} color="#818cf8" />
                  <div className={styles.axisRow}>{ticks.map((t) => <span key={t}>{t.slice(5)}</span>)}</div>
                </>
              );
            })()}
          </div>

          <div className={`${styles.panel} ${styles.span2}`}>
            <div className={styles.panelHead}>
              <h3 className={styles.panelTitle}>Cost by Device</h3>
            </div>
            {(() => {
              const meta = dash?.cost_donut?.meta || [];
              if (!meta.length) return <div className={styles.emptyMini}>No cost data yet</div>;
              const segments = meta.map((m) => ({ value: m.cost_EGP, color: m.color }));
              const total = meta.reduce((a, m) => a + m.cost_EGP, 0);
              return (
                <div className={styles.donutWrap}>
                  <div className={styles.donutChart}>
                    <Donut segments={segments} />
                    <div className={styles.donutCenter}>
                      <div className={styles.donutTotal}>{total.toFixed(0)}</div>
                      <div className={styles.donutUnit}>EGP total</div>
                    </div>
                  </div>
                  <div className={styles.legend}>
                    {meta.slice(0, 6).map((m) => (
                      <div key={m.device} className={styles.legendRow}>
                        <span className={styles.legendDot} style={{ background: m.color }} />
                        <span className={styles.legendName}>{m.device}</span>
                        <span className={styles.legendPct}>{m.share_pct}%</span>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })()}
          </div>

          <div className={`${styles.panel} ${styles.span4}`}>
            <div className={styles.panelHead}>
              <h3 className={styles.panelTitle}>Peak Hours</h3>
              {dash?.peak_hours?.peak_hour_label && (
                <span className={styles.panelHint}>Busiest at {dash.peak_hours.peak_hour_label}</span>
              )}
            </div>
            {(() => {
              const vals = dash?.peak_hours?.datasets?.[0]?.data || [];
              const colors = dash?.peak_hours?.datasets?.[0]?.backgroundColor || [];
              if (!vals.length) return <div className={styles.emptyMini}>No data yet</div>;
              const max = Math.max(...vals, 0.0001);
              return (
                <>
                  <div className={styles.bars}>
                    {vals.map((v, h) => (
                      <div key={h} className={styles.barTrack} title={`${String(h).padStart(2, '0')}:00 — ${v} kWh`}>
                        <div className={styles.bar} style={{ height: `${(v / max) * 100}%`, background: colors[h] || '#a5b4fc' }} />
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

          <div className={`${styles.panel} ${styles.span2}`}>
            <div className={styles.panelHead}>
              <h3 className={styles.panelTitle}>Schedules</h3>
              <button className={styles.linkBtn} onClick={() => router.push('/schedules')}>Manage →</button>
            </div>
            {upcomingSchedules.length === 0 ? (
              <div className={styles.emptyMini}>No active schedules</div>
            ) : (
              <div className={styles.schedList}>
                {upcomingSchedules.map((s) => (
                  <div key={s.id} className={styles.schedRow}>
                    <div className={styles.schedInfo}>
                      <div className={styles.schedDevice}>{s.appliance_name}</div>
                      <div className={styles.schedWhen}>
                        {s.timer_minutes != null ? formatTimer(s.timer_minutes) : parseCron(s.cron_expression)}
                      </div>
                    </div>
                    <span className={`${styles.schedAction} ${s.action === 'on' ? styles.schedOn : styles.schedOff}`}>
                      {s.action === 'on' ? 'On' : 'Off'}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>

        </div>
      </div>
    </div>
  );
}
