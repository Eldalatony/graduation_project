'use client';

import { useState, useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
import styles from './Navbar.module.css';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:3001';

const TYPE_CONFIG = {
  HIGH_USAGE: { label: 'High Usage', color: '#f59e0b' },
  LEFT_ON:    { label: 'Left On',    color: '#3b82f6' },
  OFFLINE:    { label: 'Offline',    color: '#ef4444' },
};

const NAV_LINKS = [
  { key: 'home',       label: 'Home',       path: '/home' },
  { key: 'appliances', label: 'Appliances', path: '/appliances' },
  { key: 'analytics',  label: 'Analytics',  path: '/analytics' },
  { key: 'schedules',  label: 'Schedules',  path: '/schedules' },
  { key: 'settings',   label: 'Settings',   path: '/settings' },
];

const timeAgo = (ts) => {
  const diff = Date.now() - new Date(ts).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
};

export default function Navbar({ activePage }) {
  const router = useRouter();
  const [alerts, setAlerts]         = useState([]);
  const [userName, setUserName]     = useState('');
  const [open, setOpen]             = useState(false);
  const dropdownRef                 = useRef(null);

  const token   = () => (typeof window !== 'undefined' ? localStorage.getItem('token') : null);
  const headers = () => ({ 'Content-Type': 'application/json', Authorization: `Bearer ${token()}` });

  const fetchAlerts = async () => {
    if (!token()) return;
    try {
      const res = await fetch(`${API_URL}/api/alerts`, { headers: headers() });
      if (res.status === 401) { localStorage.removeItem('token'); router.replace('/auth'); return; }
      if (!res.ok) return;
      const data = await res.json();
      setAlerts(data.alerts || []);
    } catch { /* silent */ }
  };

  const fetchUser = async () => {
    if (!token()) return;
    try {
      const res = await fetch(`${API_URL}/api/users/settings`, { headers: headers() });
      if (!res.ok) return;
      const data = await res.json();
      setUserName(data.user?.name || '');
    } catch { /* silent */ }
  };

  useEffect(() => {
    fetchAlerts();
    fetchUser();
    const iv = setInterval(fetchAlerts, 15000);
    return () => clearInterval(iv);
  }, []);

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const markRead = async (id) => {
    try {
      const res = await fetch(`${API_URL}/api/alerts/${id}/read`, { method: 'PUT', headers: headers() });
      if (!res.ok) return;
      setAlerts(prev => prev.map(a => a.id === id ? { ...a, is_read: true } : a));
    } catch { /* silent */ }
  };

  const markAllRead = async () => {
    try {
      const res = await fetch(`${API_URL}/api/alerts/read-all`, { method: 'PUT', headers: headers() });
      if (!res.ok) return;
      setAlerts(prev => prev.map(a => ({ ...a, is_read: true })));
    } catch { /* silent */ }
  };

  const logout = () => {
    localStorage.removeItem('token');
    router.replace('/');
  };

  const unreadCount = alerts.filter(a => !a.is_read).length;

  return (
    <nav className={styles.nav}>
      {/* User */}
      <div className={styles.brand} onClick={() => router.push('/settings')} title="Account settings">
        <span className={styles.avatar}>{(userName || '?').charAt(0).toUpperCase()}</span>
        <span className={styles.name}>{userName || 'Account'}</span>
      </div>

      {/* Links */}
      <div className={styles.links}>
        {NAV_LINKS.map(l => (
          <button
            key={l.key}
            className={`${styles.link} ${activePage === l.key ? styles.linkActive : ''}`}
            onClick={() => router.push(l.path)}
          >
            {l.label}
          </button>
        ))}
      </div>

      {/* Right: bell + logout */}
      <div className={styles.right}>
        <div className={styles.bellWrap} ref={dropdownRef}>
          <button
            className={`${styles.bellBtn} ${open ? styles.bellBtnActive : ''}`}
            onClick={() => setOpen(o => !o)}
            title="Notifications"
          >
            🔔
            {unreadCount > 0 && (
              <span className={styles.badge}>{unreadCount > 9 ? '9+' : unreadCount}</span>
            )}
          </button>

          {open && (
            <div className={styles.dropdown}>
              <div className={styles.dropHeader}>
                <span className={styles.dropTitle}>
                  Notifications {unreadCount > 0 && `(${unreadCount})`}
                </span>
                {unreadCount > 0 && (
                  <button className={styles.markAllBtn} onClick={markAllRead}>
                    Mark all read
                  </button>
                )}
              </div>

              <div className={styles.alertList}>
                {alerts.length === 0 ? (
                  <div className={styles.empty}>
                    <div>All clear — no alerts</div>
                  </div>
                ) : (
                  alerts.slice(0, 20).map(alert => {
                    const cfg = TYPE_CONFIG[alert.type] || { label: alert.type, color: '#64748b' };
                    return (
                      <div
                        key={alert.id}
                        className={`${styles.alertItem} ${!alert.is_read ? styles.alertUnread : ''}`}
                        onClick={() => { if (!alert.is_read) markRead(alert.id); }}
                      >
                        <div className={styles.alertDot} style={{ background: cfg.color }} />
                        <div className={styles.alertBody}>
                          <div className={styles.alertTop}>
                            <span className={styles.alertType} style={{ color: cfg.color }}>
                              {cfg.label}
                            </span>
                            <span className={styles.alertTime}>{timeAgo(alert.triggered_at)}</span>
                          </div>
                          {alert.appliance_name && (
                            <div className={styles.alertDevice}>{alert.appliance_name}</div>
                          )}
                          <div className={styles.alertMsg}>{alert.message}</div>
                        </div>
                        {!alert.is_read && <div className={styles.unreadDot} />}
                      </div>
                    );
                  })
                )}
              </div>
            </div>
          )}
        </div>

        <button className={styles.logoutBtn} onClick={logout}>Logout</button>
      </div>
    </nav>
  );
}
