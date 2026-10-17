import { createContext, useContext, useState, useEffect } from 'react';
import { authApi } from '../services/api';

const AuthContext = createContext();

// Mock user data for development
const MOCK_USER = {
  id: 'user-001',
  username: 'demo_user',
  name: 'Demo User',
  email: 'demo@proofofaction.gov.in',
  role: 'reviewer',
  permissions: ['evidence.read', 'evidence.upload', 'review.read', 'review.decide'],
  created_at: new Date().toISOString()
};

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    checkAuth();
  }, []);

  const checkAuth = async () => {
    const token = localStorage.getItem('auth_token');
    const storedUser = localStorage.getItem('user');

    if (token) {
      try {
        const response = await authApi.getCurrentUser();
        const principal = response.data;
        if (principal && principal.authenticated) {
          const liveUser = {
            id: principal.id || 'usr-live-001',
            username: principal.display_name || 'Officer',
            name: principal.display_name || 'GovTech Official',
            email: 'officer@proofofaction.gov.in',
            role: (principal.roles && principal.roles[0]) ? principal.roles[0].toLowerCase() : 'admin',
            permissions: principal.permissions || [],
            created_at: new Date().toISOString(),
          };
          setUser(liveUser);
          localStorage.setItem('user', JSON.stringify(liveUser));
          setLoading(false);
          return;
        }
      } catch (err) {
        console.warn('Backend /auth/me check warning, using cached/mock principal:', err);
      }
    }

    if (storedUser) {
      try {
        setUser(JSON.parse(storedUser));
      } catch {
        localStorage.removeItem('auth_token');
        localStorage.removeItem('user');
      }
    }
    setLoading(false);
  };

  const login = (username, password) => {
    // Mock login - accept any credentials for development
    // In production, this would call the actual API
    return new Promise((resolve) => {
      setTimeout(() => {
        if (username && username.length >= 3) {
          // Generate a mock token
          const token = 'mock-token-' + Math.random().toString(36).substring(2);

          localStorage.setItem('auth_token', token);
          localStorage.setItem('user', JSON.stringify(MOCK_USER));

          setUser(MOCK_USER);
          resolve({ success: true });
        } else {
          const errorMsg = username.length < 3
            ? 'Username must be at least 3 characters'
            : 'Invalid credentials';
          setError(errorMsg);
          resolve({
            success: false,
            message: errorMsg
          });
        }
      }, 300);
    });
  };

  const logout = () => {
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
