'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import styles from './page.module.css';
import { API_URL } from '../lib/api';

export default function AuthPage() {
  const router = useRouter();
  const [mode, setMode] = useState('login');
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const [loginForm, setLoginForm] = useState({ email: '', password: '' });
  const [signupForm, setSignupForm] = useState({ name: '', email: '', password: '' });
  const [resetForm, setResetForm] = useState({ email: '', code: '', newPassword: '' });
  const [notice, setNotice] = useState(null);

  const handleLogin = async (e) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(loginForm),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.message || `HTTP ${res.status}`);
      localStorage.setItem('token', data.token);
      router.push('/home');
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleSignup = async (e) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(signupForm),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.message || `HTTP ${res.status}`);
      localStorage.setItem('token', data.token);
      router.push('/home');
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleForgot = async (e) => {
    e.preventDefault();
    setError(null);
    setNotice(null);
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/auth/forgot-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: resetForm.email }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.message || `HTTP ${res.status}`);
      setNotice('If that email is registered, a 6-digit code is on its way. Enter it below.');
      setMode('reset');
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleReset = async (e) => {
    e.preventDefault();
    setError(null);
    setNotice(null);
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/auth/reset-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(resetForm),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.message || `HTTP ${res.status}`);
      setNotice('Password reset! You can now sign in with your new password.');
      setMode('login');
      setResetForm({ email: '', code: '', newPassword: '' });
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const switchMode = (next) => {
    setMode(next);
    setError(null);
    setNotice(null);
  };

  return (
    <div className={styles.page}>
      <div className={styles.card}>

        <div className={styles.logo}>
          <div>
            <div className={styles.logoText}>SHEMMS</div>
            <div className={styles.logoSub}>Smart Home Energy Monitor</div>
          </div>
        </div>

        {(mode === 'login' || mode === 'signup') && (
          <div className={styles.tabs}>
            <button
              className={`${styles.tab} ${mode === 'login' ? styles.tabActive : ''}`}
              onClick={() => switchMode('login')}
            >
              Sign In
            </button>
            <button
              className={`${styles.tab} ${mode === 'signup' ? styles.tabActive : ''}`}
              onClick={() => switchMode('signup')}
            >
              Create Account
            </button>
          </div>
        )}

        {error && (
          <div className={styles.error}>
            <span>⚠</span>
            {error}
          </div>
        )}

        {notice && (
          <div className={styles.notice}>{notice}</div>
        )}

        {mode === 'login' && (
          <form className={styles.form} onSubmit={handleLogin}>
            <div className={styles.field}>
              <label className={styles.label}>Email address</label>
              <input
                className={styles.input}
                type="email"
                required
                placeholder="you@example.com"
                value={loginForm.email}
                onChange={e => setLoginForm(f => ({ ...f, email: e.target.value }))}
              />
            </div>
            <div className={styles.field}>
              <label className={styles.label}>Password</label>
              <input
                className={styles.input}
                type="password"
                required
                placeholder="••••••••"
                value={loginForm.password}
                onChange={e => setLoginForm(f => ({ ...f, password: e.target.value }))}
              />
            </div>
            <button className={styles.submitBtn} type="submit" disabled={loading}>
              {loading ? 'Signing in…' : 'Sign In'}
            </button>
            <button
              type="button"
              className={styles.switchLink}
              onClick={() => switchMode('forgot')}
            >
              Forgot password?
            </button>
          </form>
        )}

        {mode === 'signup' && (
          <form className={styles.form} onSubmit={handleSignup}>
            <div className={styles.field}>
              <label className={styles.label}>Full name</label>
              <input
                className={styles.input}
                type="text"
                required
                placeholder="John Doe"
                value={signupForm.name}
                onChange={e => setSignupForm(f => ({ ...f, name: e.target.value }))}
              />
            </div>
            <div className={styles.field}>
              <label className={styles.label}>Email address</label>
              <input
                className={styles.input}
                type="email"
                required
                placeholder="you@example.com"
                value={signupForm.email}
                onChange={e => setSignupForm(f => ({ ...f, email: e.target.value }))}
              />
            </div>
            <div className={styles.field}>
              <label className={styles.label}>Password</label>
              <input
                className={styles.input}
                type="password"
                required
                placeholder="••••••••"
                value={signupForm.password}
                onChange={e => setSignupForm(f => ({ ...f, password: e.target.value }))}
              />
            </div>
            <button className={styles.submitBtn} type="submit" disabled={loading}>
              {loading ? 'Creating account…' : 'Create Account'}
            </button>
          </form>
        )}

        {mode === 'forgot' && (
          <form className={styles.form} onSubmit={handleForgot}>
            <div className={styles.field}>
              <label className={styles.label}>Email address</label>
              <input
                className={styles.input}
                type="email"
                required
                placeholder="you@example.com"
                value={resetForm.email}
                onChange={e => setResetForm(f => ({ ...f, email: e.target.value }))}
              />
            </div>
            <button className={styles.submitBtn} type="submit" disabled={loading}>
              {loading ? 'Sending…' : 'Send reset code'}
            </button>
            <button type="button" className={styles.switchLink} onClick={() => switchMode('login')}>
              Back to sign in
            </button>
          </form>
        )}

        {mode === 'reset' && (
          <form className={styles.form} onSubmit={handleReset}>
            <div className={styles.field}>
              <label className={styles.label}>Email address</label>
              <input
                className={styles.input}
                type="email"
                required
                placeholder="you@example.com"
                value={resetForm.email}
                onChange={e => setResetForm(f => ({ ...f, email: e.target.value }))}
              />
            </div>
            <div className={styles.field}>
              <label className={styles.label}>6-digit code</label>
              <input
                className={styles.input}
                type="text"
                inputMode="numeric"
                maxLength={6}
                required
                placeholder="123456"
                value={resetForm.code}
                onChange={e => setResetForm(f => ({ ...f, code: e.target.value }))}
              />
            </div>
            <div className={styles.field}>
              <label className={styles.label}>New password</label>
              <input
                className={styles.input}
                type="password"
                required
                placeholder="••••••••"
                value={resetForm.newPassword}
                onChange={e => setResetForm(f => ({ ...f, newPassword: e.target.value }))}
              />
            </div>
            <button className={styles.submitBtn} type="submit" disabled={loading}>
              {loading ? 'Resetting…' : 'Reset password'}
            </button>
            <button type="button" className={styles.switchLink} onClick={() => switchMode('login')}>
              Back to sign in
            </button>
          </form>
        )}

        {(mode === 'login' || mode === 'signup') && (
          <p className={styles.switchRow}>
            {mode === 'login' ? "Don't have an account?" : 'Already have an account?'}
            <button className={styles.switchLink} onClick={() => switchMode(mode === 'login' ? 'signup' : 'login')}>
              {mode === 'login' ? 'Create one' : 'Sign in'}
            </button>
          </p>
        )}

      </div>
    </div>
  );
}
