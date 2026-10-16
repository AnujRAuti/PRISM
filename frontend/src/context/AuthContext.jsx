import { createContext, useContext, useState, useEffect } from 'react';

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

  const checkAuth = () => {
    const token = localStorage.getItem('auth_token');
    const storedUser = localStorage.getItem('user');
    if (token && storedUser) {
      try {
        setUser(JSON.parse(storedUser));
      } catch (err) {
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
