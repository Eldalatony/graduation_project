'use client';

import { useEffect, useState, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import styles from './page.module.css';
import Navbar from '../components/Navbar';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:3001';

const EMPTY_FORM = { name: '', node_key: '', gateway_id: '', room: '', is_active: true };

export default function AppliancesPage() {
  const router = useRouter();
  const [appliances, setAppliances]     = useState([]);
  const [spaces, setSpaces]             = useState([]);
  const [liveMap, setLiveMap]           = useState({});
  const [loading, setLoading]           = useState(true);
  const [error, setError]               = useState(null);

  // create / edit modal
  const [modal, setModal]     = useState(null); // null | 'create' | 'edit'
  const [editing, setEditing] = useState(null); // appliance object being edited
  const [form, setForm]       = useState(EMPTY_FORM);
  const [saving, setSaving]   = useState(false);

  // space (room) management modal
  const [spaceModal, setSpaceModal]   = useState(null); // null | { mode:'create'|'rename', id, name }
  const [spaceSaving, setSpaceSaving] = useState(false);

  // readings modal
  const [rdModal, setRdModal]     = useState(null); // { id, name }
  const [readings, setReadings]   = useState([]);
  const [rdLoading, setRdLoading] = useState(false);

  const token = () => (typeof window !== 'undefined' ? localStorage.getItem('token') : null);
  const headers = () => ({ 'Content-Type': 'application/json', Authorization: `Bearer ${token()}` });

  const handleAuth = (status) => {
    if (status === 401) { localStorage.removeItem('token'); router.replace('/auth'); return true; }
    return false;
  };

  const fetchAppliances = async () => {
    try {
      const res = await fetch(`${API_URL}/api/appliances`, { headers: headers() });
      if (handleAuth(res.status)) return;
      const data = await res.json();
      if (!res.ok) throw new Error(data.message || `HTTP ${res.status}`);
      setAppliances(data.appliances || []);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const fetchSpaces = async () => {
    try {
      const res = await fetch(`${API_URL}/api/spaces`, { headers: headers() });
      if (handleAuth(res.status)) return;
      const data = await res.json();
      if (res.ok) setSpaces(data.spaces || []);
    } catch { /* silent */ }
  };

  const fetchLive = async () => {
    try {
      const res = await fetch(`${API_URL}/api/live`, { headers: headers() });
      if (!res.ok) return;
      const data = await res.json();
      setLiveMap(data || {});
    } catch { /* silent */ }
  };

  useEffect(() => {
    if (!token()) { router.replace('/auth'); return; }
    fetchAppliances();
    fetchSpaces();
    fetchLive();
    const iv = setInterval(fetchLive, 1000);
    return () => clearInterval(iv);
  }, []);

  // ── Room grouping (includes empty managed spaces) ──
  const { grouped, roomOrder } = useMemo(() => {
    const map = {};
    spaces.forEach(s => { map[s.name] = []; });          // empty spaces still render
    appliances.forEach(a => {
      const room = a.room?.trim() || 'Unassigned';
      (map[room] ??= []).push(a);
    });
    const realRooms = Object.keys(map)
      .filter(r => r !== 'Unassigned')
      .sort((a, b) => a.localeCompare(b));
    const order = [...realRooms];
    if (map['Unassigned']?.length) order.push('Unassigned');
    return { grouped: map, roomOrder: order };
  }, [appliances, spaces]);

  const spaceNames    = useMemo(() => spaces.map(s => s.name), [spaces]);
  const spaceIdByName = useMemo(
    () => Object.fromEntries(spaces.map(s => [s.name, s.id])), [spaces]
  );

  // ── CRUD ──
  const openCreate = () => { setForm(EMPTY_FORM); setEditing(null); setModal('create'); };
  const openEdit   = (a)  => {
    setForm({ name: a.name, node_key: a.node_key, gateway_id: a.gateway_id || '', room: a.room || '', is_active: a.is_active });
    setEditing(a);
    setModal('edit');
  };
  const closeModal = () => { setModal(null); setEditing(null); setForm(EMPTY_FORM); };

  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const url    = modal === 'edit' ? `${API_URL}/api/appliances/${editing.id}` : `${API_URL}/api/appliances`;
      const method = modal === 'edit' ? 'PUT' : 'POST';
      const res    = await fetch(url, { method, headers: headers(), body: JSON.stringify(form) });
      if (handleAuth(res.status)) return;
      const data = await res.json();
      if (!res.ok) throw new Error(data.message || `HTTP ${res.status}`);
      closeModal();
      fetchAppliances();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (a) => {
    if (!confirm(`Delete "${a.name}"?`)) return;
    setError(null);
    try {
      const res = await fetch(`${API_URL}/api/appliances/${a.id}`, { method: 'DELETE', headers: headers() });
      if (handleAuth(res.status)) return;
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.message || `HTTP ${res.status}`);
      fetchAppliances();
    } catch (err) {
      setError(err.message);
    }
  };

  // ── Space (room) management ──
  const openAddSpace    = () => setSpaceModal({ mode: 'create', id: null, name: '' });
  const openRenameSpace = (name) => setSpaceModal({ mode: 'rename', id: spaceIdByName[name], name });
  const closeSpaceModal = () => setSpaceModal(null);

  const handleSaveSpace = async (e) => {
    e.preventDefault();
    const name = spaceModal.name.trim();
    if (!name) return;
    setSpaceSaving(true);
    setError(null);
    try {
      const url    = spaceModal.mode === 'rename' ? `${API_URL}/api/spaces/${spaceModal.id}` : `${API_URL}/api/spaces`;
      const method = spaceModal.mode === 'rename' ? 'PUT' : 'POST';
      const res    = await fetch(url, { method, headers: headers(), body: JSON.stringify({ name }) });
      if (handleAuth(res.status)) return;
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.message || `HTTP ${res.status}`);
      closeSpaceModal();
      fetchSpaces();
      fetchAppliances();
    } catch (err) {
      setError(err.message);
    } finally {
      setSpaceSaving(false);
    }
  };

  const handleDeleteSpace = async (name) => {
    const id = spaceIdByName[name];
    if (!id) return;
    const count = grouped[name]?.length || 0;
    const msg = count
      ? `Remove space "${name}"? Its ${count} appliance${count !== 1 ? 's' : ''} will move to Unassigned.`
      : `Remove empty space "${name}"?`;
    if (!confirm(msg)) return;
    setError(null);
    try {
      const res = await fetch(`${API_URL}/api/spaces/${id}`, { method: 'DELETE', headers: headers() });
      if (handleAuth(res.status)) return;
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.message || `HTTP ${res.status}`);
      fetchSpaces();
      fetchAppliances();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleMove = async (a, target) => {
    if ((a.room?.trim() || 'Unassigned') === target) return;
    const room = target === 'Unassigned' ? '' : target;
    setError(null);
    try {
      const res = await fetch(`${API_URL}/api/appliances/${a.id}`, {
        method: 'PUT', headers: headers(), body: JSON.stringify({ room }),
      });
      if (handleAuth(res.status)) return;
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.message || `HTTP ${res.status}`);
      fetchAppliances();
      fetchSpaces();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleControl = async (a, command) => {
    setError(null);
    try {
      const res = await fetch(`${API_URL}/api/appliances/${a.id}/control`, {
        method: 'POST', headers: headers(), body: JSON.stringify({ command }),
      });
      if (handleAuth(res.status)) return;
      const data = await res.json();
      if (!res.ok) throw new Error(data.message || `HTTP ${res.status}`);
      fetchAppliances();
    } catch (err) {
      setError(err.message);
    }
  };

  const openReadings = async (a) => {
    setRdModal({ id: a.id, name: a.name });
    setReadings([]);
    setRdLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/appliances/${a.id}/readings?minutes=5`, { headers: headers() });
      if (handleAuth(res.status)) return;
      const data = await res.json();
      if (!res.ok) throw new Error(data.message || `HTTP ${res.status}`);
      setReadings(data.readings || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setRdLoading(false);
    }
  };

  // ── Card status ──
  const getStatus = (a) => {
    const live = liveMap[`${a.gateway_id}/${a.node_key}`];
    return live?.status || (a.is_active ? 'active' : 'idle');
  };

  const cardClass = (status) =>
    status === 'active' ? styles.cardActive : status === 'offline' ? styles.cardOffline : styles.cardIdle;

  const badgeClass = (status) =>
    status === 'active' ? styles.badgeActive : status === 'offline' ? styles.badgeOffline : styles.badgeIdle;

  return (
    <div className={styles.page}>
      <Navbar activePage="appliances" />

      <div className={styles.content}>
        {/* ── Header ── */}
        <div className={styles.pageHeader}>
          <div>
            <h1 className={styles.pageTitle}>Appliances</h1>
            <p className={styles.pageSubtitle}>Manage and monitor your home devices</p>
          </div>
          <div className={styles.headerActions}>
            <button className={styles.addBtnSecondary} onClick={openAddSpace}>
              + Add Space
            </button>
            <button className={styles.addBtn} onClick={openCreate}>
              + Add Appliance
            </button>
          </div>
        </div>

        {error && (
          <div className={styles.error}>⚠ {error}</div>
        )}

        {/* ── Content ── */}
        {loading ? (
          <div className={styles.loading}>
            <div className={styles.spinner} />
            <div>Loading your appliances…</div>
          </div>
        ) : appliances.length === 0 ? (
          <div className={styles.emptyPage}>
            <p className={styles.emptyTitle}>No appliances yet</p>
            <p className={styles.emptyText}>Add your first device to start monitoring your home energy.</p>
          </div>
        ) : (
          roomOrder.map(room => (
            <section key={room} className={styles.roomSection}>
              <div className={styles.roomHeader}>
                <span className={styles.roomName}>{room}</span>
                <span className={styles.roomCount}>{grouped[room].length} device{grouped[room].length !== 1 ? 's' : ''}</span>
                {room !== 'Unassigned' && (
                  <span className={styles.roomActions}>
                    <button className={styles.iconBtn} title="Rename space" onClick={() => openRenameSpace(room)}>✎</button>
                    <button className={`${styles.iconBtn} ${styles.iconBtnDanger}`} title="Remove space" onClick={() => handleDeleteSpace(room)}>🗑</button>
                  </span>
                )}
              </div>
              {grouped[room].length === 0 ? (
                <div className={styles.spaceEmpty}>No appliances here yet — move one in or add a new appliance.</div>
              ) : (
              <div className={styles.roomGrid}>
                {grouped[room].map(a => {
                  const live   = liveMap[`${a.gateway_id}/${a.node_key}`];
                  const status = getStatus(a);
                  return (
                    <div key={a.id} className={`${styles.card} ${cardClass(status)}`}>
                      <div className={styles.cardBody}>
                        <div className={styles.cardTop}>
                          <div className={styles.cardTopLeft}>
                            <div>
                              <div className={styles.deviceName}>{a.name}</div>
                              <div className={styles.deviceMeta}>{a.node_key}</div>
                            </div>
                          </div>
                          <span className={`${styles.statusBadge} ${badgeClass(status)}`}>
                            {status}
                          </span>
                        </div>

                        {live ? (
                          <>
                            <div className={styles.powerRow}>
                              <span className={styles.powerNumber}>{Number(live.power_W ?? 0).toFixed(0)}</span>
                              <span className={styles.powerUnit}>W</span>
                            </div>
                            <div className={styles.metricsGrid}>
                              <div className={styles.metricItem}>
                                <div className={styles.metricLabel}>Current</div>
                                <div className={styles.metricValue}>{Number(live.current_A ?? 0).toFixed(2)} A</div>
                              </div>
                              <div className={styles.metricItem}>
                                <div className={styles.metricLabel}>Rate</div>
                                <div className={styles.metricValue}>{(Number(live.cost_EGP ?? 0) * 3600).toFixed(2)} EGP/hr</div>
                              </div>
                            </div>
                          </>
                        ) : (
                          <div className={styles.noSignal}>No live signal</div>
                        )}

                        <div className={styles.moveRow}>
                          <span className={styles.moveLabel}>Space</span>
                          <select
                            className={styles.moveSelect}
                            value={a.room?.trim() || 'Unassigned'}
                            onChange={e => handleMove(a, e.target.value)}
                          >
                            {[...new Set([...(a.room?.trim() ? [a.room.trim()] : []), ...spaceNames])]
                              .map(n => <option key={n} value={n}>{n}</option>)}
                            <option value="Unassigned">Unassigned</option>
                          </select>
                        </div>
                      </div>

                      <div className={styles.cardActions}>
                        {a.is_active ? (
                          <button className={`${styles.actionBtn} ${styles.actionBtnOff}`} onClick={() => handleControl(a, 'off')}>Off</button>
                        ) : (
                          <button className={`${styles.actionBtn} ${styles.actionBtnOn}`} onClick={() => handleControl(a, 'on')}>On</button>
                        )}
                        <button className={styles.actionBtn} onClick={() => openReadings(a)}>History</button>
                        <button className={styles.actionBtn} onClick={() => openEdit(a)}>Edit</button>
                        <button className={`${styles.actionBtn} ${styles.actionBtnDanger}`} onClick={() => handleDelete(a)}>Delete</button>
                      </div>
                    </div>
                  );
                })}
              </div>
              )}
            </section>
          ))
        )}
      </div>

      {/* ── Create / Edit Modal ── */}
      {modal && (
        <div className={styles.overlay} onClick={(e) => e.target === e.currentTarget && closeModal()}>
          <div className={styles.modal}>
            <div className={styles.modalHeader}>
              <h2 className={styles.modalTitle}>{modal === 'edit' ? `Edit "${editing.name}"` : 'Add Appliance'}</h2>
              <button className={styles.modalClose} onClick={closeModal}>✕</button>
            </div>
            <div className={styles.modalBody}>
              <form onSubmit={handleSave}>
                <div className={styles.formGrid}>
                  <div className={styles.formRow}>
                    <div className={styles.field}>
                      <label className={styles.label}>Name *</label>
                      <input
                        className={styles.input}
                        required
                        placeholder="e.g. Air Conditioner"
                        value={form.name}
                        onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                      />
                    </div>
                    <div className={styles.field}>
                      <label className={styles.label}>Node Key *</label>
                      <input
                        className={styles.input}
                        required
                        placeholder="e.g. ac_unit"
                        value={form.node_key}
                        onChange={e => setForm(f => ({ ...f, node_key: e.target.value }))}
                      />
                    </div>
                  </div>

                  <div className={styles.formRow}>
                    <div className={styles.field}>
                      <label className={styles.label}>Room</label>
                      <input
                        className={styles.input}
                        list="rooms-list"
                        placeholder="e.g. Kitchen"
                        value={form.room}
                        onChange={e => setForm(f => ({ ...f, room: e.target.value }))}
                      />
                      <datalist id="rooms-list">
                        {spaceNames.map(r => <option key={r} value={r} />)}
                      </datalist>
                    </div>
                    <div className={styles.field}>
                      <label className={styles.label}>Gateway ID</label>
                      <input
                        className={styles.input}
                        placeholder="optional"
                        value={form.gateway_id}
                        onChange={e => setForm(f => ({ ...f, gateway_id: e.target.value }))}
                      />
                    </div>
                  </div>

                  <div className={styles.toggleRow}>
                    <label className={styles.toggle}>
                      <input
                        type="checkbox"
                        checked={form.is_active}
                        onChange={e => setForm(f => ({ ...f, is_active: e.target.checked }))}
                      />
                      <span className={styles.toggleSlider} />
                    </label>
                    <span className={styles.toggleLabel}>Active</span>
                  </div>

                  <div className={styles.modalFooter}>
                    <button type="button" className={styles.btnSecondary} onClick={closeModal}>Cancel</button>
                    <button type="submit" className={styles.btnPrimary} disabled={saving}>
                      {saving ? 'Saving…' : modal === 'edit' ? 'Save Changes' : 'Add Appliance'}
                    </button>
                  </div>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}

      {/* ── Add / Rename Space Modal ── */}
      {spaceModal && (
        <div className={styles.overlay} onClick={(e) => e.target === e.currentTarget && closeSpaceModal()}>
          <div className={styles.modal}>
            <div className={styles.modalHeader}>
              <h2 className={styles.modalTitle}>{spaceModal.mode === 'rename' ? 'Rename Space' : 'Add Space'}</h2>
              <button className={styles.modalClose} onClick={closeSpaceModal}>✕</button>
            </div>
            <div className={styles.modalBody}>
              <form onSubmit={handleSaveSpace}>
                <div className={styles.formGrid}>
                  <div className={styles.field}>
                    <label className={styles.label}>Space name *</label>
                    <input
                      className={styles.input}
                      required
                      autoFocus
                      placeholder="e.g. Living Room"
                      value={spaceModal.name}
                      onChange={e => setSpaceModal(m => ({ ...m, name: e.target.value }))}
                    />
                  </div>
                  <div className={styles.modalFooter}>
                    <button type="button" className={styles.btnSecondary} onClick={closeSpaceModal}>Cancel</button>
                    <button type="submit" className={styles.btnPrimary} disabled={spaceSaving}>
                      {spaceSaving ? 'Saving…' : spaceModal.mode === 'rename' ? 'Rename' : 'Add Space'}
                    </button>
                  </div>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}

      {/* ── Readings Modal ── */}
      {rdModal && (
        <div className={styles.overlay} onClick={(e) => e.target === e.currentTarget && setRdModal(null)}>
          <div className={styles.readingsModal}>
            <div className={styles.modalHeader} style={{ padding: '20px 24px 16px' }}>
              <h2 className={styles.modalTitle}>{rdModal.name} — Last 5 min</h2>
              <button className={styles.modalClose} onClick={() => setRdModal(null)}>✕</button>
            </div>
            <div className={styles.readingsBody}>
              {rdLoading ? (
                <div className={styles.readingsEmpty}>
                  <div className={styles.spinner} />
                  <div>Loading readings…</div>
                </div>
              ) : readings.length === 0 ? (
                <div className={styles.readingsEmpty}>No readings in the last 5 minutes.</div>
              ) : (
                <table className={styles.table}>
                  <thead>
                    <tr>
                      <th>Time</th>
                      <th>Power (W)</th>
                      <th>Current (A)</th>
                      <th>Voltage (V)</th>
                      <th>Energy (kWh)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {readings.map((r, i) => (
                      <tr key={i}>
                        <td>{r.time || r._time || '—'}</td>
                        <td>{r.power_W   ?? r.power   ?? '—'}</td>
                        <td>{r.current_A ?? r.current ?? '—'}</td>
                        <td>{r.voltage_V ?? r.voltage ?? '—'}</td>
                        <td>{r.energy_kWh ?? r.energy ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
