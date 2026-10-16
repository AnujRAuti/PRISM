import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import PrismLogo from '../common/PrismLogo';

function Login() {
  const [formData, setFormData] = useState({
    username: '',
    password: ''
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const { login, isAuthenticated } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (isAuthenticated) {
      navigate('/dashboard');
    }
  }, [isAuthenticated, navigate]);

  const handleChange = (e) => {
    setFormData({
      ...formData,
      [e.target.name]: e.target.value
    });
    setError('');
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    try {
      const result = await login(formData.username, formData.password);
      if (result.success) {
        navigate('/dashboard');
      } else {
        setError(result.message || 'Login failed');
      }
    } catch (err) {
      setError('An error occurred. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      minHeight: '100vh',
      backgroundColor: 'var(--govt-gray-off-white)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '2rem 1rem'
    }}>
      <div style={{
        maxWidth: '440px',
        width: '100%',
        backgroundColor: 'var(--govt-white)',
        borderRadius: 'var(--radius-xl)',
        border: '1px solid var(--govt-gray-medium)',
        boxShadow: 'var(--shadow-lg)',
        overflow: 'hidden'
      }}>
        {/* Header with animated PRISM Logo */}
        <div style={{
          padding: '2rem 2rem 1.5rem',
          backgroundColor: 'var(--govt-blue-dark)',
          textAlign: 'center',
          borderBottom: '1px solid rgba(255,255,255,0.08)'
        }}>
          <div style={{ display: 'inline-flex', justifyContent: 'center', marginBottom: '0.75rem' }}>
            <PrismLogo />
          </div>
          <p style={{
            margin: 0,
            fontSize: '0.85rem',
            color: '#94a3b8',
            fontWeight: '400',
            letterSpacing: '0.02em'
          }}>
            Multi-Signal Infrastructure Evidence & Cryptographic Audit
          </p>
        </div>

        <div style={{ padding: '2rem' }}>
          {error && (
            <div style={{
              backgroundColor: 'var(--govt-danger-light)',
              border: '1px solid var(--govt-danger-border)',
              color: 'var(--govt-danger-text)',
              padding: '0.75rem 1rem',
              borderRadius: 'var(--radius-md)',
              fontSize: '0.85rem',
              fontWeight: '500',
              marginBottom: '1.25rem',
            }} role="alert">
              {error}
            </div>
          )}
          <form onSubmit={handleSubmit}>
            <div style={{ marginBottom: '1.25rem' }}>
              <label htmlFor="username" style={{
                display: 'block',
                fontSize: '0.825rem',
                fontWeight: '600',
                color: 'var(--govt-gray-title)',
                marginBottom: '0.4rem',
              }}>
                Reviewer Email or Account ID
              </label>
              <input
                type="text"
                id="username"
                name="username"
                value={formData.username}
                onChange={handleChange}
                placeholder="e.g. reviewer@prism.gov.in"
                required
                autoComplete="username"
                style={{
                  width: '100%',
                  padding: '0.65rem 0.85rem',
                  fontSize: '0.9rem',
                  border: '1px solid var(--govt-gray-medium)',
                  borderRadius: 'var(--radius-md)',
                  boxSizing: 'border-box',
                  outline: 'none',
                }}
              />
            </div>
            <div style={{ marginBottom: '1.5rem' }}>
              <label htmlFor="password" style={{
                display: 'block',
                fontSize: '0.825rem',
                fontWeight: '600',
                color: 'var(--govt-gray-title)',
                marginBottom: '0.4rem',
              }}>
                Password
              </label>
              <input
                type="password"
                id="password"
                name="password"
                value={formData.password}
                onChange={handleChange}
                required
                autoComplete="current-password"
                placeholder="••••••••••••"
                style={{
                  width: '100%',
                  padding: '0.65rem 0.85rem',
                  fontSize: '0.9rem',
                  border: '1px solid var(--govt-gray-medium)',
                  borderRadius: 'var(--radius-md)',
                  boxSizing: 'border-box',
                  outline: 'none',
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
                fontSize: '0.95rem',
                fontWeight: '600',
                cursor: loading ? 'not-allowed' : 'pointer',
                opacity: loading ? 0.7 : 1,
                boxShadow: 'var(--shadow-sm)',
                transition: 'background-color 0.15s ease',
              }}
            >
              {loading ? 'Authenticating Credentials...' : 'Sign In as Reviewer'}
            </button>
          </form>
              <div className="text-center mt-3">
                <p className="mb-0 small">
                  Need help? Contact support at{' '}
                  <a href="mailto:support@prism.gov.in">
                    support@prism.gov.in
                  </a>
                </p>
            </div>
          </div>
        </div>
      </div>
  );
}

export default Login;
