// API Service for Proof-of-Action Frontend
// Handles all backend API communication

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';

// Create axios instance
import axios from 'axios';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor for adding auth token
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('auth_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor for handling errors
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Token expired or invalid - clear auth and redirect to login
      localStorage.removeItem('auth_token');
      localStorage.removeItem('user');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

// Authentication API
export const authApi = {
  login: (username, password) => api.post('/auth/login', { username, password }),
  logout: () => api.post('/auth/logout'),
  getCurrentUser: () => api.get('/auth/me'),
};

// Project API
export const projectApi = {
  getAll: (params = {}) => api.get('/projects', { params }),
  getById: (id) => api.get(`/projects/${id}`),
  create: (data) => api.post('/projects', data),
  update: (id, data) => api.patch(`/projects/${id}`, data),
  delete: (id) => api.delete(`/projects/${id}`),
};

// Evidence API
export const evidenceApi = {
  createUpload: (data) => api.post('/evidence/uploads', data),
  completeUpload: (id) => api.post(`/evidence/${id}/complete`),
  getById: (id) => api.get(`/evidence/${id}`),
  getAnalysis: (id) => api.get(`/evidence/${id}/analysis`),
  getSimilar: (id) => api.get(`/evidence/${id}/similar`),
  getAnomalies: (id) => api.get(`/evidence/${id}/anomalies`),
  getGraph: (id) => api.get(`/evidence/${id}/graph`),
  search: (params = {}) => api.get('/evidence/search', { params }),
};

// Review API
export const reviewApi = {
  getQueue: (params = {}) => api.get('/reviews/queue', { params }),
  makeDecision: (id, data) => api.post(`/reviews/${id}/decision`, data),
  getHistory: (params = {}) => api.get('/reviews/history', { params }),
};

// Audit API
export const auditApi = {
  getEvents: (params = {}) => api.get('/audit/events', { params }),
};

// Admin API
export const adminApi = {
  getUsers: (params = {}) => api.get('/admin/users', { params }),
  updateUser: (id, data) => api.patch(`/admin/users/${id}`, data),
  createUser: (data) => api.post('/admin/users', data),
  getConfig: () => api.get('/admin/config'),
  updateConfig: (data) => api.put('/admin/config', data),
  getMetrics: () => api.get('/admin/metrics'),
};

export default api;
