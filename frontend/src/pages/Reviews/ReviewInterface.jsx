import { useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';

// Canonical redirect to Section 4.4 Case URL contract: /review/case?id=UUID
function ReviewInterface() {
  const { id } = useParams();
  const navigate = useNavigate();

  useEffect(() => {
    navigate(`/review/case?id=${id || 'case-001-pmgsy'}`, { replace: true });
  }, [id, navigate]);

  return (
    <div style={{ padding: '3rem', textAlign: 'center' }}>
      <div className="spinner" style={{ width: '40px', height: '40px', margin: '0 auto 1rem' }}></div>
      <p style={{ color: 'var(--govt-gray-dark)' }}>Redirecting to Case Workspace...</p>
    </div>
  );
}

export default ReviewInterface;
