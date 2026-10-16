import { createContext, useContext, useState, useEffect } from 'react';
import { supabase, isSupabaseConfigured } from '../lib/supabase/client';

const AuthContext = createContext();

// Default provisioned reviewer identity for local development fallback
const MOCK_REVIEWER = {
  id: 'usr-rev-001',
  username: 'reviewer_lead',
  name: 'Senior Reviewer (Operations)',
  email: 'reviewer@prism.gov.in',
  role: 'reviewer',
  permissions: ['cases.read', 'evidence.read', 'evidence.upload', 'decisions.create'],
  created_at: new Date().toISOString()
};

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let subscription = null;

    if (isSupabaseConfigured && supabase) {
      // 1. Initial Supabase session check
      supabase.auth.getSession().then(({ data: { session } }) => {
        if (session?.user) {
          mapAndSetUser(session.user);
        } else {
          setUser(null);
        }
        setLoading(false);
      });

      // 2. Listen to Supabase auth state changes
      const { data } = supabase.auth.onAuthStateChange((_event, session) => {
        if (session?.user) {
          mapAndSetUser(session.user);
        } else {
          setUser(null);
        }
        setLoading(false);
      });
      subscription = data.subscription;
    } else {
      // Local fallback check
      const stored = localStorage.getItem('user');
      if (stored) {
        try {
          setUser(JSON.parse(stored));
        } catch {
          localStorage.removeItem('user');
          localStorage.removeItem('auth_token');
        }
      }
      setLoading(false);
    }

    return () => {
      if (subscription) subscription.unsubscribe();
    };
  }, []);

  const mapAndSetUser = (sbUser) => {
    const formatted = {
      id: sbUser.id,
      email: sbUser.email,
      name: sbUser.user_metadata?.full_name || sbUser.email?.split('@')[0] || 'Reviewer',
      role: sbUser.app_metadata?.role || sbUser.user_metadata?.role || 'reviewer',
      permissions: ['cases.read', 'evidence.read', 'evidence.upload', 'decisions.create'],
    };
    setUser(formatted);
    localStorage.setItem('user', JSON.stringify(formatted));
  };

  /**
   * Sign In using provisioned credentials
   * (Section 3.1: No public signup, no role selector)
   */
  const login = async (emailOrUsername, password) => {
    setError(null);

    // If Supabase is connected in production/staging
    if (isSupabaseConfigured && supabase) {
      try {
        const { data, error: sbError } = await supabase.auth.signInWithPassword({
          email: emailOrUsername,
          password: password,
        });

        if (sbError) {
          const msg = sbError.message || 'Invalid credentials or account suspended.';
          setError(msg);
          return { success: false, message: msg };
        }

        if (data.user) {
          mapAndSetUser(data.user);
          return { success: true };
        }
      } catch (err) {
        const msg = 'Authentication service unavailable. Please verify network connectivity.';
        setError(msg);
        return { success: false, message: msg };
      }
    }

    // Local development fallback
    return new Promise((resolve) => {
      setTimeout(() => {
        if (emailOrUsername && emailOrUsername.length >= 3 && password) {
          const localUser = {
            ...MOCK_REVIEWER,
            email: emailOrUsername.includes('@') ? emailOrUsername : `${emailOrUsername}@prism.gov.in`,
            name: emailOrUsername.split('@')[0],
          };
          const mockToken = 'mock-jwt-token-' + Math.random().toString(36).substring(2);
          localStorage.setItem('auth_token', mockToken);
          localStorage.setItem('user', JSON.stringify(localUser));
          setUser(localUser);
          resolve({ success: true });
        } else {
          const msg = 'Invalid credentials. Please provide valid authorized reviewer credentials.';
          setError(msg);
          resolve({ success: false, message: msg });
        }
      }, 250);
    });
  };

  const logout = async () => {
    if (isSupabaseConfigured && supabase) {
      await supabase.auth.signOut();
    }
    localStorage.removeItem('auth_token');
    localStorage.removeItem('user');
    setUser(null);
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
