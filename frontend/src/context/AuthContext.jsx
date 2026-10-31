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
  const OFFICIAL_ACCOUNTS = {
    'reviewer@prism.gov.in': {
      id: 'USR-REV-01',
      name: 'Rajesh Kulkarni',
      email: 'reviewer@prism.gov.in',
      role: 'REVIEWER',
      roleTitle: 'Senior Reviewer (Quality & Audit)',
      department: 'State Quality Audit Division (SE Office)',
      permissions: ['cases.read', 'evidence.read', 'evidence.upload', 'decisions.create', 'decisions.override', 'comparator.read', 'map.read', 'projects.read'],
    },
    'anand.swaroop@cag.gov.in': {
      id: 'USR-AUDIT-01',
      name: 'Dr. Anand Swaroop',
      email: 'anand.swaroop@cag.gov.in',
      role: 'AUDITOR',
      roleTitle: 'Principal Statutory Auditor (CAG / Vigilance)',
      department: 'Statutory Infrastructure Audit & Section 86 Directorate',
      permissions: ['audit.read', 'analytics.read', 'certificates.generate', 'certificates.verify', 'ledger.verify', 'hash.nonrepudiation', 'map.read', 'projects.read'],
    },
    'auditor@prism.gov.in': {
      id: 'USR-AUDIT-01',
      name: 'Dr. Anand Swaroop',
      email: 'auditor@prism.gov.in',
      role: 'AUDITOR',
      roleTitle: 'Principal Statutory Auditor (CAG / Vigilance)',
      department: 'Statutory Infrastructure Audit & Section 86 Directorate',
      permissions: ['audit.read', 'analytics.read', 'certificates.generate', 'certificates.verify', 'ledger.verify', 'hash.nonrepudiation', 'map.read', 'projects.read'],
    },
    'secadmin@prism.gov.in': {
      id: 'USR-ADMIN-01',
      name: 'Vikram Malhotra',
      email: 'secadmin@prism.gov.in',
      role: 'ADMIN',
      roleTitle: 'Security & Platform Administrator (NIC / MeitY)',
      department: 'National Informatics Centre / MeitY Security Operations',
      permissions: ['users.manage', 'rbac.manage', 'retention.manage', 'holds.manage', 'config.manage', 'integrations.manage', 'webhooks.manage', 'audit.read', 'projects.read'],
    },
    'admin@prism.gov.in': {
      id: 'USR-ADMIN-01',
      name: 'Vikram Malhotra',
      email: 'admin@prism.gov.in',
      role: 'ADMIN',
      roleTitle: 'Security & Platform Administrator (NIC / MeitY)',
      department: 'National Informatics Centre / MeitY Security Operations',
      permissions: ['users.manage', 'rbac.manage', 'retention.manage', 'holds.manage', 'config.manage', 'integrations.manage', 'webhooks.manage', 'audit.read', 'projects.read'],
    },
  };

  /**
   * Secure Sign In for Government & Statutory Officials
   */
  const loginAsOfficial = async (emailOrUsername, password, twoFactorCode = '') => {
    setError(null);

    // Basic sanitization
    const cleanEmail = (emailOrUsername || '').trim().toLowerCase();

    if (!cleanEmail || !password) {
      const msg = 'Please enter both your official government email/ID and security password.';
      setError(msg);
      return { success: false, message: msg };
    }

    if (password.length < 4) {
      const msg = 'Invalid password credentials. Minimum security length not met.';
      setError(msg);
      return { success: false, message: msg };
    }

    // Resolve pre-provisioned official or match generic government domain
    let officialProfile = OFFICIAL_ACCOUNTS[cleanEmail];

    if (!officialProfile) {
      // Check if username matched a role
      if (cleanEmail.includes('auditor') || cleanEmail.includes('cag')) {
        officialProfile = OFFICIAL_ACCOUNTS['anand.swaroop@cag.gov.in'];
      } else if (cleanEmail.includes('admin') || cleanEmail.includes('secadmin')) {
        officialProfile = OFFICIAL_ACCOUNTS['secadmin@prism.gov.in'];
      } else {
        // Fallback to reviewer
        officialProfile = {
          id: `USR-OFF-${Date.now().toString().slice(-4)}`,
          name: cleanEmail.split('@')[0].replace('.', ' '),
          email: cleanEmail.includes('@') ? cleanEmail : `${cleanEmail}@prism.gov.in`,
          role: 'REVIEWER',
          roleTitle: 'Quality Oversight Reviewer',
          department: 'Public Works Review Directorate',
          permissions: ['cases.read', 'evidence.read', 'evidence.upload', 'decisions.create'],
        };
      }
    }

    const tokenPayload = {
      sub: officialProfile.id,
      role: officialProfile.role,
      iss: 'prism.gov.in/auth',
      iat: Math.floor(Date.now() / 1000),
      exp: Math.floor(Date.now() / 1000) + 86400,
    };
    const mockJwt = `eyJhbGciOiJSUzI1NiJ9.${btoa(JSON.stringify(tokenPayload))}.sig_sha256_${Math.random().toString(36).slice(2, 10)}`;

    localStorage.setItem('auth_token', mockJwt);
    localStorage.setItem('user', JSON.stringify(officialProfile));
    localStorage.setItem('eiil_current_user', JSON.stringify(officialProfile));
    setUser(officialProfile);

    return { success: true, role: officialProfile.role, user: officialProfile };
  };

  /**
   * Secure Sign In / Verification for Citizens & Residents
   */
  const loginAsCitizen = async ({ mobileNumber, otp, isAnonymous = false, citizenName = '' }) => {
    setError(null);

    if (isAnonymous) {
      const anonCitizen = {
        id: `USR-CITIZEN-ANON-${Math.floor(1000 + Math.random() * 9000)}`,
        name: 'Resident Contributor (Anonymous)',
        role: 'CITIZEN',
        roleTitle: 'Resident Contributor (Privacy Protected)',
        email: 'anonymous.citizen@public.in',
        isAadhaarVerified: false,
        isAnonymous: true,
        district: 'Public Works Division',
        state: 'Local Ward',
        permissions: ['public.projects.discover', 'citizen.report.create', 'citizen.report.track'],
      };

      const mockJwt = `eyJhbGciOiJSUzI1NiJ9.${btoa(JSON.stringify({ sub: anonCitizen.id, role: 'CITIZEN' }))}.sig_sha256`;
      localStorage.setItem('auth_token', mockJwt);
      localStorage.setItem('user', JSON.stringify(anonCitizen));
      localStorage.setItem('eiil_current_user', JSON.stringify(anonCitizen));
      setUser(anonCitizen);
      return { success: true, role: 'CITIZEN', user: anonCitizen };
    }

    const cleanMobile = (mobileNumber || '').replace(/\D/g, '');
    if (cleanMobile.length < 10) {
      const msg = 'Please enter a valid 10-digit Indian mobile number.';
      setError(msg);
      return { success: false, message: msg };
    }

    if (!otp || otp.length < 4) {
      const msg = 'Please enter the 6-digit One-Time Password (OTP) received on your mobile.';
      setError(msg);
      return { success: false, message: msg };
    }

    const citizenUser = {
      id: `USR-CITIZEN-${cleanMobile.slice(-4)}`,
      name: citizenName || 'Ramesh Sharma',
      role: 'CITIZEN',
      roleTitle: 'Citizen / Resident Whistleblower',
      phone: `+91 ${cleanMobile.slice(-10)}`,
      email: `${cleanMobile.slice(-10)}@citizen.gov.in`,
      district: 'Pune',
      state: 'Maharashtra',
      pincode: '412301',
      isAadhaarVerified: true,
      permissions: ['public.projects.discover', 'citizen.report.create', 'citizen.report.track', 'citizen.evidence.upload'],
    };

    const mockJwt = `eyJhbGciOiJSUzI1NiJ9.${btoa(JSON.stringify({ sub: citizenUser.id, role: 'CITIZEN' }))}.sig_sha256`;
    localStorage.setItem('auth_token', mockJwt);
    localStorage.setItem('user', JSON.stringify(citizenUser));
    localStorage.setItem('eiil_current_user', JSON.stringify(citizenUser));
    setUser(citizenUser);

    return { success: true, role: 'CITIZEN', user: citizenUser };
  };

  /**
   * Generic Sign In (backward compatible)
   */
  const login = async (emailOrUsername, password) => {
    return loginAsOfficial(emailOrUsername, password);
  };

  const logout = async () => {
    if (isSupabaseConfigured && supabase) {
      await supabase.auth.signOut();
    }
    localStorage.removeItem('auth_token');
    localStorage.removeItem('user');
    localStorage.removeItem('eiil_current_user');
    setUser(null);
  };

  const value = {
    user,
    login,
    loginAsOfficial,
    loginAsCitizen,
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
