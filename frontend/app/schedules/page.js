'use client';

import { useEffect, useState, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import Navbar from '../components/Navbar';
import styles from './page.module.css';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:3001';

const DAYS = [
  { label: 'Mon', value: 1 },
  { label: 'Tue', value: 2 },
  { label: 'Wed', value: 3 },
  { label: 'Thu', value: 4 },
  { label: 'Fri', value: 5 },
  { label: 'Sat', value: 6 },
  { label: 'Sun', value: 0 },
];

const ALL_DAYS = DAYS.map(d => d.value);

const buildCron = (time, days) => {
  const [h, m] = time.split(':');
  const sorted = [...days].sort((a, b) => a - b);
  const daysStr = sorted.length === 7 ? '*' : sorted.join(',');
  return `${parseInt(m, 10)} ${parseInt(h, 10)} * * ${daysStr}`;
};

const parseCron = (expr) => {
  try {
    const parts = expr.trim().split(/\s+/);
    if (parts.length < 5) return expr;
    const [min, hour, , , daysRaw] = parts;
    const h = parseInt(hour, 10);
    const m = String(parseInt(min, 10)).padStart(2, '0');
    const ampm = h >= 12 ? 'PM' : 'AM';
    const h12 = String(h % 12 || 12);
    const timeStr = `${h12}:${m} ${ampm}`;
    if (daysRaw === '*') return `Every day at ${timeStr}`;
    const dayNames = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    const dayStr = daysRaw.split(',').map(d => dayNames[Number(d)]).join(', ');
    return `${dayStr} at ${timeStr}`;
  } catch {
    return expr;
  }
};

const formatTimer = (minutes) => {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  const parts = [];
  if (h > 0) parts.push(`${h}h`);
  if (m > 0) parts.push(`${m}m`);
  return `One-time • ${parts.join(' ') || '0m'}`;
};

const EMPTY_FORM = {
  appliance_id: '',
  action: 'off',
  scheduleType: 'fixed',
  time: '22:00',
  days: ALL_DAYS,
  timerH: 1,
  timerM: 0,
};

export default function SchedulesPage() {
  const router = useRouter();

  const [schedules, setSchedules]   = useState([]);
  const [appliances, setAppliances] = useState([]);
  const [loading, setLoading]       = useState(true);
  const [error, setError]           = useState(null);
  const [modalOpen, setModalOpen]   = useState(false);
  const [form, setForm]             = useState(EMPTY_FORM);
  const [saving, setSaving]         = useState(false);

  const token   = () => localStorage.getItem('token');
  const headers = () => ({ 'Content-Type': 'application/json', Authorization: `Bearer ${token()}` });

  const handleAuth = (status) => {
    if (status === 401) { localStorage.removeItem('token'); router.replace('/auth'); return true; }
    return false;
  };

  const fetchAll = async () => {
    try {
      const [sRes, aRes] = await Promise.all([
        fetch(`${API_URL}/api/schedules`,  { headers: headers() }),
        fetch(`${API_URL}/api/appliances`, { headers: headers() }),
      ]);
      if (handleAuth(sRes.status) || handleAuth(aRes.status)) return;
      const [sData, aData] = await Promise.all([sRes.json(), aRes.json()]);
      setSchedules(sData.schedules || []);
      setAppliances(aData.appliances || []);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!token()) { router.replace('/auth'); return; }
    fetchAll();
  }, []);

  const openModal = () => {
    setForm({ ...EMPTY_FORM, appliance_id: appliances[0]?.id || '' });
    setModalOpen(true);
  };

  const closeModal = () => { setModalOpen(false); setForm(EMPTY_FORM); setError(null); };

  const toggleDay = (val) => {
    setForm(f => {
      const has = f.days.includes(val);
      const days = has ? f.days.filter(d => d !== val) : [...f.days, val];
      return { ...f, days: days.length ? days : [val] };
    });
  };

  const toggleAllDays = () => {
    setForm(f => ({ ...f, days: f.days.length === 7 ? [1] : ALL_DAYS }));
  };

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!form.appliance_id) { setError('Select a device'); return; }
    setSaving(true);
    setError(null);
    try {
      let body;
      if (form.scheduleType === 'timer') {
        const totalMinutes = form.timerH * 60 + form.timerM;
        if (totalMinutes < 1) { setError('Timer must be at least 1 minute'); setSaving(false); return; }
        body = { appliance_id: form.appliance_id, action: form.action, timer_minutes: totalMinutes, is_enabled: true };
      } else {
        if (!form.days.length) { setError('Select at least one day'); setSaving(false); return; }
        body = {
          appliance_id:    form.appliance_id,
          action:          form.action,
          cron_expression: buildCron(form.time, form.days),
          is_enabled:      true,
        };
      }
      const res = await fetch(`${API_URL}/api/schedules`, { method: 'POST', headers: headers(), body: JSON.stringify(body) });
      if (handleAuth(res.status)) return;
      const data = await res.json();
      if (!res.ok) throw new Error(data.message || `HTTP ${res.status}`);
      closeModal();
      fetchAll();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const toggleEnabled = async (s) => {
    try {
      const res = await fetch(`${API_URL}/api/schedules/${s.id}`, {
        method: 'PUT', headers: headers(),
        body: JSON.stringify({ is_enabled: !s.is_enabled }),
      });
      if (!res.ok) return;
      setSchedules(prev => prev.map(x => x.id === s.id ? { ...x, is_enabled: !x.is_enabled } : x));
    } catch { /* silent */ }
  };

  const handleDelete = async (s) => {
    if (!confirm('Delete this schedule?')) return;
    try {
      const res = await fetch(`${API_URL}/api/schedules/${s.id}`, { method: 'DELETE', headers: headers() });
      if (handleAuth(res.status)) return;
      if (!res.ok) return;
      setSchedules(prev => prev.filter(x => x.id !== s.id));
    } catch { /* silent */ }
  };

  return (
    <div className={styles.page}>
      <Navbar activePage="schedules" />

      <div className={styles.content}>
        <div className={styles.pageHeader}>
          <div>
            <h1 className={styles.pageTitle}>Power Schedules</h1>
            <p className={styles.pageSubtitle}>Automate when your devices get power</p>
          </div>
          <button className={styles.addBtn} onClick={openModal}>+ Add Schedule</button>
        </div>

        {error && !modalOpen && <div className={styles.error}>⚠ {error}</div>}

        {loading ? (
          <div className={styles.loading}>
            <div className={styles.spinner} />
            <div>Loading schedules…</div>
          </div>
        ) : schedules.length === 0 ? (
          <div className={styles.empty}>
            <p className={styles.emptyTitle}>No schedules yet</p>
            <p className={styles.emptyText}>Create a schedule to automate when your devices get power.</p>
          </div>
        ) : (
          <div className={styles.list}>
            {schedules.map(s => (
              <div key={s.id} className={`${styles.card} ${!s.is_enabled ? styles.cardDisabled : ''}`}>
                <div className={styles.cardInfo}>
                  <div className={styles.cardDevice}>{s.appliance_name}</div>
                  <div className={styles.cardSchedule}>
                    {s.timer_minutes != null ? formatTimer(s.timer_minutes) : parseCron(s.cron_expression)}
                    <span className={`${styles.cardAction} ${s.action === 'on' ? styles.actionOn : styles.actionOff}`}>
                      Power {s.action === 'on' ? 'On' : 'Off'}
                    </span>
                  </div>
                </div>

                <div className={styles.cardControls}>
                  <label className={styles.toggle} title={s.is_enabled ? 'Disable' : 'Enable'}>
                    <input type="checkbox" checked={s.is_enabled} onChange={() => toggleEnabled(s)} />
                    <span className={styles.toggleSlider} />
                  </label>
                  <button className={styles.deleteBtn} onClick={() => handleDelete(s)} title="Delete">✕</button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── Add Schedule Modal ── */}
      {modalOpen && (
        <div className={styles.overlay} onClick={e => e.target === e.currentTarget && closeModal()}>
          <div className={styles.modal}>
            <div className={styles.modalHeader}>
              <h2 className={styles.modalTitle}>Add Power Schedule</h2>
              <button className={styles.modalClose} onClick={closeModal}>✕</button>
            </div>

            <form onSubmit={handleCreate}>
              <div className={styles.modalBody}>

                {error && <div className={styles.modalError}>⚠ {error}</div>}

                {/* Device */}
                <div className={styles.field}>
                  <label className={styles.label}>Device</label>
                  <select
                    className={styles.select}
                    required
                    value={form.appliance_id}
                    onChange={e => setForm(f => ({ ...f, appliance_id: e.target.value }))}
                  >
                    <option value="" disabled>Select a device…</option>
                    {appliances.map(a => (
                      <option key={a.id} value={a.id}>{a.name}{a.room ? ` — ${a.room}` : ''}</option>
                    ))}
                  </select>
                </div>

                {/* Action */}
                <div className={styles.field}>
                  <label className={styles.label}>Action</label>
                  <div className={styles.actionTabs}>
                    <button
                      type="button"
                      className={`${styles.actionTab} ${styles.actionTabOff} ${form.action === 'off' ? styles.actionTabActive : ''}`}
                      onClick={() => setForm(f => ({ ...f, action: 'off' }))}
                    >Power Off</button>
                    <button
                      type="button"
                      className={`${styles.actionTab} ${styles.actionTabOn} ${form.action === 'on' ? styles.actionTabActive : ''}`}
                      onClick={() => setForm(f => ({ ...f, action: 'on' }))}
                    >Power On</button>
                  </div>
                </div>

                {/* Schedule Type */}
                <div className={styles.field}>
                  <label className={styles.label}>Schedule Type</label>
                  <div className={styles.typeTabs}>
                    <button
                      type="button"
                      className={`${styles.typeTab} ${form.scheduleType === 'fixed' ? styles.typeTabActive : ''}`}
                      onClick={() => setForm(f => ({ ...f, scheduleType: 'fixed' }))}
                    >Fixed Time</button>
                    <button
                      type="button"
                      className={`${styles.typeTab} ${form.scheduleType === 'timer' ? styles.typeTabActive : ''}`}
                      onClick={() => setForm(f => ({ ...f, scheduleType: 'timer' }))}
                    >Timer</button>
                  </div>
                </div>

                {form.scheduleType === 'fixed' ? (
                  <>
                    {/* Time */}
                    <div className={styles.field}>
                      <label className={styles.label}>Time</label>
                      <input
                        className={styles.timeInput}
                        type="time"
                        required
                        value={form.time}
                        onChange={e => setForm(f => ({ ...f, time: e.target.value }))}
                      />
                    </div>

                    {/* Days */}
                    <div className={styles.field}>
                      <label className={styles.label}>Repeat on</label>
                      <div className={styles.daysRow}>
                        <button
                          type="button"
                          className={`${styles.dayBtn} ${styles.everyDayBtn} ${form.days.length === 7 ? styles.dayBtnActive : ''}`}
                          onClick={toggleAllDays}
                        >Every day</button>
                        {DAYS.map(d => (
                          <button
                            key={d.value}
                            type="button"
                            className={`${styles.dayBtn} ${form.days.includes(d.value) ? styles.dayBtnActive : ''}`}
                            onClick={() => toggleDay(d.value)}
                          >{d.label}</button>
                        ))}
                      </div>
                    </div>
                  </>
                ) : (
                  /* Timer */
                  <div className={styles.field}>
                    <label className={styles.label}>Run after</label>
                    <div className={styles.timerRow}>
                      <div className={styles.timerField}>
                        <input
                          className={styles.timerInput}
                          type="number"
                          min="0"
                          max="23"
                          value={form.timerH}
                          onChange={e => setForm(f => ({ ...f, timerH: Math.max(0, Math.min(23, +e.target.value || 0)) }))}
                        />
                        <span className={styles.timerUnit}>h</span>
                      </div>
                      <div className={styles.timerSep}>:</div>
                      <div className={styles.timerField}>
                        <input
                          className={styles.timerInput}
                          type="number"
                          min="0"
                          max="59"
                          value={form.timerM}
                          onChange={e => setForm(f => ({ ...f, timerM: Math.max(0, Math.min(59, +e.target.value || 0)) }))}
                        />
                        <span className={styles.timerUnit}>m</span>
                      </div>
                    </div>
                    <p className={styles.timerHint}>
                      Action runs once, {form.timerH * 60 + form.timerM < 1 ? 'set at least 1 minute' : `in ${form.timerH > 0 ? `${form.timerH}h ` : ''}${form.timerM}m from when saved`}
                    </p>
                  </div>
                )}

                <div className={styles.modalFooter}>
                  <button type="button" className={styles.btnSecondary} onClick={closeModal}>Cancel</button>
                  <button type="submit" className={styles.btnPrimary} disabled={saving}>
                    {saving ? 'Saving…' : 'Add Schedule'}
                  </button>
                </div>

              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
