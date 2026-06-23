/**
 * API client — centralized HTTP client for the SheetNotify backend.
 */

import axios from 'axios';

// Users might configure VITE_API_URL or VITE_API_BASE_URL.
let API_BASE_URL = import.meta.env.VITE_API_URL || import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

// If they included /api in VITE_API_URL, don't append it again.
if (API_BASE_URL.endsWith('/api')) {
  API_BASE_URL = API_BASE_URL.slice(0, -4);
}

const api = axios.create({
  baseURL: `${API_BASE_URL}/api`,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Attach JWT token to every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('sheetnotify_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Handle 401 responses globally
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('sheetnotify_token');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export default api;
