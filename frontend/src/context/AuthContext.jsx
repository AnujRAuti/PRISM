import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { authApi } from '../services/api';
import { getSupabaseClient } from '../services/supabaseClient';
import { onSessionChange, signOut } from '../services/authSession';

const AuthContext = createContext();

// The identity this app shows is the identity the backend confirmed: a token from
// Supabase, verified by the API, mapped onto a linked PoA account with its own
// roles and permissions. There is deliberately no placeholder principal here — if
// /auth/me refuses, nobody is signed in.
function principalToUser(principal, sessionUser) {
  const email = sessionUser?.email || null;
  return {
    id: principal.id,
    username: email ? email.split('@')[0] : (principal.display_name || 'Reviewer'),
    name: principal.display_name || email || 'Reviewer',
    email,
    role: (principal.roles && principal.roles[0]) ? String(principal.roles[0]).toLowerCase() : '',
    roles: principal.roles || [],
    permissions: principal.permissions || [],
    scopes: principal.scopes || [],
    organization_ids: principal.organization_ids || [],
    status: principal.status,
  };
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const loadPrincipal = useCallback(async (knownSession) => {
    const response = await authApi.getCurrentUser();
    const principal = response.data;
    if (!principal || !principal.authenticated) {
      throw new Error('This sign-in is not linked to an account on this backend.');
    }
    const supabase = getSupabaseClient();
    const session = knownSession
      ?? (supabase ? (await supabase.auth.getSession()).data?.session : null);
    setUser(principalToUser(principal, session?.user));
  }, []);

  useEffect(() => {
    // Any principal cached by the old mock login is removed on load: a stored
    // object is not proof that anyone is signed in.
    localStorage.removeItem('auth_token');
    localStorage.removeItem('user');

    const supabase = getSupabaseClient();
    if (!supabase) {
      setLoading(false);
      return undefined;
    }

    let active = true;
    supabase.auth.getSession().then(({ data }) => {
      if (!active) return;
      if (!data?.session) {
        setLoading(false);
        return;
      }
      loadPrincipal(data.session)
        .catch((err) => {
          setUser(null);
          setError(err.response?.data?.detail || err.message || 'Session check failed.');
        })
        .finally(() => {
          if (active) setLoading(false);
        });
    });

    const unsubscribe = onSessionChange(supabase, (session) => {
      if (!session) {
        setUser(null);
        return;
      }
      loadPrincipal(session).catch((err) => {
        setUser(null);
        setError(err.response?.data?.detail || err.message || 'Session check failed.');
      });
    });

    return () => {
      active = false;
      unsubscribe();
    };
  }, [loadPrincipal]);

  const login = async (email, password) => {
    setError(null);
    const result = await authApi.login(email, password);
    if (!result.success) {
      setError(result.message);
      return { success: false, message: result.message };
    }
    // The login call already proved /auth/me answers for this token.
    setUser(principalToUser(result.principal, { email: result.email }));
    return { success: true };
  };

  const logout = async () => {
    await signOut(getSupabaseClient());
    setUser(null);
    setError(null);
  };

  const value = {
    user,
    login,
    logout,
    loading,
    error,
    isAuthenticated: !!user,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}

export default AuthContext;
