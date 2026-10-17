import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import { AppProvider } from './context/AppContext';
import { useState, useEffect, lazy, Suspense } from 'react';

// Import Styles
import './styles/variables.css';
import './styles/common.css';

// Layout & Core Components
import ProtectedRoute from './components/common/ProtectedRoute';
import Layout from './components/common/Layout';
import LoadingSplash from './components/common/LoadingSplash';

// Code-split route components for performance optimization & bundle reduction
const Login = lazy(() => import('./components/auth/LoginForm'));
const Dashboard = lazy(() => import('./pages/Dashboard'));
const ProjectsList = lazy(() => import('./pages/Projects/ProjectsList'));
const ProjectDetail = lazy(() => import('./pages/Projects/ProjectDetail'));
const ReviewQueue = lazy(() => import('./pages/Reviews/ReviewQueue'));
const EvidenceDetail = lazy(() => import('./pages/Evidence/EvidenceDetail'));
const EvidenceCompare = lazy(() => import('./pages/Compare/EvidenceCompare'));
const GeospatialMap = lazy(() => import('./pages/Map/GeospatialMap'));
const IngestionSandbox = lazy(() => import('./pages/Ingest/IngestionSandbox'));
const AuditAnalytics = lazy(() => import('./pages/Analytics/AuditAnalytics'));
const AuditLog = lazy(() => import('./pages/Audit/AuditLog'));
const FieldOperations = lazy(() => import('./pages/Field/FieldOperations'));
const About = lazy(() => import('./pages/About/About'));
const Settings = lazy(() => import('./pages/Settings/Settings'));
const Profile = lazy(() => import('./pages/Profile'));

// Accessible Loading Fallback for Suspense transitions with PRISM branding
function LoadingFallback() {
  return (
    <div
      role="status"
      aria-live="polite"
      style={{
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        alignItems: 'center',
        minHeight: '60vh',
        gap: '1.25rem',
        padding: '2rem'
      }}
    >
      <div
        style={{
          width: '56px',
          height: '56px',
          borderRadius: '14px',
          backgroundColor: '#0f172a',
          border: '1.5px solid rgba(168, 85, 247, 0.4)',
          boxShadow: '0 0 20px rgba(168, 85, 247, 0.3)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <img
          src="/prism-symbol-transparent.png"
          alt="PRISM Loading"
          style={{
            width: '36px',
            height: '36px',
            objectFit: 'contain',
            animation: 'prism-pulse 2s ease-in-out infinite',
          }}
        />
      </div>
      <div style={{ textAlign: 'center' }}>
        <p style={{ margin: 0, color: 'var(--govt-blue-dark)', fontSize: '0.95rem', fontWeight: '700', letterSpacing: '0.02em' }}>
          PRISM
        </p>
        <p style={{ margin: '0.25rem 0 0', color: 'var(--govt-gray-dark)', fontSize: '0.8rem', fontWeight: '500' }}>
          Loading PRISM Verification Workspace...
        </p>
      </div>
      <span className="sr-only">Please wait, loading PRISM content.</span>
    </div>
  );
}

// Main App component
function App() {
  const [showSplash, setShowSplash] = useState(true);

  useEffect(() => {
    // Load Bootstrap CSS for dropdowns and grid utilities
    const link = document.createElement('link');
    link.href = 'https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css';
    link.rel = 'stylesheet';
    document.head.appendChild(link);

    return () => {
      document.head.removeChild(link);
    };
  }, []);

  return (
    <AuthProvider>
      {showSplash && <LoadingSplash onComplete={() => setShowSplash(false)} />}
      <Router>
        <AppProvider>
          <Suspense fallback={<LoadingFallback />}>
            <Routes>
              {/* Public routes */}
              <Route path="/login" element={<Login />} />

              {/* Protected routes */}
              <Route element={<ProtectedRoute />}>
                <Route element={<Layout />}>
                  <Route path="/" element={<Navigate to="/dashboard" replace />} />
                  <Route path="/dashboard" element={<Dashboard />} />

                  {/* Review Queue (PoA Primary Workflow) */}
                  <Route path="/reviews" element={<ReviewQueue />} />
                  <Route path="/queue" element={<ReviewQueue />} />
                  <Route path="/review" element={<Navigate to="/reviews" replace />} />

                  {/* Evidence Dossier Routes */}
                  <Route path="/evidence" element={<Navigate to="/reviews" replace />} />
                  <Route path="/evidence/:id" element={<EvidenceDetail />} />

                  {/* Project Dossier Routes */}
                  <Route path="/projects" element={<ProjectsList />} />
                  <Route path="/projects/:id" element={<ProjectDetail />} />

                  {/* PoA Feature Routes */}
                  <Route path="/compare" element={<EvidenceCompare />} />
                  <Route path="/map" element={<GeospatialMap />} />
                  <Route path="/ingest" element={<IngestionSandbox />} />
                  <Route path="/analytics" element={<AuditAnalytics />} />
                  <Route path="/audit" element={<AuditLog />} />
                  <Route path="/field" element={<FieldOperations />} />
                  <Route path="/about" element={<About />} />
                  <Route path="/settings" element={<Settings />} />
                  <Route path="/profile" element={<Profile />} />

                  {/* Legacy Redirections */}
                  <Route path="/graph" element={<Navigate to="/compare" replace />} />
                  <Route path="/search" element={<Navigate to="/reviews" replace />} />
                  <Route path="/admin" element={<Navigate to="/settings" replace />} />
                </Route>
              </Route>
            </Routes>
          </Suspense>
        </AppProvider>
      </Router>
    </AuthProvider>
  );
}

export default App;
