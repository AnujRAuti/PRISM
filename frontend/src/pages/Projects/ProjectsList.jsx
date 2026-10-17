import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { formatDate } from '../../utils/helpers';
import { PlusIcon, ProjectIcon, EvidenceIcon, ReviewIcon } from '../../components/common/Icon';
import { projectApi } from '../../services/api';

function ProjectsList() {
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [schemeFilter, setSchemeFilter] = useState('all');

  // Authoritative Demonstration Project Portfolio (ADR Section 9 & 23)
  const defaultProjects = [
    {
      id: 'PRJ-001',
      name: 'PMGSY Phase 1 Road Works — Taluka Baramati',
      scheme: 'Pradhan Mantri Gram Sadak Yojana',
      department: 'Ministry of Rural Development',
      status: 'ACTIVE',
      location: 'Pune District, Maharashtra',
      activities_count: 5,
      evidence_count: 45,
      active_cases: 1,
      start_date: '2024-01-01',
      target_date: '2024-12-31',
      supervisor: 'Sunita Patel'
    },
    {
      id: 'PRJ-002',
      name: 'Surat Ward 4 Solar Street Luminaire Installation',
      scheme: 'Solar Energy Programme',
      department: 'Ministry of New & Renewable Energy',
      status: 'ACTIVE',
      location: 'Surat District, Gujarat',
      activities_count: 3,
      evidence_count: 28,
      active_cases: 1,
      start_date: '2024-02-01',
      target_date: '2024-08-31',
      supervisor: 'Sunita Patel'
    },
    {
      id: 'PRJ-003',
      name: 'Community Water Tank Construction',
      scheme: 'Jal Jeevan Mission',
      department: 'Department of Drinking Water & Sanitation',
      status: 'ACTIVE',
      location: 'Jaipur District, Rajasthan',
      activities_count: 4,
      evidence_count: 67,
      active_cases: 1,
      start_date: '2023-06-01',
      target_date: '2024-06-30',
      supervisor: 'Amit Verma'
    },
    {
      id: 'PRJ-004',
      name: 'Primary School Structural Roof Renovation',
      scheme: 'Samagra Shiksha Abhiyan',
      department: 'Department of School Education & Literacy',
      status: 'COMPLETED',
      location: 'Mysuru District, Karnataka',
      activities_count: 4,
      evidence_count: 18,
      active_cases: 0,
      start_date: '2023-10-01',
      target_date: '2024-02-28',
      supervisor: 'Dr. Ramesh Sharma'
    },
    {
      id: 'PRJ-005',
      name: 'Community Health Sub-center Perimeter Foundation',
      scheme: 'National Health Mission',
      department: 'Ministry of Health & Family Welfare',
      status: 'ACTIVE',
      location: 'Lucknow District, Uttar Pradesh',
      activities_count: 3,
      evidence_count: 12,
      active_cases: 1,
      start_date: '2024-02-01',
      target_date: '2024-12-31',
      supervisor: 'Kavita Singh'
    },
  ];

  useEffect(() => {
    projectApi.getAll()
      .then(res => {
        if (res.data && Array.isArray(res.data.items)) {
          setProjects(res.data.items);
        } else if (Array.isArray(res.data)) {
          setProjects(res.data);
        } else {
          setProjects(defaultProjects);
        }
      })
      .catch(() => {
        setProjects(defaultProjects);
      })
      .finally(() => {
        setLoading(false);
      });
  }, []);

  const schemes = [
    'Pradhan Mantri Gram Sadak Yojana',
    'Jal Jeevan Mission',
    'Solar Energy Programme',
    'Samagra Shiksha Abhiyan',
    'National Health Mission'
  ];

  const filteredProjects = projects.filter(project => {
    const q = searchTerm.toLowerCase();
    const matchesSearch =
      project.id.toLowerCase().includes(q) ||
      project.name.toLowerCase().includes(q) ||
      project.scheme.toLowerCase().includes(q) ||
      project.location.toLowerCase().includes(q);

    const matchesScheme = schemeFilter === 'all' || project.scheme === schemeFilter;
    return matchesSearch && matchesScheme;
  });

  if (loading) {
    return (
      <div style={{ padding: '3rem', textAlign: 'center' }}>
        <div className="spinner" style={{ width: '40px', height: '40px', margin: '0 auto 1rem' }}></div>
        <p style={{ color: 'var(--govt-gray-dark)' }}>Loading public works projects...</p>
      </div>
    );
  }

  return (
    <div style={{
      padding: '1.75rem 2rem',
      width: '100%',
      boxSizing: 'border-box',
      backgroundColor: 'var(--govt-gray-off-white)',
    }}>
      {/* Header */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'flex-start',
        marginBottom: '1.75rem',
        flexWrap: 'wrap',
        gap: '1rem'
      }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <span style={{ color: 'var(--govt-blue-primary)' }}><ProjectIcon /></span>
            <h1 style={{
              margin: 0,
              color: 'var(--govt-blue-dark)',
              fontSize: '1.65rem',
              fontWeight: 700,
              letterSpacing: '-0.02em'
            }}>
              Monitored Public Infrastructure Projects
            </h1>
          </div>
          <p style={{
            margin: '0.35rem 0 0 0',
            color: 'var(--govt-gray-dark)',
            fontSize: '0.875rem'
          }}>
            Top-level operational domain objects (ADR §9). Projects anchor activities, canonical claims, and geofence baselines.
          </p>
        </div>

        <Link
          to="/projects/create"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.5rem',
            padding: '0.625rem 1.15rem',
            borderRadius: 'var(--radius-md)',
            backgroundColor: 'var(--govt-blue-primary)',
            color: '#ffffff',
            textDecoration: 'none',
            fontSize: '0.875rem',
            fontWeight: 600,
            boxShadow: 'var(--shadow-sm)'
          }}
        >
          + Register New Project
        </Link>
      </div>

      {/* Filter and Search Bar */}
      <div style={{
        backgroundColor: 'var(--govt-white)',
        padding: '1.25rem 1.5rem',
        borderRadius: 'var(--radius-lg)',
        boxShadow: 'var(--shadow-sm)',
        border: '1px solid var(--govt-gray-medium)',
        marginBottom: '1.5rem',
        display: 'flex',
        flexWrap: 'wrap',
        gap: '1rem',
        alignItems: 'center'
      }}>
        <div style={{ flex: '1 1 320px' }}>
          <input
            type="text"
            placeholder="Search by project title, scheme, jurisdiction, or Project ID..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            style={{
              width: '100%',
              padding: '0.625rem 0.85rem',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--govt-gray-medium)',
              fontSize: '0.875rem',
              boxSizing: 'border-box',
              outline: 'none'
            }}
          />
        </div>

        <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
          <select
            value={schemeFilter}
            onChange={(e) => setSchemeFilter(e.target.value)}
            style={{
              padding: '0.625rem 0.85rem',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--govt-gray-medium)',
              fontSize: '0.85rem',
              backgroundColor: 'var(--govt-white)'
            }}
          >
            <option value="all">All Schemes</option>
            {schemes.map(s => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>

          {(searchTerm || schemeFilter !== 'all') && (
            <button
              type="button"
              onClick={() => { setSearchTerm(''); setSchemeFilter('all'); }}
              style={{
                background: 'none',
                border: 'none',
                color: 'var(--govt-blue-primary)',
                fontSize: '0.85rem',
                cursor: 'pointer',
                fontWeight: 600
              }}
            >
              Reset
            </button>
          )}
        </div>
      </div>

      {/* Projects Grid Cards */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))',
        gap: '1.5rem'
      }}>
        {filteredProjects.map(p => (
          <div
            key={p.id}
            style={{
              backgroundColor: 'var(--govt-white)',
              borderRadius: 'var(--radius-lg)',
              boxShadow: 'var(--shadow-sm)',
              border: '1px solid var(--govt-gray-medium)',
              padding: '1.5rem',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'space-between',
              transition: 'border-color 0.15s ease'
            }}
          >
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                <span style={{ fontFamily: 'monospace', fontWeight: 700, color: 'var(--govt-blue-primary)', fontSize: '0.82rem' }}>
                  {p.id}
                </span>
                <span style={{
                  padding: '0.15rem 0.55rem',
                  borderRadius: '9999px',
                  fontSize: '0.72rem',
                  fontWeight: 700,
                  backgroundColor: p.status === 'COMPLETED' ? 'var(--govt-info-light)' : 'var(--govt-success-light)',
                  color: p.status === 'COMPLETED' ? 'var(--govt-info-text)' : 'var(--govt-success-text)'
                }}>
                  {p.status}
                </span>
              </div>

              <h3 style={{ margin: '0 0 0.4rem', fontSize: '1.05rem', fontWeight: 700, color: 'var(--govt-blue-dark)' }}>
                {p.name}
              </h3>
              <p style={{ margin: '0 0 0.85rem', fontSize: '0.82rem', color: 'var(--govt-gray-text)' }}>
                {p.scheme} • {p.department}
              </p>

              <div style={{
                backgroundColor: 'var(--govt-gray-off-white)',
                padding: '0.75rem 1rem',
                borderRadius: 'var(--radius-md)',
                display: 'grid',
                gridTemplateColumns: '1fr 1fr',
                gap: '0.5rem',
                fontSize: '0.78rem',
                marginBottom: '1rem'
              }}>
                <div>
                  <span style={{ color: 'var(--govt-gray-dark)' }}>Jurisdiction:</span>
                  <p style={{ margin: '0.1rem 0 0', fontWeight: 600, color: 'var(--govt-blue-dark)' }}>{p.location}</p>
                </div>
                <div>
                  <span style={{ color: 'var(--govt-gray-dark)' }}>Supervisor:</span>
                  <p style={{ margin: '0.1rem 0 0', fontWeight: 600, color: 'var(--govt-blue-dark)' }}>{p.supervisor}</p>
                </div>
                <div>
                  <span style={{ color: 'var(--govt-gray-dark)' }}>Activities:</span>
                  <p style={{ margin: '0.1rem 0 0', fontWeight: 600, color: 'var(--govt-blue-dark)' }}>{p.activities_count} work units</p>
                </div>
                <div>
                  <span style={{ color: 'var(--govt-gray-dark)' }}>Evidence Ledger:</span>
                  <p style={{ margin: '0.1rem 0 0', fontWeight: 600, color: 'var(--govt-blue-dark)' }}>{p.evidence_count} items</p>
                </div>
              </div>
            </div>

            <div style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              paddingTop: '0.85rem',
              borderTop: '1px solid var(--govt-gray-medium)'
            }}>
              <div>
                {p.active_cases > 0 ? (
                  <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--govt-warning-text)' }}>
                    ● {p.active_cases} Active Review Case
                  </span>
                ) : (
                  <span style={{ fontSize: '0.75rem', color: 'var(--govt-success-text)' }}>
                    ✓ No Review Backlog
                  </span>
                )}
              </div>
              <Link
                to={`/projects/${p.id}`}
                style={{
                  fontSize: '0.82rem',
                  fontWeight: 600,
                  color: 'var(--govt-blue-primary)',
                  textDecoration: 'none'
                }}
              >
                Inspect Project →
              </Link>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default ProjectsList;
