// API Service for PRISM / Proof-of-Action Frontend
// Handles all backend API communication with FastAPI backend
import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1';

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
  (error) => Promise.reject(error)
);

// Response interceptor for handling errors
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && window.location.pathname !== '/login') {
      // Token expired or unauthorized
      localStorage.removeItem('auth_token');
      localStorage.removeItem('user');
    }
    return Promise.reject(error);
  }
);

// ----------------------------------------------------------------------
// Authentication & Principals
// ----------------------------------------------------------------------
export const authApi = {
  getCurrentUser: () => api.get('/auth/me'),
  getUsers: (params = {}) => api.get('/auth/users', { params }),
  getUserById: (id) => api.get(`/auth/users/${id}`),
  createUser: (data) => api.post('/auth/users', data),
  getRoles: (params = {}) => api.get('/auth/roles', { params }),
  getPermissions: (params = {}) => api.get('/auth/permissions', { params }),
  getOrganizations: (params = {}) => api.get('/auth/organizations', { params }),
  // Mock login helper that registers dev bearer token or mock credentials
  login: async (username) => {
    const token = `dev-user-${username}`;
    localStorage.setItem('auth_token', token);
    return { data: { success: true, token } };
  },
  logout: () => {
    localStorage.removeItem('auth_token');
    localStorage.removeItem('user');
    return Promise.resolve({ data: { success: true } });
  },
};

// ----------------------------------------------------------------------
// Projects (Context & Lifecycle - BE-039)
// ----------------------------------------------------------------------
export const projectApi = {
  getAll: (params = {}) => api.get('/projects', { params }),
  getById: (id) => api.get(`/projects/${id}`),
  create: (data) => api.post('/projects', {
    name: data.name,
    owner_id: data.owner_id || undefined,
  }),
  update: (id, data) => api.patch(`/projects/${id}`, data),
  getActivities: (id, params = {}) => api.get(`/projects/${id}/activities`, { params }),
  createActivity: (id, data) => api.post(`/projects/${id}/activities`, data),
  transferOwnership: (id, data) => api.post(`/auth/projects/${id}/ownership`, data),
};

// ----------------------------------------------------------------------
// Evidence Registry & Ingestion
// ----------------------------------------------------------------------
export const evidenceApi = {
  upload: (file, onProgress) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post('/evidence', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: onProgress,
    });
  },
  getById: (id) => api.get(`/evidence/${id}`),
  download: (id) => api.get(`/evidence/${id}/download`, { responseType: 'blob' }),
  getNearby: (params = {}) => api.get('/evidence/nearby', { params }),
  updateContext: (id, data) => api.patch(`/evidence/${id}/context`, data),
  updateLocation: (id, data) => api.patch(`/evidence/${id}/location`, data),
  getVision: (id) => api.get(`/evidence/${id}/vision`),
  // Compatibility helpers
  createUpload: (data) => api.post('/evidence', data),
  completeUpload: (id) => Promise.resolve({ data: { id, status: 'completed' } }),
  getAnalysis: (id) => api.get(`/evidence/${id}/vision`),
  getSimilar: (id) => api.get('/evidence/nearby', { params: { radius_meters: 500 } }),
  getAnomalies: (id) => api.get(`/evidence/${id}/vision`),
  getGraph: (id) => api.get(`/graph/evidence/${id}`),
  search: (params = {}) => api.get('/evidence/nearby', { params }),
};

// ----------------------------------------------------------------------
// Review Cases & Adjudication (BE-012/BE-014)
// ----------------------------------------------------------------------
export const reviewApi = {
  getQueue: (params = {}) => api.get('/review-cases', { params }),
  getById: (id) => api.get(`/review-cases/${id}`),
  resolve: (id, data = {}) => api.post(`/review-cases/${id}/resolve`, data),
  escalate: (id, data = {}) => api.post(`/review-cases/${id}/escalate`, data),
  reopen: (id, data = {}) => api.post(`/review-cases/${id}/reopen`, data),
  // Compatibility wrappers
  makeDecision: (id, data) => api.post(`/review-cases/${id}/resolve`, data),
  getHistory: (params = {}) => api.get('/review-cases', { params: { status: 'RESOLVED', ...params } }),
};

// ----------------------------------------------------------------------
// Audit Ledger & Provenance (BE-015/BE-030)
// ----------------------------------------------------------------------
export const auditApi = {
  getEvents: (params = {}) => api.get('/audit/events', { params }),
  getById: (id) => api.get(`/audit/events/${id}`),
  getIntegrityBaseline: (anchorId) => api.get(`/audit/anchors/${anchorId}/verification`),
};

// ----------------------------------------------------------------------
// Intelligence Graph (BE-010)
// ----------------------------------------------------------------------
export const graphApi = {
  getEntityGraph: (nodeType, entityId, params = {}) => api.get(`/graph/${nodeType}/${entityId}`, { params }),
  createRelationship: (data) => api.post('/graph/relationships', data),
};

// ----------------------------------------------------------------------
// System Health, Telemetry & Admin
// ----------------------------------------------------------------------
export const adminApi = {
  getUsers: (params = {}) => api.get('/auth/users', { params }),
  createUser: (data) => api.post('/auth/users', data),
  getRoles: (params = {}) => api.get('/auth/roles', { params }),
  getPermissions: (params = {}) => api.get('/auth/permissions', { params }),
  getOrganizations: (params = {}) => api.get('/auth/organizations', { params }),
  getMetrics: () => api.get('/metrics'),
  getHealth: () => api.get('/health'),
  getReady: () => api.get('/ready'),
  getConfig: () => Promise.resolve({
    data: {
      high_risk_threshold: 70,
      medium_risk_threshold: 40,
      geofence_tolerance_meters: 50,
      impossible_travel_speed_kmh: 120,
      retention_period_days: 90,
      max_upload_size_mb: 15,
      quarantine_auto_purge: true,
      strict_mime_validation: true,
    }
  }),
  updateConfig: (data) => Promise.resolve({ data }),
};

// ----------------------------------------------------------------------
// Public Transparency Portal (BE-022)
// ----------------------------------------------------------------------
export const publicApi = {
  getProjects: (params = {}) => api.get('/public/projects', { params }),
  getProject: (publicId) => api.get(`/public/projects/${publicId}`),
  getProjectEvidence: (publicId) => api.get(`/public/projects/${publicId}/evidence`),
  getEvidence: (publicId) => api.get(`/public/evidence/${publicId}`),
};

export default api;
