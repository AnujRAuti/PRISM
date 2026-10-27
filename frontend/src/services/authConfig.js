// Where the reviewer's sign-in provider lives. Values come from Vite's env files:
// the project URL is public and may be committed, the publishable key is not and
// belongs in frontend/.env.local (gitignored by `*.local`).
export const REQUIRED_KEYS = ['VITE_SUPABASE_URL', 'VITE_SUPABASE_PUBLISHABLE_KEY'];

export function readSupabaseConfig(env = {}) {
  const values = {
    VITE_SUPABASE_URL: (env.VITE_SUPABASE_URL || '').trim(),
    VITE_SUPABASE_PUBLISHABLE_KEY: (env.VITE_SUPABASE_PUBLISHABLE_KEY || '').trim(),
  };
  const missing = REQUIRED_KEYS.filter((key) => !values[key]);
  return {
    url: values.VITE_SUPABASE_URL,
    publishableKey: values.VITE_SUPABASE_PUBLISHABLE_KEY,
    missing,
    // A client-side credential is expected in the browser; what is not acceptable
    // is falling back to an invented identity when it is absent.
    ready: missing.length === 0,
  };
}
