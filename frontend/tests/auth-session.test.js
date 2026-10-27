import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { readSupabaseConfig } from '../src/services/authConfig.js';
import {
  currentAccessToken,
  decodeJwtClaims,
  describeSignInError,
  onSessionChange,
  signIn,
  tokenNeedsRefresh,
  TOKEN_SKEW_SECONDS,
} from '../src/services/authSession.js';

const SRC_DIR = join(fileURLToPath(new URL('.', import.meta.url)), '..', 'src');

const b64url = (value) => Buffer.from(JSON.stringify(value)).toString('base64url');
const mintToken = (claims) => `${b64url({ alg: 'ES256', typ: 'JWT', kid: 'k1' })}.${b64url(claims)}.signature`;

function fakeSupabase({ session = null, refreshed = null } = {}) {
  const calls = { getSession: 0, refreshSession: 0, signOut: 0 };
  return {
    calls,
    auth: {
      getSession: async () => { calls.getSession += 1; return { data: { session } }; },
      refreshSession: async () => { calls.refreshSession += 1; return { data: { session: refreshed } }; },
      signOut: async () => { calls.signOut += 1; },
      signInWithPassword: async () => ({ data: { session }, error: null }),
      onAuthStateChange: (cb) => {
        cb('SIGNED_IN', session);
        return { data: { subscription: { unsubscribe() {} } } };
      },
    },
  };
}

describe('Supabase config gate', () => {
  test('names every missing key instead of half-configuring a client', () => {
    const config = readSupabaseConfig({});
    assert.equal(config.ready, false);
    assert.deepEqual(config.missing.sort(), ['VITE_SUPABASE_PUBLISHABLE_KEY', 'VITE_SUPABASE_URL']);
  });

  test('a url without a publishable key is not ready', () => {
    const config = readSupabaseConfig({ VITE_SUPABASE_URL: 'https://example.supabase.co' });
    assert.equal(config.ready, false);
    assert.deepEqual(config.missing, ['VITE_SUPABASE_PUBLISHABLE_KEY']);
  });

  test('both keys present makes the config ready', () => {
    const config = readSupabaseConfig({
      VITE_SUPABASE_URL: 'https://example.supabase.co',
      VITE_SUPABASE_PUBLISHABLE_KEY: 'sb_publishable_abc',
    });
    assert.equal(config.ready, true);
    assert.equal(config.url, 'https://example.supabase.co');
    assert.equal(config.publishableKey, 'sb_publishable_abc');
  });
});

describe('JWT claim decoding', () => {
  test('reads the payload of a base64url ES256 token', () => {
    const claims = decodeJwtClaims(mintToken({ sub: ' reviewer-uuid ', exp: 123 }));
    assert.equal(claims.sub, ' reviewer-uuid ');
    assert.equal(claims.exp, 123);
  });

  test('refuses to invent claims from a non-token', () => {
    assert.equal(decodeJwtClaims('not-a-jwt'), null);
    assert.equal(decodeJwtClaims(null), null);
    assert.equal(decodeJwtClaims('a.b.##bad##'), null);
  });
});

describe('Token freshness', () => {
  const now = 1_000_000;

  test('a token inside the skew window must be refreshed before it is sent', () => {
    assert.equal(tokenNeedsRefresh({ exp: now + TOKEN_SKEW_SECONDS - 1 }, now), true);
  });

  test('a token with time to spare is sent as-is', () => {
    assert.equal(tokenNeedsRefresh({ exp: now + 3600 }, now), false);
  });

  test('an exp-less token is not treated as expired', () => {
    assert.equal(tokenNeedsRefresh({ sub: 'x' }, now), false);
    assert.equal(tokenNeedsRefresh(null, now), false);
  });
});

describe('currentAccessToken', () => {
  const now = 1_000_000;

  test('returns the stored token untouched while it is still valid', async () => {
    const token = mintToken({ exp: now + 3600 });
    const client = fakeSupabase({ session: { access_token: token } });
    assert.equal(await currentAccessToken(client, { nowSeconds: now }), token);
    assert.equal(client.calls.refreshSession, 0, 'must not refresh a valid token');
  });

  test('refreshes a token that would expire mid-request', async () => {
    const fresh = mintToken({ exp: now + 3600 });
    const client = fakeSupabase({
      session: { access_token: mintToken({ exp: now + 10 }) },
      refreshed: { access_token: fresh },
    });
    assert.equal(await currentAccessToken(client, { nowSeconds: now }), fresh);
    assert.equal(client.calls.refreshSession, 1);
    assert.equal(client.calls.signOut, 0);
  });

  test('a refresh that yields nothing ends the session instead of sending a doomed token', async () => {
    const client = fakeSupabase({
      session: { access_token: mintToken({ exp: now + 10 }) },
      refreshed: null,
    });
    assert.equal(await currentAccessToken(client, { nowSeconds: now }), null);
    assert.equal(client.calls.signOut, 1);
  });

  test('nobody signed in means no token, not a stand-in token', async () => {
    const client = fakeSupabase({ session: null });
    assert.equal(await currentAccessToken(client, { nowSeconds: now }), null);
    assert.equal(client.calls.refreshSession, 0);
  });

  test('an unconfigured provider gives no token', async () => {
    assert.equal(await currentAccessToken(null), null);
  });
});

describe('Sign-in refusal messages', () => {
  test('an unconfigured provider refuses rather than succeeding quietly', async () => {
    const result = await signIn(null, 'a@b.gov.in', 'pw');
    assert.equal(result.ok, false);
    assert.match(result.message, /not configured/i);
  });

  test('bad credentials are reported as bad credentials', () => {
    assert.match(describeSignInError(new Error('Invalid login credentials')),
      /Email or password is not correct/);
  });

  test('an unconfirmed reviewer account says what to do about it', () => {
    assert.match(describeSignInError(new Error('Email not confirmed')),
      /disable email confirmation/);
  });

  test('an unreachable provider is not reported as a wrong password', () => {
    assert.match(describeSignInError(new Error('Failed to fetch')), /Cannot reach the sign-in service/);
  });

  test('a provider sign-in error never returns a session', async () => {
    const client = fakeSupabase({ session: { access_token: 'x' } });
    client.auth.signInWithPassword = async () => ({ data: { session: null }, error: new Error('Invalid login credentials') });
    const result = await signIn(client, 'a@b.gov.in', 'pw');
    assert.equal(result.ok, false);
    assert.equal(result.session, undefined);
  });

  test('a successful provider sign-in hands back its session', async () => {
    const session = { access_token: mintToken({ exp: 2_000 }), user: { email: 'a@b.gov.in' } };
    const result = await signIn(fakeSupabase({ session }), 'a@b.gov.in', 'pw');
    assert.equal(result.ok, true);
    assert.equal(result.session, session);
  });
});

describe('Session subscription', () => {
  test('pushes the provider session to the handler and can unsubscribe', () => {
    const session = { access_token: 'x' };
    const seen = [];
    const unsubscribe = onSessionChange(fakeSupabase({ session }), (s) => seen.push(s));
    assert.deepEqual(seen, [session]);
    assert.equal(typeof unsubscribe, 'function');
    unsubscribe();
  });

  test('an unconfigured provider still returns a callable unsubscribe', () => {
    const unsubscribe = onSessionChange(null, () => { throw new Error('must not run'); });
    assert.equal(typeof unsubscribe, 'function');
    unsubscribe();
  });
});

// The mock login this repo shipped used to write a fabricated principal and a
// dev-user-/mock-token- bearer straight into localStorage. Those strings are the
// fingerprint of the old behaviour, so their absence is checked over the source.
describe('No fabricated identity survives in the frontend source', () => {
  const forbidden = [/dev-user-/, /mock-token-/, /MOCK_USER/];

  function* jsFiles(dir) {
    for (const entry of readdirSync(dir)) {
      const path = join(dir, entry);
      if (statSync(path).isDirectory()) yield* jsFiles(path);
      else if (entry.endsWith('.js') || entry.endsWith('.jsx')) yield path;
    }
  }

  test('no file reads or writes a token from localStorage', () => {
    for (const path of jsFiles(SRC_DIR)) {
      const source = readFileSync(path, 'utf8');
      for (const pattern of forbidden) {
        assert.equal(pattern.test(source), false,
          `${path} still contains the mock identity marker ${pattern}`);
      }
      assert.equal(/localStorage\.(getItem|setItem)\(\s*['"]auth_token/.test(source), false,
        `${path} still persists a bearer token in localStorage`);
    }
  });
});
