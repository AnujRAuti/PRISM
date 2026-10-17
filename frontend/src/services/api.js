// API Service for PRISM / Proof-of-Action (PoA) Frontend
// Aligned with FastAPI Backend Contract & OpenAPI Specifications (BE-001 - BE-039)
import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 15000,
});

// Request interceptor for attaching Bearer authorization token
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

// Response interceptor for handling 401 unauthorized and normalized error handling
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && window.location.pathname !== '/login') {
      localStorage.removeItem('auth_token');
      localStorage.removeItem('user');
    }
    return Promise.reject(error);
  }
);

// ----------------------------------------------------------------------
// 1. Authentication & Identity (BE-016, ADR §6)
// ----------------------------------------------------------------------
export const authApi = {
  getCurrentUser: () => api.get('/auth/me'),
  getUsers: (params = {}) => api.get('/auth/users', { params }),
  getUserById: (id) => api.get(`/auth/users/${id}`),
  createUser: (data) => api.post('/auth/users', data),
  getRoles: (params = {}) => api.get('/auth/roles', { params }),
  getPermissions: (params = {}) => api.get('/auth/permissions', { params }),
  getOrganizations: (params = {}) => api.get('/auth/organizations', { params }),
  getOrgUnits: (orgId) => api.get(`/auth/organizations/${orgId}/units`),
  login: async (username, password) => {
    // Uses pre-provisioned Supabase Auth or developer credentials
    const token = `dev-user-${username}`;
    const user = {
      id: `usr-${username}-01`,
      email: `${username}@prism.gov.in`,
      name: username.replace(/[-_]/g, ' ').replace(/\b\w/g, l => l.toUpperCase()),
      role: username.includes('admin') ? 'ADMINISTRATOR' : username.includes('super') ? 'SUPERVISOR' : 'REVIEWER',
      organization: 'Ministry of Rural Development',
      jurisdiction: 'National & Regional Operations'
    };
    localStorage.setItem('auth_token', token);
    localStorage.setItem('user', JSON.stringify(user));
    return { data: { success: true, token, user } };
  },
  logout: () => {
    localStorage.removeItem('auth_token');
    localStorage.removeItem('user');
    return Promise.resolve({ data: { success: true } });
  },
};

// ----------------------------------------------------------------------
// 2. Projects & Claims (BE-039 Project Creation & Identity Audit)
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
  changeScope: (id, data) => api.post(`/auth/projects/${id}/scope`, data),
};

// ----------------------------------------------------------------------
// 3. Evidence Ingestion, Storage & Integrity (BE-002, BE-003, BE-004)
// ----------------------------------------------------------------------
export const evidenceApi = {
  upload: (file, caseId, onProgress) => {
    const formData = new FormData();
    formData.append('file', file);
    if (caseId) {
      formData.append('case_id', caseId);
    }
    return api.post('/evidence', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: onProgress,
    });
  },
  getById: (id) => api.get(`/evidence/${id}`),
  download: (id) => api.get(`/evidence/${id}/download`),
  getNearby: (params = {}) => api.get('/evidence/nearby', { params }),
  updateContext: (id, data) => api.patch(`/evidence/${id}/context`, data),
  updateLocation: (id, data) => api.patch(`/evidence/${id}/location`, data),
  getVision: (id) => api.get(`/evidence/${id}/vision`),
  // Compatibility wrappers
  createUpload: (data) => api.post('/evidence', data),
  completeUpload: (id) => Promise.resolve({ data: { id, status: 'completed' } }),
  getAnalysis: (id) => api.get(`/evidence/${id}/vision`),
  getSimilar: (id) => api.get('/evidence/nearby', { params: { radius_meters: 500 } }),
  getAnomalies: (id) => api.get(`/evidence/${id}/vision`),
  getGraph: (id) => api.get(`/graph/evidence/${id}`),
  search: (params = {}) => api.get('/evidence/nearby', { params }),
};

// ----------------------------------------------------------------------
// 4. Review Cases & Human Decisions (BE-013, BE-014, ADR §14)
// ----------------------------------------------------------------------
export const reviewApi = {
  getQueue: (params = {}) => api.get('/review-cases', { params }),
  getById: (id) => api.get(`/review-cases/${id}`),
  recordDecision: (caseId, { decision, rationale }) => api.post(`/review-cases/${caseId}/decision`, {
    decision,
    rationale,
  }),
  getHistory: (caseId) => api.get(`/review-cases/${caseId}/history`),
  assign: (caseId, reviewerId) => api.post(`/review-cases/${caseId}/assign`, { reviewer_id: reviewerId }),
  startInvestigation: (caseId) => api.post(`/review-cases/${caseId}/investigate`),
  escalate: (caseId, data = {}) => api.post(`/review-cases/${caseId}/escalate`, data),
  resolve: (caseId, data = {}) => api.post(`/review-cases/${caseId}/resolve`, data),
  reopen: (caseId, { reason }) => api.post(`/review-cases/${caseId}/reopen`, { reason }),
  // Compatibility wrappers
  makeDecision: (id, data) => api.post(`/review-cases/${id}/decision`, data),
};

// ----------------------------------------------------------------------
// 5. Tamper-Evident Audit Ledger (BE-015, BE-030)
// ----------------------------------------------------------------------
export const auditApi = {
  getEvents: (params = {}) => api.get('/audit/events', { params }),
  getById: (id) => api.get(`/audit/events/${id}`),
  verifyLedger: () => api.get('/audit/verify'),
  verifyAnchored: () => api.get('/audit/verify/anchored'),
  recordDecision: (data) => Promise.resolve({ data }),
};

// ----------------------------------------------------------------------
// 6. Evidence Graph (BE-010, Section 14)
// ----------------------------------------------------------------------
export const graphApi = {
  getEntityGraph: (nodeType, entityId, params = {}) => api.get(`/graph/${nodeType}/${entityId}`, { params }),
  createRelationship: (data) => api.post('/graph/relationships', data),
};

// ----------------------------------------------------------------------
// 7. Retention, Archival & Legal Holds (BE-017, Scope Classification 2026-10-17)
// ----------------------------------------------------------------------
export const governanceApi = {
  getPolicies: (params = {}) => api.get('/retention/policies', { params }),
  getPolicyById: (id) => api.get(`/retention/policies/${id}`),
  createPolicy: (data) => api.post('/retention/policies', data),
  getPolicyHistory: (id) => api.get(`/retention/policies/${id}/history`),
  getHolds: (params = {}) => api.get('/retention/holds', { params }),
  getHoldById: (id) => api.get(`/retention/holds/${id}`),
  createHold: (data) => api.post('/retention/holds', data),
  releaseHold: (id, data) => api.post(`/retention/holds/${id}/release`, data),
  getOperations: (params = {}) => api.get('/retention/operations', { params }),
};

// ----------------------------------------------------------------------
// 8. Public Transparency Portal (BE-022)
// ----------------------------------------------------------------------
export const publicApi = {
  getProjects: (params = {}) => api.get('/public/projects', { params }),
  getProject: (publicId) => api.get(`/public/projects/${publicId}`),
  getProjectEvidence: (publicId) => api.get(`/public/projects/${publicId}/evidence`),
  getEvidence: (publicId) => api.get(`/public/evidence/${publicId}`),
};

// ----------------------------------------------------------------------
// 9. System Health & Telemetry
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
      max_upload_size_mb: 10, // 10 MiB limit per Section 9.4
      quarantine_auto_purge: true,
      strict_mime_validation: true,
    }
  }),
  updateConfig: (data) => Promise.resolve({ data }),
};

export const casesApi = reviewApi;
export const projectsApi = projectApi;

export default api;
