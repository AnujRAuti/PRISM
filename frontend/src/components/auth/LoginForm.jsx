import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { useApp } from '../../context/AppContext';
import { isSupabaseConfigured } from '../../lib/supabase/client';
import PrismLogo from '../common/PrismLogo';
import {
  ShieldCheck,
  Lock,
  User,
  Smartphone,
  Eye,
  EyeOff,
  CheckCircle2,
  AlertTriangle,
  Building2,
  Users,
  Award,
  ArrowRight
} from 'lucide-react';

export default function LoginForm() {
  const [authMode, setAuthMode] = useState('official'); // 'official' | 'citizen'

  // Official Form State
  const [officialEmail, setOfficialEmail] = useState('');
  const [officialPassword, setOfficialPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);

  // Citizen Form State
  const [citizenMobile, setCitizenMobile] = useState('');
  const [citizenOtp, setCitizenOtp] = useState('');
  const [otpSent, setOtpSent] = useState(false);
  const [otpCountdown, setOtpCountdown] = useState(0);

  // General State
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [infoMessage, setInfoMessage] = useState('');

  const { loginAsOfficial, loginAsCitizen, requestCitizenOtp, isAuthenticated, user } = useAuth();
  const { loginUser } = useApp();
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    if (isAuthenticated && user) {
      const targetPath =
        user.role === 'CITIZEN'
          ? '/citizen'
          : user.role === 'AUDITOR'
          ? '/auditor'
          : user.role === 'ADMIN'
          ? '/admin'
          : '/dashboard';
      navigate(targetPath, { replace: true });
    }
  }, [isAuthenticated, user, navigate]);

  // Countdown timer for OTP
  useEffect(() => {
    let timer;
    if (otpCountdown > 0) {
      timer = setTimeout(() => setOtpCountdown((prev) => prev - 1), 1000);
    }
    return () => clearTimeout(timer);
  }, [otpCountdown]);

  const handleSendOtp = async () => {
    setError('');
    setInfoMessage('');
    try {
      await requestCitizenOtp(citizenMobile || '9823011223');
      setOtpSent(true);
      setOtpCountdown(45);
      if (!isSupabaseConfigured) {
        setCitizenOtp('123456');
        setInfoMessage('Development mode: Verification OTP pre-filled (123456).');
      } else {
        setInfoMessage('A verification code was requested from the configured identity provider.');
      }
    } catch (cause) {
      setError(cause.message || 'Could not send a verification code.');
    }
  };

  const handleOfficialSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    setInfoMessage('');

    try {
      const res = await loginAsOfficial(officialEmail, officialPassword);
      if (res.success) {
        // Synchronize AppContext state
        loginUser(res.role, res.user);

        const target =
          res.role === 'AUDITOR'
            ? '/auditor'
            : res.role === 'ADMIN'
            ? '/admin'
            : '/dashboard';
        navigate(target, { replace: true });
      } else {
        setError(res.message || 'Official authentication failed.');
      }
    } catch {
      setError('Secure government authentication server timed out. Check network connection.');
    } finally {
      setLoading(false);
    }
  };

  const handleCitizenSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    setInfoMessage('');

    try {
      const res = await loginAsCitizen({ mobileNumber: citizenMobile, otp: citizenOtp });

      if (res.success) {
        loginUser('CITIZEN', res.user);
        navigate('/citizen', { replace: true });
      } else {
        setError(res.message || 'Citizen OTP verification failed.');
      }
    } catch {
      setError('Citizen authentication gateway unreachable. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleAnonymousCitizenAccess = async () => {
    setInfoMessage('Public published project information does not require sign-in.');
    navigate('/public');
  };

  return (
    <div
      style={{
        minHeight: '100vh',
        backgroundColor: 'var(--govt-gray-off-white)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '2rem 1rem',
        boxSizing: 'border-box',
      }}
    >
      <div
        style={{
          maxWidth: '520px',
          width: '100%',
          backgroundColor: 'var(--govt-white)',
          borderRadius: 'var(--radius-xl, 16px)',
          border: '1px solid var(--govt-gray-medium)',
          boxShadow: 'var(--shadow-xl)',
          overflow: 'hidden',
        }}
      >
        {/* Header with animated PRISM Logo */}
        <div
          style={{
            padding: '2.25rem 2rem 1.5rem',
            backgroundColor: 'var(--govt-blue-dark)',
            textAlign: 'center',
            borderBottom: '1px solid rgba(255,255,255,0.08)',
          }}
        >
          <div style={{ display: 'inline-flex', justifyContent: 'center', marginBottom: '0.85rem' }}>
            <PrismLogo />
          </div>
          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.4rem',
              backgroundColor: 'rgba(255, 255, 255, 0.1)',
              padding: '0.2rem 0.65rem',
              borderRadius: '999px',
              color: '#38bdf8',
              fontSize: '0.725rem',
              fontWeight: 700,
              letterSpacing: '0.04em',
              textTransform: 'uppercase',
              marginBottom: '0.5rem',
            }}
          >
            <ShieldCheck size={13} /> Digital Public Infrastructure (DPI)
          </div>
          <p
            style={{
              margin: 0,
              fontSize: '0.825rem',
              color: '#94a3b8',
              fontWeight: '400',
              lineHeight: 1.4,
            }}
          >
            Multi-Signal Infrastructure Evidence & Cryptographic Audit System
          </p>
        </div>

        {/* 2-Option Sign-In Selector Tabs */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            borderBottom: '1px solid var(--govt-gray-medium)',
            backgroundColor: 'var(--govt-gray-off-white)',
          }}
        >
          <button
            type="button"
            onClick={() => {
              setAuthMode('official');
              setError('');
              setInfoMessage('');
            }}
            style={{
              padding: '0.9rem 1rem',
              border: 'none',
              backgroundColor: authMode === 'official' ? '#ffffff' : 'transparent',
              borderBottom: authMode === 'official' ? '3px solid var(--govt-blue-primary)' : '3px solid transparent',
              color: authMode === 'official' ? 'var(--govt-blue-primary)' : 'var(--govt-gray-dark)',
              fontWeight: authMode === 'official' ? 700 : 500,
              fontSize: '0.875rem',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '0.5rem',
              transition: 'all 0.15s ease',
            }}
          >
            <Building2 size={16} /> Sign In as Official
          </button>

          <button
            type="button"
            onClick={() => {
              setAuthMode('citizen');
              setError('');
              setInfoMessage('');
            }}
            style={{
              padding: '0.9rem 1rem',
              border: 'none',
              backgroundColor: authMode === 'citizen' ? '#ffffff' : 'transparent',
              borderBottom: authMode === 'citizen' ? '3px solid var(--govt-blue-primary)' : '3px solid transparent',
              color: authMode === 'citizen' ? 'var(--govt-blue-primary)' : 'var(--govt-gray-dark)',
              fontWeight: authMode === 'citizen' ? 700 : 500,
              fontSize: '0.875rem',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '0.5rem',
              transition: 'all 0.15s ease',
            }}
          >
            <Users size={16} /> Sign In as Citizen
          </button>
        </div>

        <div style={{ padding: '1.75rem 2rem 2rem' }}>
          {/* Error & Info Alerts */}
          {error && (
            <div
              style={{
                backgroundColor: 'rgba(239, 68, 68, 0.08)',
                border: '1px solid rgba(239, 68, 68, 0.3)',
                color: 'var(--govt-danger)',
                padding: '0.75rem 1rem',
                borderRadius: 'var(--radius-md)',
                fontSize: '0.825rem',
                fontWeight: '500',
                marginBottom: '1.25rem',
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
              }}
              role="alert"
            >
              <AlertTriangle size={16} style={{ flexShrink: 0 }} />
              <span>{error}</span>
            </div>
          )}

          {infoMessage && (
            <div
              style={{
                backgroundColor: 'rgba(59, 130, 246, 0.08)',
                border: '1px solid rgba(59, 130, 246, 0.25)',
                color: 'var(--govt-blue-primary)',
                padding: '0.75rem 1rem',
                borderRadius: 'var(--radius-md)',
                fontSize: '0.825rem',
                fontWeight: '500',
                marginBottom: '1.25rem',
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
              }}
            >
              <CheckCircle2 size={16} style={{ flexShrink: 0 }} />
              <span>{infoMessage}</span>
            </div>
          )}

          {/* OPTION 1: OFFICIAL LOGIN FORM */}
          {authMode === 'official' ? (
            <form onSubmit={handleOfficialSubmit}>
              <div style={{ marginBottom: '1.25rem' }}>
                <label
                  htmlFor="officialEmail"
                  style={{
                    display: 'block',
                    fontSize: '0.8rem',
                    fontWeight: 700,
                    color: 'var(--govt-blue-dark)',
                    marginBottom: '0.4rem',
                  }}
                >
                  Official Government Email or Operator ID *
                </label>
                <div style={{ position: 'relative' }}>
                  <User
                    size={16}
                    style={{ position: 'absolute', left: '0.85rem', top: '50%', transform: 'translateY(-50%)', color: '#94a3b8' }}
                  />
                  <input
                    type="text"
                    id="officialEmail"
                    value={officialEmail}
                    onChange={(e) => setOfficialEmail(e.target.value)}
                    placeholder="e.g. reviewer@prism.gov.in"
                    required
                    style={{
                      width: '100%',
                      padding: '0.65rem 0.85rem 0.65rem 2.4rem',
                      fontSize: '0.875rem',
                      border: '1px solid var(--govt-gray-medium)',
                      borderRadius: 'var(--radius-md)',
                      boxSizing: 'border-box',
                      outline: 'none',
                    }}
                  />
                </div>
              </div>

              {/* Password with visibility toggle */}
              <div style={{ marginBottom: '1.25rem' }}>
                <label
                  htmlFor="officialPassword"
                  style={{
                    display: 'block',
                    fontSize: '0.8rem',
                    fontWeight: 700,
                    color: 'var(--govt-blue-dark)',
                    marginBottom: '0.4rem',
                  }}
                >
                  Government Access Password *
                </label>
                <div style={{ position: 'relative' }}>
                  <Lock
                    size={16}
                    style={{ position: 'absolute', left: '0.85rem', top: '50%', transform: 'translateY(-50%)', color: '#94a3b8' }}
                  />
                  <input
                    type={showPassword ? 'text' : 'password'}
                    id="officialPassword"
                    value={officialPassword}
                    onChange={(e) => setOfficialPassword(e.target.value)}
                    required
                    style={{
                      width: '100%',
                      padding: '0.65rem 2.5rem 0.65rem 2.4rem',
                      fontSize: '0.875rem',
                      border: '1px solid var(--govt-gray-medium)',
                      borderRadius: 'var(--radius-md)',
                      boxSizing: 'border-box',
                      outline: 'none',
                    }}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    style={{
                      position: 'absolute',
                      right: '0.75rem',
                      top: '50%',
                      transform: 'translateY(-50%)',
                      background: 'none',
                      border: 'none',
                      color: '#94a3b8',
                      cursor: 'pointer',
                      padding: '0.2rem',
                    }}
                    aria-label="Toggle password visibility"
                  >
                    {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>
              </div>

              {!isSupabaseConfigured && (
                <div style={{ marginBottom: '1.25rem' }}>
                  <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--govt-gray-dark)', marginBottom: '0.4rem' }}>
                    Quick Demo Accounts (Local Dev):
                  </div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem' }}>
                    <button
                      type="button"
                      onClick={() => {
                        setOfficialEmail('reviewer@prism.gov.in');
                        setOfficialPassword('GovTech@2026!Prism');
                      }}
                      style={{
                        fontSize: '0.725rem',
                        padding: '0.25rem 0.55rem',
                        borderRadius: '4px',
                        border: '1px solid var(--govt-gray-medium)',
                        backgroundColor: officialEmail.includes('reviewer') ? '#e0f2fe' : '#ffffff',
                        color: officialEmail.includes('reviewer') ? 'var(--govt-blue-primary)' : 'var(--govt-gray-dark)',
                        fontWeight: officialEmail.includes('reviewer') ? 700 : 500,
                        cursor: 'pointer',
                      }}
                    >
                      🛡️ Reviewer
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setOfficialEmail('anand.swaroop@cag.gov.in');
                        setOfficialPassword('GovTech@2026!Prism');
                      }}
                      style={{
                        fontSize: '0.725rem',
                        padding: '0.25rem 0.55rem',
                        borderRadius: '4px',
                        border: '1px solid var(--govt-gray-medium)',
                        backgroundColor: officialEmail.includes('cag') ? '#e0f2fe' : '#ffffff',
                        color: officialEmail.includes('cag') ? 'var(--govt-blue-primary)' : 'var(--govt-gray-dark)',
                        fontWeight: officialEmail.includes('cag') ? 700 : 500,
                        cursor: 'pointer',
                      }}
                    >
                      ⚖️ Auditor
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setOfficialEmail('secadmin@prism.gov.in');
                        setOfficialPassword('GovTech@2026!Prism');
                      }}
                      style={{
                        fontSize: '0.725rem',
                        padding: '0.25rem 0.55rem',
                        borderRadius: '4px',
                        border: '1px solid var(--govt-gray-medium)',
                        backgroundColor: officialEmail.includes('admin') ? '#e0f2fe' : '#ffffff',
                        color: officialEmail.includes('admin') ? 'var(--govt-blue-primary)' : 'var(--govt-gray-dark)',
                        fontWeight: officialEmail.includes('admin') ? 700 : 500,
                        cursor: 'pointer',
                      }}
                    >
                      ⚙️ Admin
                    </button>
                  </div>
                </div>
              )}

              <button
                type="submit"
                disabled={loading}
                style={{
                  width: '100%',
                  padding: '0.75rem',
                  backgroundColor: 'var(--govt-blue-primary)',
                  color: '#ffffff',
                  border: 'none',
                  borderRadius: 'var(--radius-md)',
                  fontSize: '0.925rem',
                  fontWeight: 700,
                  cursor: loading ? 'not-allowed' : 'pointer',
                  boxShadow: 'var(--shadow-sm)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '0.5rem',
                }}
              >
                {loading ? 'Authenticating & Establishing Session...' : 'Authenticate & Sign In as Official →'}
              </button>
            </form>
          ) : (
            /* OPTION 2: CITIZEN LOGIN FORM */
            <form onSubmit={handleCitizenSubmit}>
              <div style={{ marginBottom: '1.25rem' }}>
                <label
                  htmlFor="citizenMobile"
                  style={{
                    display: 'block',
                    fontSize: '0.8rem',
                    fontWeight: 700,
                    color: 'var(--govt-blue-dark)',
                    marginBottom: '0.4rem',
                  }}
                >
                  Citizen Mobile Number (Aadhaar Linked) *
                </label>
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <span
                    style={{
                      padding: '0.65rem 0.85rem',
                      backgroundColor: 'var(--govt-gray-off-white)',
                      border: '1px solid var(--govt-gray-medium)',
                      borderRadius: 'var(--radius-md)',
                      fontSize: '0.875rem',
                      fontWeight: 700,
                      color: 'var(--govt-blue-dark)',
                    }}
                  >
                    +91
                  </span>
                  <input
                    type="tel"
                    id="citizenMobile"
                    value={citizenMobile}
                    onChange={(e) => setCitizenMobile(e.target.value)}
                    placeholder="10-digit mobile number"
                    maxLength={10}
                    required
                    style={{
                      flex: 1,
                      padding: '0.65rem 0.85rem',
                      fontSize: '0.875rem',
                      border: '1px solid var(--govt-gray-medium)',
                      borderRadius: 'var(--radius-md)',
                      outline: 'none',
                    }}
                  />
                  <button
                    type="button"
                    onClick={handleSendOtp}
                    disabled={otpCountdown > 0}
                    style={{
                      padding: '0.65rem 1rem',
                      backgroundColor: otpCountdown > 0 ? 'var(--govt-gray-medium)' : 'var(--govt-blue-primary)',
                      color: '#fff',
                      border: 'none',
                      borderRadius: 'var(--radius-md)',
                      fontSize: '0.8rem',
                      fontWeight: 700,
                      cursor: otpCountdown > 0 ? 'not-allowed' : 'pointer',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {otpCountdown > 0 ? `Resend (${otpCountdown}s)` : 'Send OTP'}
                  </button>
                </div>
              </div>

              {/* 6-Digit OTP Input */}
              <div style={{ marginBottom: '1.5rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.4rem' }}>
                  <label
                    htmlFor="citizenOtp"
                    style={{
                      fontSize: '0.8rem',
                      fontWeight: 700,
                      color: 'var(--govt-blue-dark)',
                    }}
                  >
                    6-Digit Verification OTP *
                  </label>
                  <span style={{ fontSize: '0.7rem', color: 'var(--govt-success)', fontWeight: 700 }}>
                    {!isSupabaseConfigured
                      ? (otpSent ? 'Demo code: 123456' : 'Click Send OTP (Demo: 123456)')
                      : (otpSent ? 'Code sent' : 'Request a code first')}
                  </span>
                </div>
                <input
                  type="text"
                  id="citizenOtp"
                  value={citizenOtp}
                  onChange={(e) => setCitizenOtp(e.target.value)}
                  placeholder="Enter 6-digit OTP"
                  maxLength={6}
                  required
                  style={{
                    width: '100%',
                    padding: '0.75rem',
                    fontSize: '1.1rem',
                    fontWeight: 700,
                    textAlign: 'center',
                    letterSpacing: '0.25em',
                    border: '1.5px solid var(--govt-blue-primary)',
                    borderRadius: 'var(--radius-md)',
                    boxSizing: 'border-box',
                    fontFamily: 'var(--font-family-mono)',
                    backgroundColor: 'var(--govt-gray-off-white)',
                  }}
                />
              </div>

              <button
                type="submit"
                disabled={loading}
                style={{
                  width: '100%',
                  padding: '0.75rem',
                  backgroundColor: 'var(--govt-blue-primary)',
                  color: '#ffffff',
                  border: 'none',
                  borderRadius: 'var(--radius-md)',
                  fontSize: '0.925rem',
                  fontWeight: 700,
                  cursor: loading ? 'not-allowed' : 'pointer',
                  boxShadow: 'var(--shadow-sm)',
                  marginBottom: '1rem',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '0.5rem',
                }}
              >
                {loading ? 'Verifying Resident OTP...' : 'Sign In via Verified OTP →'}
              </button>

              {/* Limited Anonymous Whistleblower Option (BE-022) */}
              <div style={{ textAlign: 'center' }}>
                <button
                  type="button"
                  onClick={handleAnonymousCitizenAccess}
                  disabled={loading}
                  style={{
                    background: 'none',
                    border: 'none',
                    color: 'var(--govt-gray-dark)',
                    fontSize: '0.775rem',
                    textDecoration: 'underline',
                    cursor: 'pointer',
                    fontWeight: 500,
                  }}
                >
                  Or Continue Anonymously (Privacy Protected per BE-022)
                </button>
              </div>
            </form>
          )}

          {/* Security & Statutory Non-Repudiation Footer */}
          <div
            style={{
              marginTop: '1.75rem',
              paddingTop: '1.25rem',
              borderTop: '1px solid var(--govt-gray-medium)',
              fontSize: '0.725rem',
              color: 'var(--govt-gray-dark)',
              textAlign: 'center',
              lineHeight: 1.4,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.4rem', marginBottom: '0.25rem' }}>
              <Lock size={12} style={{ color: 'var(--govt-success)' }} />
              <strong>256-Bit TLS & Section 86 Statutory Compliance</strong>
            </div>
            <span>
              All transactions are recorded in the immutable SHA-256 event ledger. Unauthorized access attempts to Government evidence verification registries are punishable under the IT Act.
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
