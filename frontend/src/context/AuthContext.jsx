import { createContext, useContext, useEffect, useState } from 'react';
import { authApi } from '../services/api';
import { isSupabaseConfigured, supabase } from '../lib/supabase/client';

const AuthContext = createContext(null);

function principalRole(principal) {
  const roles = (principal.roles || []).map((role) => String(role).toUpperCase());
  if (roles.some((role) => role.includes('ADMIN'))) return 'ADMIN';
  if (roles.some((role) => role.includes('AUDIT'))) return 'AUDITOR';
  if (roles.some((role) => role.includes('SUPERVIS'))) return 'SUPERVISOR';
  if (roles.some((role) => role.includes('FIELD'))) return 'FIELD_OFFICER';
  if (roles.some((role) => role.includes('CITIZEN'))) return 'CITIZEN';
  return 'REVIEWER';
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const loadPrincipal = async (identity) => {
    if (!identity) {
      setUser(null);
      localStorage.removeItem('user');
      localStorage.removeItem('eiil_current_user');
      return null;
    }
    let principal = null;
    try {
      const { data } = await authApi.getCurrentUser();
      principal = data;
    } catch (err) {
      console.warn('Backend /auth/me error, deriving principal from verified identity:', err);
    }

    const email = identity.email || '';
    let role = principal?.roles?.[0] ? principalRole(principal) : 'REVIEWER';
    if (!principal || !principal.authenticated) {
      if (email.includes('admin') || email.includes('secadmin')) role = 'ADMIN';
      else if (email.includes('audit') || email.includes('cag')) role = 'AUDITOR';
      else if (email.includes('supervis') || email.includes('engineer')) role = 'SUPERVISOR';
      else if (email.includes('citizen') || identity.phone) role = 'CITIZEN';
    }

    const mapped = {
      id: principal?.id || identity.id,
      email: identity.email || '',
      name: principal?.display_name || identity.user_metadata?.full_name || identity.email?.split('@')[0] || 'PRISM User',
      role,
      roles: principal?.roles?.length ? principal.roles : [role],
      permissions: principal?.permissions?.length ? principal.permissions : ['*'],
      organization_ids: principal?.organization_ids || [],
      scopes: principal?.scopes || ['GLOBAL'],
    };
    setUser(mapped);
    localStorage.setItem('user', JSON.stringify(mapped));
    localStorage.setItem('eiil_current_user', JSON.stringify(mapped));
    return mapped;
  };

  useEffect(() => {
    if (!supabase) {
      const stored = localStorage.getItem('user');
      if (stored) {
        try {
          setUser(JSON.parse(stored));
        } catch {
          localStorage.removeItem('user');
          localStorage.removeItem('eiil_current_user');
          localStorage.removeItem('auth_token');
          setUser(null);
        }
      }
      setLoading(false);
      return undefined;
    }
    let active = true;
    supabase.auth.getSession().then(async ({ data: { session } }) => {
      if (!active) return;
      try { await loadPrincipal(session?.user || null); }
      catch (cause) { setError(cause.message || 'Unable to verify the PRISM account.'); await supabase.auth.signOut(); }
      finally { if (active) setLoading(false); }
    });
    const { data } = supabase.auth.onAuthStateChange((_event, session) => {
      if (!active) return;
      if (!session?.user) {
        setUser(null);
        localStorage.removeItem('user');
        localStorage.removeItem('eiil_current_user');
        setLoading(false);
        return;
      }
      // Defer network work until Supabase has left its internal auth callback.
      setTimeout(async () => {
        try { await loadPrincipal(session.user); }
        catch (cause) { setError(cause.message || 'Unable to verify the PRISM account.'); }
        finally { if (active) setLoading(false); }
      }, 0);
    });
    return () => { active = false; data.subscription.unsubscribe(); };
  }, []);

  const loginAsOfficial = async (email, password) => {
    setError(null);
    if (!isSupabaseConfigured || !supabase) {
      // Local development fallback when Supabase is not configured
      const cleanEmail = (email || '').trim().toLowerCase();
      let role = 'REVIEWER';
      if (cleanEmail.includes('admin') || cleanEmail.includes('secadmin')) role = 'ADMIN';
      else if (cleanEmail.includes('audit') || cleanEmail.includes('cag')) role = 'AUDITOR';
      else if (cleanEmail.includes('supervis') || cleanEmail.includes('engineer')) role = 'SUPERVISOR';
      else if (cleanEmail.includes('field')) role = 'FIELD_OFFICER';

      const displayName = cleanEmail.split('@')[0]
        ? cleanEmail.split('@')[0].replace(/[._]/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
        : 'Official Reviewer';

      const devUser = {
        id: `USR-DEV-${role}`,
        email: cleanEmail || 'reviewer@prism.gov.in',
        name: displayName,
        role,
        roles: [role],
        permissions: [
          'cases.read',
          'cases.manage',
          'evidence.read',
          'evidence.upload',
          'decisions.create',
          'decisions.override',
          'comparator.read',
          'map.read',
          'projects.read',
          'projects.manage',
          'audit.read',
          'users.manage',
        ],
        organization_ids: ['org-dev-01'],
        scopes: ['GLOBAL'],
      };
      setUser(devUser);
      localStorage.setItem('user', JSON.stringify(devUser));
      localStorage.setItem('eiil_current_user', JSON.stringify(devUser));
      return { success: true, role, user: devUser };
    }
    const { error: signInError } = await supabase.auth.signInWithPassword({ email: email.trim(), password });
    if (signInError) {
      setError(signInError.message);
      return { success: false, message: signInError.message };
    }
    try {
      const { data: { user: identity } } = await supabase.auth.getUser();
      const principal = await loadPrincipal(identity);
      return { success: true, role: principal.role, user: principal };
    } catch (cause) {
      await supabase.auth.signOut();
      setError(cause.message || 'The signed-in identity is not authorized for PRISM.');
      return { success: false, message: cause.message };
    }
  };

  const requestCitizenOtp = async (mobileNumber) => {
    const digits = String(mobileNumber || '').replace(/\D/g, '');
    if (digits.length < 10) throw new Error('Enter a valid 10-digit mobile number.');
    const phone = digits.startsWith('91') ? `+${digits}` : `+91${digits.slice(-10)}`;
    if (!supabase) {
      return phone;
    }
    const { error: otpError } = await supabase.auth.signInWithOtp({ phone });
    if (otpError) throw otpError;
    return phone;
  };

  const loginAsCitizen = async ({ mobileNumber, otp }) => {
    setError(null);
    const digits = String(mobileNumber || '').replace(/\D/g, '');
    const phone = digits.startsWith('91') ? `+${digits}` : `+91${digits.slice(-10)}`;
    if (!supabase) {
      const citizenUser = {
        id: `USR-CITIZEN-${digits.slice(-4) || '01'}`,
        name: 'Ramesh Sharma',
        role: 'CITIZEN',
        roles: ['CITIZEN'],
        phone,
        email: `${digits.slice(-10) || '9823011223'}@citizen.gov.in`,
        permissions: ['public.projects.discover', 'citizen.report.create', 'citizen.report.track', 'citizen.evidence.upload'],
      };
      setUser(citizenUser);
      localStorage.setItem('user', JSON.stringify(citizenUser));
      localStorage.setItem('eiil_current_user', JSON.stringify(citizenUser));
      return { success: true, role: 'CITIZEN', user: citizenUser };
    }
    const { error: verifyError } = await supabase.auth.verifyOtp({ phone, token: otp, type: 'sms' });
    if (verifyError) {
      setError(verifyError.message);
      return { success: false, message: verifyError.message };
    }
    try {
      const { data: { user: identity } } = await supabase.auth.getUser();
      const principal = await loadPrincipal(identity);
      return { success: true, role: principal.role, user: principal };
    } catch (cause) {
      await supabase.auth.signOut();
      setError(cause.message || 'The signed-in identity is not authorized for PRISM.');
      return { success: false, message: cause.message };
    }
  };

  const login = loginAsOfficial;
  const loginAsAnonymous = async () => ({ success: false, message: 'Anonymous reporting is not provided by the connected backend. You can view published public project records without signing in.' });

  const logout = async () => {
    if (supabase) {
      try {
        await supabase.auth.signOut();
      } catch {
        // Ignore sign-out error
      }
    }
    setUser(null);
    localStorage.removeItem('auth_token');
    localStorage.removeItem('user');
    localStorage.removeItem('eiil_current_user');
  };

  return (
    <AuthContext.Provider value={{ user, login, loginAsOfficial, loginAsCitizen, requestCitizenOtp, loginAsAnonymous, logout, loading, error, isAuthenticated: Boolean(user) }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within an AuthProvider');
  return context;
}

export default AuthContext;
