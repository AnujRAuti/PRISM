import { createClient } from '@supabase/supabase-js';
import { readSupabaseConfig } from './authConfig';

let client = null;

// Null client means "nobody can sign in" — callers must never substitute an identity.
export function getSupabaseClient(env = import.meta.env || {}) {
  if (client) return client;
  const config = readSupabaseConfig(env);
  if (!config.ready) return null;
  client = createClient(config.url, config.publishableKey, {
    auth: {
      persistSession: true,
      autoRefreshToken: true,
      detectSessionInUrl: false,
      storageKey: 'poa-supabase-session',
    },
  });
  return client;
}

export function supabaseConfigError(env = import.meta.env || {}) {
  if (client) return null;
  const config = readSupabaseConfig(env);
  return config.ready
    ? null
    : `Sign-in is not configured: missing ${config.missing.join(', ')}.`;
}

/** Test hook: drop the cached client so a suite can inject a fake env. */
export function resetSupabaseClient() {
  client = null;
}
