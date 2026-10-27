// The reviewer's real session: Supabase issues the token, this module hands the
// current, unexpired one to the API client, and maps provider failures into
// sentences an operator can act on. Nothing here ever fabricates an identity.

/** Refresh this far ahead of expiry so a request never races the expiry claim. */
export const TOKEN_SKEW_SECONDS = 60;

function decodeSegment(segment) {
  const padded = segment + '='.repeat((4 - (segment.length % 4)) % 4);
  const json = decodeURIComponent(
    atob(padded.replace(/-/g, '+').replace(/_/g, '/'))
      .split('')
      .map((byte) => `%${byte.charCodeAt(0).toString(16).padStart(2, '0')}`)
      .join('')
  );
  return JSON.parse(json);
}

/** Claims only — signature verification is the backend's job, never the browser's. */
export function decodeJwtClaims(token) {
  if (typeof token !== 'string' || token.split('.').length !== 3) return null;
  try {
    return decodeSegment(token.split('.')[1]);
  } catch {
    return null;
  }
}

export function tokenNeedsRefresh(claims, nowSeconds = Math.floor(Date.now() / 1000),
                                  skew = TOKEN_SKEW_SECONDS) {
  if (!claims || typeof claims.exp !== 'number') return false;
  return claims.exp - skew <= nowSeconds;
}

/**
 * The bearer token to send with the next request, refreshed when it is about to
 * expire. Null means "nobody is signed in", which the caller must not replace
 * with a stand-in token.
 */
export async function currentAccessToken(supabase, { nowSeconds, skew = TOKEN_SKEW_SECONDS } = {}) {
  if (!supabase) return null;
  const clock = nowSeconds ?? Math.floor(Date.now() / 1000);
  const stored = await supabase.auth.getSession();
  const token = stored.data?.session?.access_token;
  if (!token) return null;
  if (!tokenNeedsRefresh(decodeJwtClaims(token), clock, skew)) return token;

  const refreshed = await supabase.auth.refreshSession();
  const next = refreshed.data?.session?.access_token;
  if (!next) {
    // A refresh that yields nothing means the session is gone; say so by signing
    // out rather than sending a token the backend will refuse.
    await supabase.auth.signOut();
    return null;
  }
  return next;
}

export function describeSignInError(error) {
  const message = String(error?.message || error || '');
  if (/Invalid login credentials/i.test(message)) {
    return 'Email or password is not correct for this reviewer account.';
  }
  if (/Email not confirmed/i.test(message)) {
    return 'This reviewer account has not confirmed its email address yet. Check the inbox, '
      + 'or ask a project owner to disable email confirmation for the reviewer-auth project.';
  }
  if (/Failed to fetch|NetworkError|FetchError|Could not parse/i.test(message)) {
    return 'Cannot reach the sign-in service. Check that the Supabase project URL is correct '
      + 'and that this browser can reach it.';
  }
  if (/rate limit/i.test(message)) {
    return 'The sign-in service is rate limiting this browser. Wait a minute and try again.';
  }
  return message || 'Sign-in failed.';
}

export async function signIn(supabase, email, password) {
  if (!supabase) {
    return { ok: false, message: 'Sign-in is not configured for this deployment.' };
  }
  const { data, error } = await supabase.auth.signInWithPassword({ email, password });
  if (error) return { ok: false, message: describeSignInError(error) };
  return { ok: true, session: data.session };
}

export async function signOut(supabase) {
  if (!supabase) return;
  await supabase.auth.signOut();
}

/** Subscribe to the provider's own session events (sign-in, sign-out, token refresh). */
export function onSessionChange(supabase, handler) {
  if (!supabase) return () => {};
  const { data } = supabase.auth.onAuthStateChange((_event, session) => handler(session));
  return () => data.subscription.unsubscribe();
}
