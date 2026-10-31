import { getAccessToken, supabase } from '../supabase/client';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export class ApiError extends Error {
  constructor(category, message, status = 0, details = null) {
    super(message);
    this.name = 'ApiError';
    this.category = category;
    this.status = status;
    this.details = details;
  }
}

/**
 * Normalizes HTTP status codes to PoA PWA normalized categories
 */
function normalizeError(status, data) {
  const message = data?.detail || data?.message || 'An API error occurred';
  switch (status) {
    case 401:
      return new ApiError('UNAUTHENTICATED', 'Your session has expired or authentication failed. Please sign in.', status, data);
    case 403:
      return new ApiError('FORBIDDEN', 'Access forbidden. You do not have permissions for this case or project.', status, data);
    case 404:
      return new ApiError('NOT_FOUND', 'The requested resource was not found.', status, data);
    case 409:
      return new ApiError('CONFLICT', message || 'Conflict with current server state.', status, data);
    case 422:
      return new ApiError('VALIDATION_ERROR', message || 'Submitted data failed schema validation.', status, data);
    case 429:
      return new ApiError('RATE_LIMITED', 'Too many requests. Please slow down and try again.', status, data);
    case 502:
    case 503:
    case 504:
      return new ApiError('SERVICE_UNAVAILABLE', 'Backend verification service is currently unreachable.', status, data);
    default:
      return new ApiError('UNKNOWN', message, status, data);
  }
}

/**
 * Centralized fetch wrapper
 */
export async function apiClient(endpoint, options = {}, schema = null, isRetry = false) {
  const url = endpoint.startsWith('http') ? endpoint : `${API_BASE_URL}${endpoint}`;
  
  const headers = {
    'Accept': 'application/json',
    ...options.headers,
  };

  // Only set Content-Type if not sending FormData
  if (!(options.body instanceof FormData) && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json';
  }

  // Attach Supabase access token if available
  const token = await getAccessToken();
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  try {
    const response = await fetch(url, {
      ...options,
      headers,
    });

    // Handle 401 with ONE-TIME token refresh
    if (response.status === 401 && !isRetry && supabase) {
      const { data, error } = await supabase.auth.refreshSession();
      if (!error && data?.session?.access_token) {
        return apiClient(endpoint, options, schema, true);
      }
    }

    if (!response.ok) {
      let errorBody = null;
      try {
        errorBody = await response.json();
      } catch {
        errorBody = null;
      }
      throw normalizeError(response.status, errorBody);
    }

    // 204 No Content
    if (response.status === 204) {
      return null;
    }

    const json = await response.json();

    // Runtime validation with Zod if schema provided
    if (schema) {
      const parseResult = schema.safeParse(json);
      if (!parseResult.success) {
        console.warn('[Zod Validation Warning]', parseResult.error);
        throw new ApiError('VALIDATION_ERROR', 'Server response failed schema validation', response.status, parseResult.error.format());
      }
      return parseResult.data;
    }

    return json;
  } catch (err) {
    if (err instanceof ApiError) {
      throw err;
    }
    // Network failures / fetch rejections
    throw new ApiError('SERVICE_UNAVAILABLE', 'Unable to reach the server. Check your connection.', 0, err);
  }
}
