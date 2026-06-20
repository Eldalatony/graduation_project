import { getToken } from './auth';

export const API_URL = process.env.EXPO_PUBLIC_API_URL || 'http://localhost:3001';

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

async function request(path, { method = 'GET', body, auth = true } = {}) {
  const headers = { 'Content-Type': 'application/json' };
  if (auth) {
    const token = await getToken();
    if (token) headers.Authorization = `Bearer ${token}`;
  }

  const res = await fetch(`${API_URL}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });

  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new ApiError(data.message || `HTTP ${res.status}`, res.status);
  }
  return data;
}

export const api = {
  login:         (email, password) => request('/api/auth/login', { method: 'POST', body: { email, password }, auth: false }),
  listAppliances: () => request('/api/appliances'),
  liveSnapshot:   () => request('/api/live'),
};
