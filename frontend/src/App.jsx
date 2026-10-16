import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
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
const CreateProject = lazy(() => import('./pages/Projects/CreateProject'));
const EvidenceList = lazy(() => import('./pages/Evidence/EvidenceList'));
const UploadEvidence = lazy(() => import('./pages/Evidence/UploadEvidence'));
const EvidenceDetail = lazy(() => import('./pages/Evidence/EvidenceDetail'));
const EvidenceGraph = lazy(() => import('./pages/Graph/EvidenceGraph'));
const ReviewQueue = lazy(() => import('./pages/Reviews/ReviewQueue'));
const ReviewInterface = lazy(() => import('./pages/Reviews/ReviewInterface'));
const CaseWorkspace = lazy(() => import('./pages/Reviews/CaseWorkspace'));
const Search = lazy(() => import('./pages/Search'));
const Profile = lazy(() => import('./pages/Profile'));
const AdminDashboard = lazy(() => import('./pages/Admin/AdminDashboard'));

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
        <Suspense fallback={<LoadingFallback />}>
          <Routes>
            {/* Public routes */}
            <Route path="/login" element={<Login />} />

            {/* Protected routes */}
            <Route element={<ProtectedRoute />}>
              <Route element={<Layout />}>
                <Route path="/" element={<Navigate to="/dashboard" replace />} />
                <Route path="/dashboard" element={<Dashboard />} />

                {/* Project Routes */}
                <Route path="/projects" element={<ProjectsList />} />
                <Route path="/projects/create" element={<CreateProject />} />
                <Route path="/projects/:id" element={<ProjectDetail />} />

                {/* Evidence Routes */}
                <Route path="/evidence" element={<EvidenceList />} />
                <Route path="/evidence/upload" element={<UploadEvidence />} />
                <Route path="/evidence/:id" element={<EvidenceDetail />} />

                {/* Evidence Graph Route */}
                <Route path="/graph" element={<EvidenceGraph />} />

                {/* Review Routes (PoA PWA Specification) */}
                <Route path="/review" element={<ReviewQueue />} />
                <Route path="/reviews" element={<ReviewQueue />} />
                <Route path="/review/case" element={<CaseWorkspace />} />
                <Route path="/review/:id" element={<ReviewInterface />} />

                {/* Search & Profile Routes */}
                <Route path="/search" element={<Search />} />
                <Route path="/profile" element={<Profile />} />
                <Route path="/profile/edit" element={<div className="p-4">Edit Profile (To be built)</div>} />

                {/* Admin Routes */}
                <Route path="/admin" element={<AdminDashboard />} />
              </Route>
            </Route>
          </Routes>
        </Suspense>
      </Router>
    </AuthProvider>
  );
}

export default App;
