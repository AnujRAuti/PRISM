import { useAuth } from '../../context/AuthContext';
import { Navigate, Outlet } from 'react-router-dom';

function ProtectedRoute() {
  const { isAuthenticated, loading } = useAuth();

  if (loading) {
    return (
      <div className="d-flex justify-content-center align-items-center" style={{ height: '100vh' }}>
        <div className="text-center">
          <div className="spinner" style={{ width: '40px', height: '40px' }}></div>
          <p className="mt-3 text-muted">Authenticating...</p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return <Outlet />;
}

export default ProtectedRoute;
