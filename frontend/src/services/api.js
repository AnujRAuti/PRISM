// Single authenticated HTTP client for the FastAPI application.
import axios from 'axios';
import { getAccessToken, supabase } from '../lib/supabase/client';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1';
const API_ROOT_URL = API_BASE_URL.replace(/\/api\/v1\/?$/, '') || '/';

export const api = axios.create({
  baseURL: API_BASE_URL.replace(/\/$/, ''),
  timeout: 30000,
  headers: { Accept: 'application/json' },
});

export const operationsApi = axios.create({
  baseURL: API_ROOT_URL,
  timeout: 30000,
  headers: { Accept: 'application/json' },
});

const clients = [api, operationsApi];
for (const client of clients) {
  client.interceptors.request.use(async (config) => {
    const token = await getAccessToken();
    if (token) config.headers.Authorization = `Bearer ${token}`;
    if (typeof FormData !== 'undefined' && config.data instanceof FormData) {
      delete config.headers['Content-Type']; // Let the browser add the multipart boundary.
    }
    return config;
  });
  client.interceptors.response.use(
    (response) => response,
    async (error) => {
      if (error.response?.status === 401) {
        if (supabase) await supabase.auth.signOut().catch(() => {});
        for (const key of ['auth_token', 'user', 'eiil_current_user']) localStorage.removeItem(key);
        if (typeof window !== 'undefined' && !window.location.pathname.startsWith('/login') && !window.location.pathname.startsWith('/public')) {
          window.location.href = '/login';
        }
      }
      return Promise.reject(error);
    },
  );
}

const query = (params) => ({ params });

export const authApi = {
  logout: async () => {
    if (supabase) await supabase.auth.signOut().catch(() => {});
    for (const key of ['auth_token', 'user', 'eiil_current_user']) localStorage.removeItem(key);
  },
  getCurrentUser: () => api.get('/auth/me'),
  getUsers: (params = {}) => api.get('/auth/users', query(params)),
  getUserById: (id) => api.get(`/auth/users/${id}`),
  createUser: (data) => api.post('/auth/users', data),
  updateUserStatus: (id, data) => api.patch(`/auth/users/${id}/status`, data),
  getRoles: (params = {}) => api.get('/auth/roles', query(params)),
  getPermissions: (params = {}) => api.get('/auth/permissions', query(params)),
  getOrganizations: (params = {}) => api.get('/auth/organizations', query(params)),
  createOrganization: (data) => api.post('/auth/organizations', data),
  getOrganizationUnits: (id, params = {}) => api.get(`/auth/organizations/${id}/units`, query(params)),
  createOrganizationUnit: (id, data) => api.post(`/auth/organizations/${id}/units`, data),
  assignRole: (id, data) => api.post(`/auth/users/${id}/roles`, data),
  getRoleAssignments: (id, params = {}) => api.get(`/auth/users/${id}/roles`, query(params)),
  revokeRole: (id, assignmentId) => api.delete(`/auth/users/${id}/roles/${assignmentId}`),
  createApiClient: (data) => api.post('/auth/clients', data),
  updateProjectScope: (id, data) => api.patch(`/auth/projects/${id}/scope`, data),
  transferProjectOwnership: (id, data) => api.post(`/auth/projects/${id}/ownership`, data),
};

export const projectApi = {
  getAll: (params = {}) => api.get('/projects', query(params)),
  getById: (id) => api.get(`/projects/${id}`),
  create: (data) => api.post('/projects', data),
  update: (id, data) => api.patch(`/projects/${id}`, data),
  getActivities: (id, params = {}) => api.get(`/projects/${id}/activities`, query(params)),
  getActivity: (projectId, activityId) => api.get(`/projects/${projectId}/activities/${activityId}`),
  createActivity: (id, data) => api.post(`/projects/${id}/activities`, data),
  getClaims: (id, params = {}) => api.get(`/projects/${id}/claims`, query(params)),
  createClaim: (id, data) => api.post(`/projects/${id}/claims`, data),
  getClaim: (projectId, claimId) => api.get(`/projects/${projectId}/claims/${claimId}`),
  updateClaim: (projectId, claimId, data) => api.patch(`/projects/${projectId}/claims/${claimId}`, data),
  transferOwnership: (id, data) => authApi.transferProjectOwnership(id, data),
  changeScope: (id, data) => authApi.updateProjectScope(id, data),
};

export const evidenceApi = {
  list: (params = {}) => api.get('/evidence', query(params)),
  upload: (file, _caseId, onProgress) => {
    const body = new FormData();
    body.append('file', file);
    return api.post('/evidence', body, { onUploadProgress: onProgress });
  },
  getById: (id) => api.get(`/evidence/${id}`),
  download: (id) => api.get(`/evidence/${id}/download`),
  getNearby: (params = {}) => api.get('/evidence/nearby', query(params)),
  getProjectNearby: (projectId, params = {}) => api.get(`/projects/${projectId}/evidence/nearby`, query(params)),
  updateContext: (id, data) => api.patch(`/evidence/${id}/context`, data),
  updateLocation: (id, data) => api.patch(`/evidence/${id}/location`, data),
  getVision: (id) => api.get(`/evidence/${id}/vision`),
  createAnalysisJob: (data) => api.post('/analysis/jobs', data),
  getAnalysisJob: (id) => api.get(`/analysis/jobs/${id}`),
  runTemporalAnalysis: (id, data) => api.post(`/analysis/temporal/${id}`, data),
};

export const reviewApi = {
  getQueue: (params = {}) => api.get('/review-cases', query(params)),
  getById: (id) => api.get(`/review-cases/${id}`),
  getHistory: (id) => api.get(`/review-cases/${id}/history`),
  generateFromFusion: (id, data = {}) => api.post(`/review-cases/from-fusion/${id}`, data),
  assign: (id, assignedTo) => api.post(`/review-cases/${id}/assign`, { assigned_to: assignedTo }),
  startInvestigation: (id) => api.post(`/review-cases/${id}/investigate`),
  recordDecision: (id, data) => api.post(`/review-cases/${id}/decision`, data),
  escalate: (id, data) => api.post(`/review-cases/${id}/escalate`, data),
  resolve: (id, data = {}) => api.post(`/review-cases/${id}/resolve`, data),
  reopen: (id, data) => api.post(`/review-cases/${id}/reopen`, data),
};

export const auditApi = {
  getEvents: (params = {}) => api.get('/audit/events', query(params)),
  getById: (id) => api.get(`/audit/events/${id}`),
  verifyLedger: (params = {}) => api.get('/audit/verify', query(params)),
  verifyAnchored: (params = {}) => api.get('/audit/verify/anchored', query(params)),
};

export const graphApi = {
  getEntityGraph: (type, id, params = {}) => api.get(`/graph/${type}/${id}`, query(params)),
  createRelationship: (data) => api.post('/graph/relationships', data),
  updateRelationship: (id, data) => api.patch(`/graph/relationships/${id}`, data),
};

export const fusionApi = {
  execute: (type, id, data = {}) => api.post(`/fusion/${type}/${id}`, data),
  latest: (type, id) => api.get(`/fusion/${type}/${id}`),
  getRun: (id) => api.get(`/fusion/runs/${id}`),
  getHistory: (type, id, params = {}) => api.get(`/fusion/${type}/${id}/history`, query(params)),
  createConfiguration: (data) => api.post('/fusion/configurations', data),
};

export const explanationApi = {
  getForRun: (id) => api.get(`/explanations/fusion/${id}`),
  materializeForRun: (id, data = {}) => api.post(`/explanations/fusion/${id}`, data),
  getForTarget: (type, id) => api.get(`/explanations/${type}/${id}`),
};

export const evidenceRequestApi = {
  list: (params = {}) => api.get('/evidence-requests', query(params)),
  get: (id) => api.get(`/evidence-requests/${id}`),
  history: (id) => api.get(`/evidence-requests/${id}/history`),
  create: (data) => api.post('/evidence-requests', data),
  issue: (id, data = {}) => api.post(`/evidence-requests/${id}/issue`, data),
  acknowledge: (id, data = {}) => api.post(`/evidence-requests/${id}/acknowledge`, data),
  linkEvidence: (id, evidenceId, data = {}) => api.post(`/evidence-requests/${id}/evidence/${evidenceId}`, data),
  submitEvidence: (id, data) => api.post(`/evidence-requests/${id}/submissions`, data),
  acceptItem: (id, itemId, data = {}) => api.post(`/evidence-requests/${id}/items/${itemId}/accept`, data),
  rejectItem: (id, itemId, data) => api.post(`/evidence-requests/${id}/items/${itemId}/reject`, data),
  decline: (id, data) => api.post(`/evidence-requests/${id}/decline`, data),
  cancel: (id, data = {}) => api.post(`/evidence-requests/${id}/cancel`, data),
  expire: (id, data) => api.post(`/evidence-requests/${id}/expire`, data),
};

export const retentionApi = {
  getPolicies: (params = {}) => api.get('/retention/policies', query(params)),
  getPolicy: (id) => api.get(`/retention/policies/${id}`),
  createPolicy: (data) => api.post('/retention/policies', data),
  createPolicyVersion: (id, data) => api.post(`/retention/policies/${id}/versions`, data),
  getPolicyHistory: (id) => api.get(`/retention/policies/${id}/history`),
  activatePolicyVersion: (id, data = {}) => api.post(`/retention/policies/versions/${id}/activate`, data),
  evaluate: (data) => api.post('/retention/evaluate', data),
  getResourceState: (type, id) => api.get(`/retention/resources/${type}/${id}`),
  getHolds: (params = {}) => api.get('/retention/holds', query(params)),
  getHold: (id) => api.get(`/retention/holds/${id}`),
  createHold: (data) => api.post('/retention/holds', data),
  releaseHold: (id, data) => api.post(`/retention/holds/${id}/release`, data),
  cancelHold: (id, data) => api.post(`/retention/holds/${id}/cancel`, data),
  archive: (type, id, data = {}) => api.post(`/retention/archive/${type}/${id}`, data),
  restore: (type, id, data) => api.post(`/retention/restore/${type}/${id}`, data),
  delete: (type, id, data) => api.post(`/retention/delete/${type}/${id}`, data),
  getOperations: (params = {}) => api.get('/retention/operations', query(params)),
};

export const notificationApi = {
  list: (params = {}) => api.get('/notifications', query(params)),
  unreadCount: () => api.get('/notifications/unread-count'),
  get: (id) => api.get(`/notifications/${id}`),
  getPreferences: () => api.get('/notifications/preferences'),
  updatePreferences: (data) => api.patch('/notifications/preferences', data),
  markRead: (id) => api.post(`/notifications/${id}/read`),
  markAllRead: () => api.post('/notifications/read-all'),
  deliveries: (id, params = {}) => api.get(`/notifications/${id}/deliveries`, query(params)),
};

export const integrationApi = {
  systems: (params = {}) => api.get('/integrations/systems', query(params)),
  registerSystem: (data) => api.post('/integrations/systems', data),
  clients: (params = {}) => api.get('/integrations/clients', query(params)),
  createClient: (data) => api.post('/integrations/clients', data),
  getClient: (id) => api.get(`/integrations/clients/${id}`),
  issueCredential: (id, data = {}) => api.post(`/integrations/clients/${id}/credentials`, data),
  revokeCredential: (id, data = {}) => api.post(`/integrations/credentials/${id}/revoke`, data),
  references: (params = {}) => api.get('/integrations/references', query(params)),
  mapReference: (data) => api.post('/integrations/references', data),
  ingestEvidence: (data) => api.post('/integrations/evidence', data),
  importClaim: (data) => api.post('/integrations/claims', data),
  webhooks: (params = {}) => api.get('/integrations/webhooks', query(params)),
  createWebhook: (data) => api.post('/integrations/webhooks', data),
  updateWebhook: (id, data) => api.patch(`/integrations/webhooks/${id}`, data),
  events: (params = {}) => api.get('/integrations/events', query(params)),
};

export const disputeApi = {
  list: (params = {}) => api.get('/disputes', query(params)),
  get: (id) => api.get(`/disputes/${id}`),
  history: (id) => api.get(`/disputes/${id}/history`),
  create: (data) => api.post('/disputes', data),
  startReview: (id, data = {}) => api.post(`/disputes/${id}/start-review`, data),
  assign: (id, data) => api.post(`/disputes/${id}/assign`, data),
  escalate: (id, data) => api.post(`/disputes/${id}/escalate`, data),
  resolve: (id, data) => api.post(`/disputes/${id}/resolve`, data),
  reject: (id, data) => api.post(`/disputes/${id}/reject`, data),
  withdraw: (id, data = {}) => api.post(`/disputes/${id}/withdraw`, data),
};

export const correctionApi = {
  list: (params = {}) => api.get('/corrections', query(params)),
  get: (id) => api.get(`/corrections/${id}`),
  history: (id) => api.get(`/corrections/${id}/history`),
  create: (data) => api.post('/corrections', data),
  startReview: (id, data = {}) => api.post(`/corrections/${id}/start-review`, data),
  approve: (id, data) => api.post(`/corrections/${id}/approve`, data),
  reject: (id, data) => api.post(`/corrections/${id}/reject`, data),
  apply: (id, data = {}) => api.post(`/corrections/${id}/apply`, data),
  cancel: (id, data = {}) => api.post(`/corrections/${id}/cancel`, data),
};

export const intelligenceGovernanceApi = {
  dependencies: (type, id) => api.get(`/governance/${type}/${id}/dependencies`),
  invalidate: (type, id, data) => api.post(`/governance/${type}/${id}/invalidate`, data),
  getInvalidation: (id) => api.get(`/governance/invalidations/${id}`),
  reprocess: (type, id, data = {}) => api.post(`/governance/${type}/${id}/reprocess`, data),
};

export const publicationApi = {
  list: (params = {}) => api.get('/publications', query(params)),
  create: (data) => api.post('/publications', data),
  get: (id) => api.get(`/publications/${id}`),
  eligibility: (id) => api.get(`/publications/${id}/eligibility`),
  submitReview: (id, data = {}) => api.post(`/publications/${id}/submit-review`, data),
  approve: (id, data = {}) => api.post(`/publications/${id}/approve`, data),
  reject: (id, data) => api.post(`/publications/${id}/reject`, data),
  publish: (id, data = {}) => api.post(`/publications/${id}/publish`, data),
  unpublish: (id, data) => api.post(`/publications/${id}/unpublish`, data),
  getPolicies: (params = {}) => api.get('/publications/policies', query(params)),
  createPolicy: (data) => api.post('/publications/policies', data),
  getPolicy: (id) => api.get(`/publications/policies/${id}`),
  publicProjects: (params = {}) => api.get('/public/projects', query(params)),
  publicProject: (id) => api.get(`/public/projects/${id}`),
  publicActivities: (id, params = {}) => api.get(`/public/projects/${id}/activities`, query(params)),
  publicClaims: (id, params = {}) => api.get(`/public/projects/${id}/claims`, query(params)),
  publicEvidence: (id, params = {}) => api.get(`/public/projects/${id}/evidence`, query(params)),
  publicEvidenceItem: (id) => api.get(`/public/evidence/${id}`),
  publicSnapshot: (id) => api.get(`/public/publications/${id}`),
};

export const fieldApi = {
  assignments: (params = {}) => api.get('/field/assignments', query(params)),
  createAssignment: (data) => api.post('/field/assignments', data),
  getAssignment: (id) => api.get(`/field/assignments/${id}`),
  updateAssignmentStatus: (id, data) => api.patch(`/field/assignments/${id}/status`, data),
  work: (params = {}) => api.get('/field/work', query(params)),
  openSession: (data) => api.post('/field/sessions', data),
  closeSession: (id, data = {}) => api.post(`/field/sessions/${id}/close`, data),
  syncCapture: (data) => api.post('/field/sync', data),
  getCapture: (id) => api.get(`/field/captures/${id}`),
  operations: (params = {}) => api.get('/field/operations', query(params)),
  resolveOperation: (id, data) => api.post(`/field/operations/${id}/resolve`, data),
};

export const adminApi = {
  getUsers: authApi.getUsers,
  createUser: authApi.createUser,
  getRoles: authApi.getRoles,
  getPermissions: authApi.getPermissions,
  getOrganizations: authApi.getOrganizations,
  getMetrics: () => operationsApi.get('/metrics'),
  getHealth: () => operationsApi.get('/health'),
  getReady: () => operationsApi.get('/ready'),
  getHealthSnapshot: () => operationsApi.get('/healthz'),
};

export const governanceApi = retentionApi;
export const publicApi = publicationApi;
export const casesApi = reviewApi;
export const projectsApi = projectApi;
export default api;
