'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Navbar from '../components/Navbar';
import styles from './page.module.css';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:3001';

export default function SettingsPage() {
  const router = useRouter();

  const [user, setUser]       = useState(null);
  const [loading, setLoading] = useState(true);

  // Profile form
  const [name, setName]           = useState('');
  const [profileMsg, setProfileMsg] = useState(null); // { ok, text }
  const [profileSaving, setProfileSaving] = useState(false);


  const token   = () => localStorage.getItem('token');
  const headers = () => ({ 'Content-Type': 'application/json', Authorization: `Bearer ${token()}` });

  const fetchSettings = async () => {
    try {
      const res = await fetch(`${API_URL}/api/users/settings`, { headers: headers() });
      if (res.status === 401) { localStorage.removeItem('token'); router.replace('/auth'); return; }
      const data = await res.json();
      if (!res.ok) throw new Error(data.message);
      setUser(data.user);
      setName(data.user.name || '');
    } catch {
      // fail silently — user still sees the form
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!token()) { router.replace('/auth'); return; }
    fetchSettings();
  }, []);

  const saveProfile = async (e) => {
    e.preventDefault();
    if (!name.trim()) return;
    setProfileSaving(true);
    setProfileMsg(null);
    try {
      const res = await fetch(`${API_URL}/api/users/settings`, {
        method: 'PUT',
        headers: headers(),
        body: JSON.stringify({ name: name.trim() }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.message || `HTTP ${res.status}`);
      setUser(data.user);
      setProfileMsg({ ok: true, text: 'Profile updated' });
    } catch (err) {
      setProfileMsg({ ok: false, text: err.message });
    } finally {
      setProfileSaving(false);
    }
  };

  const formatDate = (ts) =>
    ts ? new Date(ts).toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' }) : '—';

  return (
    <div className={styles.page}>
      <Navbar activePage="settings" />

      <div className={styles.content}>
        <div className={styles.pageHeader}>
          <h1 className={styles.pageTitle}>Settings</h1>
          <p className={styles.pageSubtitle}>Manage your account and energy preferences</p>
        </div>

        {/* ── Profile card ── */}
        <div className={styles.card}>
          <div className={styles.cardHeader}>
            <div>
              <p className={styles.cardTitle}>Profile</p>
              <p className={styles.cardDesc}>Your personal account information</p>
            </div>
          </div>

          <form onSubmit={saveProfile}>
            <div className={styles.cardBody}>
              {loading ? (
                <>
                  <div className={styles.skeleton} />
                  <div className={styles.skeleton} />
                </>
              ) : (
                <>
                  <div className={styles.fieldRow}>
                    <div className={styles.field}>
                      <label className={styles.label}>Full Name</label>
                      <input
                        className={styles.input}
                        value={name}
                        onChange={e => { setName(e.target.value); setProfileMsg(null); }}
                        placeholder="Your name"
                        required
                      />
                    </div>
                    <div className={styles.field}>
                      <label className={styles.label}>Email</label>
                      <input
                        className={`${styles.input} ${styles.inputReadonly}`}
                        value={user?.email || ''}
                        readOnly
                      />
                      <span className={styles.hint}>Email cannot be changed</span>
                    </div>
                  </div>

                  <div className={styles.fieldRow}>
                    <div className={styles.field}>
                      <label className={styles.label}>Role</label>
                      <input
                        className={`${styles.input} ${styles.inputReadonly}`}
                        value={user?.role || 'user'}
                        readOnly
                      />
                    </div>
                    <div className={styles.field}>
                      <label className={styles.label}>Member Since</label>
                      <input
                        className={`${styles.input} ${styles.inputReadonly}`}
                        value={formatDate(user?.created_at)}
                        readOnly
                      />
                    </div>
                  </div>
                </>
              )}
            </div>

            <div className={styles.cardFooter}>
              <span className={`${styles.footerMsg} ${profileMsg && !profileMsg.ok ? styles.footerMsgError : ''}`}>
                {profileMsg && (profileMsg.ok ? `✓ ${profileMsg.text}` : `✕ ${profileMsg.text}`)}
              </span>
              <button className={styles.saveBtn} type="submit" disabled={profileSaving || loading}>
                {profileSaving ? 'Saving…' : 'Save Profile'}
              </button>
            </div>
          </form>
        </div>

      </div>
    </div>
  );
}
