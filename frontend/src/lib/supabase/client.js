import { createClient } from '@supabase/supabase-js';

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

// Verify Supabase configuration
export const isSupabaseConfigured = Boolean(
  supabaseUrl && 
  supabaseAnonKey && 
  !supabaseUrl.includes('placeholder')
);

/**
 * Official Supabase browser client instance.
 * Strictly used for authentication and session management only.
 * Business operations must NEVER query PostgreSQL directly from the browser.
 */
export const supabase = isSupabaseConfigured
  ? createClient(supabaseUrl, supabaseAnonKey, {
      auth: {
        autoRefreshToken: true,
        persistSession: true,
        detectSessionInUrl: true,
      },
    })
  : null;

/**
 * Retrieve current active access token for FastAPI Authorization: Bearer <token>
 */
export async function getAccessToken() {
  if (!supabase) {
    // Fallback token for local mock execution when Supabase keys are not yet provisioned
    return localStorage.getItem('auth_token') || null;
  }
  const { data: { session }, error } = await supabase.auth.getSession();
  if (error || !session) return null;
  return session.access_token;
}

/**
 * Retrieve active authenticated user
 */
export async function getCurrentUser() {
  if (!supabase) {
    const local = localStorage.getItem('user');
    return local ? JSON.parse(local) : null;
  }
  const { data: { user }, error } = await supabase.auth.getUser();
  if (error || !user) return null;
  return {
    id: user.id,
    email: user.email,
    name: user.user_metadata?.full_name || user.email?.split('@')[0] || 'Reviewer',
    role: user.app_metadata?.role || user.user_metadata?.role || 'reviewer',
  };
}
