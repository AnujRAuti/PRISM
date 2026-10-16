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
                <div className="alert alert-danger" role="alert">
                  {error}
                </div>
              )}
              <form onSubmit={handleSubmit}>
                <div className="mb-3">
                  <label htmlFor="username" className="form-label">
                    Username
                  </label>
                  <input
                    type="text"
                    className="form-control"
                    id="username"
                    name="username"
                    value={formData.username}
                    onChange={handleChange}
                    required
                  />
                </div>
                <div className="mb-3">
                  <label htmlFor="password" className="form-label">
                    Password
                  </label>
                  <input
                    type="password"
                    className="form-control"
                    id="password"
                    name="password"
                    value={formData.password}
                    onChange={handleChange}
                    required
                  />
                </div>
                <div className="mb-3">
                  <div className="form-check">
                    <input
                      className="form-check-input"
                      type="checkbox"
                      id="rememberMe"
                    />
                    <label className="form-check-label" htmlFor="rememberMe">
                      Remember me
                    </label>
                  </div>
                </div>
                <button
                  type="submit"
                  className="btn btn-primary w-100"
                  disabled={loading}
                >
                  {loading ? (
                    <>
                      <span className="spinner spinner-border-sm me-2"></span>
                      Signing in...
                    </>
                  ) : (
                    'Sign In'
                  )}
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
