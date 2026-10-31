import { useState, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { formatDate } from '../utils/helpers';
import { SearchIcon, DownloadIcon, FilterIcon, GraphIcon, AlertIcon, CheckIcon } from '../components/common/Icon';

function Search() {
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedSchemes, setSelectedSchemes] = useState([]);
  const [selectedStates, setSelectedStates] = useState([]);
  const [selectedStatuses, setSelectedStatuses] = useState([]);
  const [geofenceFilter, setGeofenceFilter] = useState('all'); // 'all', 'compliant', 'out_of_bounds'
  const [duplicateFilter, setDuplicateFilter] = useState('all'); // 'all', 'duplicate_flagged', 'clear'
  const [viewMode, setViewMode] = useState('table'); // 'table' or 'cards'

  // Authoritative Multi-Signal Repository Search Corpus (ADR Section 10 & 13)
  const evidenceCorpus = [
    {
      id: 'EVD-001',
      case_id: 'case-001-pmgsy',
      project_id: 'PRJ-001',
      project_name: 'PMGSY Phase 1 Road Works',
      scheme: 'Pradhan Mantri Gram Sadak Yojana',
      department: 'Ministry of Rural Development',
      activity: 'Road Sub-base Gravel Compaction',
      status: 'validated',
      type: 'image/jpeg',
      captured_at: '2024-02-15T10:30:00Z',
      sha256: 'c3ab8ff13720e8ad9047dd39466b3c8974e592c2fa383d4a3960714caef0c4f2',
      location: 'Pune District, Maharashtra',
      state: 'Maharashtra',
      officer: 'John Doe (Divisional Inspector)',
      geofence_status: 'COMPLIANT',
      has_duplicate_anomaly: false,
      decision: 'PENDING_REVIEW'
    },
    {
      id: 'EVD-002',
      case_id: 'case-001-pmgsy',
      project_id: 'PRJ-001',
      project_name: 'PMGSY Phase 1 Road Works',
      scheme: 'Pradhan Mantri Gram Sadak Yojana',
      department: 'Ministry of Rural Development',
      activity: 'Bitumen Asphalt Surface Pouring',
      status: 'validated',
      type: 'image/jpeg',
      captured_at: '2024-02-18T14:20:00Z',
      sha256: '7b2a9e40183fdc329810a9f848201ac495a8e10034b1235cb99ef01a8843c089',
      location: 'Pune District, Maharashtra',
      state: 'Maharashtra',
      officer: 'Jane Smith (Supervising Engineer)',
      geofence_status: 'COMPLIANT',
      has_duplicate_anomaly: false,
      decision: 'PENDING_REVIEW'
    },
    {
      id: 'EVD-003',
      case_id: 'case-002-solar',
      project_id: 'PRJ-002',
      project_name: 'Solar Street Light Installation',
      scheme: 'Solar Energy Programme',
      department: 'Ministry of New & Renewable Energy',
      activity: 'PV Module Luminaire Mounting',
      status: 'quarantine_flagged',
      type: 'image/jpeg',
      captured_at: '2024-02-20T09:45:00Z',
      sha256: '8f43a992e564177b89d4d2320b99ac18721539bb409e5b7c7fa91823bb0d0821',
      location: 'Surat District, Gujarat',
      state: 'Gujarat',
      officer: 'Raj Kumar (Contractor Liaison)',
      geofence_status: 'OUT_OF_BOUNDS',
      has_duplicate_anomaly: true,
      anomaly_title: 'Cross-Project pHash Duplicate (89% overlap with EVD-001 in PRJ-001)',
      decision: 'INVESTIGATING'
    },
    {
      id: 'EVD-004',
      case_id: 'case-003-water',
      project_id: 'PRJ-003',
      project_name: 'Community Water Tank Construction',
      scheme: 'Jal Jeevan Mission',
      department: 'Department of Drinking Water & Sanitation',
      activity: 'RCC Storage Tank Foundation Sealing',
      status: 'uploaded_quarantine',
      type: 'image/jpeg',
      captured_at: '2024-02-22T16:10:00Z',
      sha256: 'a12bc9034f828e10091873ea8901bce2674e1199a0b4528172ce4091ab5421ef',
      location: 'Jaipur District, Rajasthan',
      state: 'Rajasthan',
      officer: 'Amit Verma (Field Officer)',
      geofence_status: 'COMPLIANT',
      has_duplicate_anomaly: false,
      decision: 'OPEN'
    },
    {
      id: 'EVD-005',
      case_id: 'case-005-health',
      project_id: 'PRJ-005',
      project_name: 'Community Health Center',
      scheme: 'National Health Mission',
      department: 'Ministry of Health & Family Welfare',
      activity: 'Perimeter Boundary Excavation',
      status: 'validated',
      type: 'image/jpeg',
      captured_at: '2024-02-26T08:30:00Z',
      sha256: '55e810a9f24b81c2039ab6601dc892711094328fa8b4e019c438201fa8843ce1',
      location: 'Lucknow District, Uttar Pradesh',
      state: 'Uttar Pradesh',
      officer: 'Kavita Singh (Field Officer)',
      geofence_status: 'COMPLIANT',
      has_duplicate_anomaly: false,
      decision: 'DECISION_PENDING'
    }
  ];

  const schemes = [
    'Pradhan Mantri Gram Sadak Yojana',
    'Jal Jeevan Mission',
    'Solar Energy Programme',
    'National Health Mission',
  ];

  const states = ['Maharashtra', 'Gujarat', 'Rajasthan', 'Uttar Pradesh'];

  const filteredData = useMemo(() => {
    return evidenceCorpus.filter(item => {
      const q = searchTerm.toLowerCase();
      const matchesSearch =
        !searchTerm ||
        item.id.toLowerCase().includes(q) ||
        item.project_name.toLowerCase().includes(q) ||
        item.activity.toLowerCase().includes(q) ||
        item.location.toLowerCase().includes(q) ||
        item.sha256.toLowerCase().includes(q);

      const matchesScheme = selectedSchemes.length === 0 || selectedSchemes.includes(item.scheme);
      const matchesState = selectedStates.length === 0 || selectedStates.includes(item.state);
      const matchesStatus = selectedStatuses.length === 0 || selectedStatuses.includes(item.status);

      const matchesGeofence =
        geofenceFilter === 'all' ||
        (geofenceFilter === 'compliant' && item.geofence_status === 'COMPLIANT') ||
        (geofenceFilter === 'out_of_bounds' && item.geofence_status === 'OUT_OF_BOUNDS');

      const matchesDuplicate =
        duplicateFilter === 'all' ||
        (duplicateFilter === 'duplicate_flagged' && item.has_duplicate_anomaly) ||
        (duplicateFilter === 'clear' && !item.has_duplicate_anomaly);

      return matchesSearch && matchesScheme && matchesState && matchesStatus && matchesGeofence && matchesDuplicate;
    });
  }, [searchTerm, selectedSchemes, selectedStates, selectedStatuses, geofenceFilter, duplicateFilter]);

  const toggleScheme = (sc) => {
    setSelectedSchemes(prev => prev.includes(sc) ? prev.filter(x => x !== sc) : [...prev, sc]);
  };

  const toggleState = (st) => {
    setSelectedStates(prev => prev.includes(st) ? prev.filter(x => x !== st) : [...prev, st]);
  };

  return (
    <div style={{
      padding: '1.75rem 2rem',
      width: '100%',
      boxSizing: 'border-box',
      backgroundColor: 'var(--govt-gray-off-white)',
    }}>
      {/* Header */}
      <div style={{ marginBottom: '1.75rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
          <span style={{ color: 'var(--govt-blue-primary)' }}><SearchIcon /></span>
          <h1 style={{
            margin: 0,
            color: 'var(--govt-blue-dark)',
            fontSize: '1.65rem',
            fontWeight: 700,
            letterSpacing: '-0.02em'
          }}>
            Multi-Signal Intelligence & Evidence Search
          </h1>
        </div>
        <p style={{
          margin: '0.35rem 0 0 0',
          color: 'var(--govt-gray-dark)',
          fontSize: '0.875rem'
        }}>
          Query cross-scheme evidence by SHA-256 digest, geofence containment, perceptual hash similarity, and jurisdiction.
        </p>
      </div>

      {/* Main Search Input */}
      <div style={{
        backgroundColor: 'var(--govt-white)',
        padding: '1.25rem 1.5rem',
        borderRadius: 'var(--radius-lg)',
        boxShadow: 'var(--shadow-sm)',
        border: '1px solid var(--govt-gray-medium)',
        marginBottom: '1.5rem'
      }}>
        <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
          <input
            type="text"
            placeholder="Search by full or partial SHA-256 hash, Evidence ID, Project, or Taluka..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            style={{
              flex: '1 1 360px',
              padding: '0.75rem 1rem',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--govt-gray-medium)',
              fontSize: '0.9rem',
              outline: 'none',
              boxSizing: 'border-box'
            }}
          />
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button
              type="button"
              onClick={() => setViewMode(viewMode === 'table' ? 'cards' : 'table')}
              style={{
                padding: '0.75rem 1rem',
                backgroundColor: 'var(--govt-white)',
                border: '1px solid var(--govt-gray-medium)',
                borderRadius: 'var(--radius-md)',
                fontSize: '0.85rem',
                fontWeight: 600,
                color: 'var(--govt-blue-dark)',
                cursor: 'pointer'
              }}
            >
              Mode: {viewMode === 'table' ? 'Table View' : 'Card View'}
            </button>
            {(searchTerm || selectedSchemes.length > 0 || selectedStates.length > 0 || geofenceFilter !== 'all' || duplicateFilter !== 'all') && (
              <button
                type="button"
                onClick={() => {
                  setSearchTerm('');
                  setSelectedSchemes([]);
                  setSelectedStates([]);
                  setSelectedStatuses([]);
                  setGeofenceFilter('all');
                  setDuplicateFilter('all');
                }}
                style={{
                  padding: '0.75rem 1rem',
                  backgroundColor: 'transparent',
                  border: 'none',
                  color: 'var(--govt-blue-primary)',
                  fontSize: '0.85rem',
                  fontWeight: 600,
                  cursor: 'pointer'
                }}
              >
                Reset All
              </button>
            )}
          </div>
        </div>

        {/* Filter Chips Bar */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1.25rem', marginTop: '1.25rem', paddingTop: '1rem', borderTop: '1px solid var(--govt-gray-medium)' }}>
          {/* Schemes */}
          <div>
            <span style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--govt-gray-dark)', textTransform: 'uppercase', display: 'block', marginBottom: '0.35rem' }}>
              Filter Scheme:
            </span>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.35rem' }}>
              {schemes.map(sc => {
                const active = selectedSchemes.includes(sc);
                return (
                  <button
                    key={sc}
                    type="button"
                    onClick={() => toggleScheme(sc)}
                    style={{
                      padding: '0.25rem 0.6rem',
                      borderRadius: '9999px',
                      fontSize: '0.72rem',
                      fontWeight: 600,
                      border: active ? '1px solid var(--govt-blue-primary)' : '1px solid var(--govt-gray-medium)',
                      backgroundColor: active ? 'var(--govt-blue-light)' : 'var(--govt-gray-light)',
                      color: active ? 'var(--govt-blue-primary)' : 'var(--govt-gray-text)',
                      cursor: 'pointer'
                    }}
                  >
                    {sc.split(' ')[0]} {sc.split(' ')[1] || ''}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Geospatial Geofence Filter */}
          <div>
            <span style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--govt-gray-dark)', textTransform: 'uppercase', display: 'block', marginBottom: '0.35rem' }}>
              Geofence Status:
            </span>
            <select
              value={geofenceFilter}
              onChange={(e) => setGeofenceFilter(e.target.value)}
              style={{
                padding: '0.35rem 0.65rem',
                borderRadius: 'var(--radius-md)',
                border: '1px solid var(--govt-gray-medium)',
                fontSize: '0.75rem',
                backgroundColor: 'var(--govt-white)'
              }}
            >
              <option value="all">All Coordinates</option>
              <option value="compliant">Compliant Within Bounds</option>
              <option value="out_of_bounds">Out of Bounds Variance</option>
            </select>
          </div>

          {/* Duplicate Intelligence */}
          <div>
            <span style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--govt-gray-dark)', textTransform: 'uppercase', display: 'block', marginBottom: '0.35rem' }}>
              Duplicate Overlap:
            </span>
            <select
              value={duplicateFilter}
              onChange={(e) => setDuplicateFilter(e.target.value)}
              style={{
                padding: '0.35rem 0.65rem',
                borderRadius: 'var(--radius-md)',
                border: '1px solid var(--govt-gray-medium)',
                fontSize: '0.75rem',
                backgroundColor: 'var(--govt-white)'
              }}
            >
              <option value="all">All Items</option>
              <option value="duplicate_flagged">pHash Duplicate Flagged</option>
              <option value="clear">Unique / No Overlap</option>
            </select>
          </div>
        </div>
      </div>

      {/* Results Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <p style={{ margin: 0, fontSize: '0.85rem', color: 'var(--govt-gray-dark)' }}>
          Showing <strong>{filteredData.length}</strong> matching evidence records
        </p>
      </div>

      {/* Results: Table or Cards */}
      {filteredData.length === 0 ? (
        <div style={{
          backgroundColor: 'var(--govt-white)',
          padding: '3rem',
          textAlign: 'center',
          borderRadius: 'var(--radius-lg)',
          border: '1px solid var(--govt-gray-medium)'
        }}>
          <p style={{ margin: 0, fontSize: '1rem', fontWeight: 600, color: 'var(--govt-blue-dark)' }}>
            No evidence records matched your multi-signal filter query.
          </p>
          <p style={{ margin: '0.4rem 0 0', fontSize: '0.82rem', color: 'var(--govt-gray-dark)' }}>
            Try searching with a shorter SHA-256 prefix or relaxing the geofence filters.
          </p>
        </div>
      ) : viewMode === 'table' ? (
        <div style={{
          backgroundColor: 'var(--govt-white)',
          borderRadius: 'var(--radius-lg)',
          boxShadow: 'var(--shadow-sm)',
          border: '1px solid var(--govt-gray-medium)',
          overflow: 'hidden'
        }}>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.85rem' }}>
              <thead>
                <tr style={{
                  backgroundColor: 'var(--govt-gray-light)',
                  borderBottom: '2px solid var(--govt-gray-medium)',
                  color: 'var(--govt-gray-dark)',
                  fontSize: '0.75rem',
                  textTransform: 'uppercase'
                }}>
                  <th style={{ padding: '0.85rem 1.25rem' }}>Evidence ID</th>
                  <th style={{ padding: '0.85rem 1rem' }}>Scheme & Project</th>
                  <th style={{ padding: '0.85rem 1rem' }}>SHA-256 Digest</th>
                  <th style={{ padding: '0.85rem 1rem' }}>Geofence</th>
                  <th style={{ padding: '0.85rem 1rem' }}>Multi-Signal Flags</th>
                  <th style={{ padding: '0.85rem 1.25rem', textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredData.map(item => (
                  <tr key={item.id} style={{ borderBottom: '1px solid var(--govt-gray-medium)' }}>
                    <td style={{ padding: '0.9rem 1.25rem' }}>
                      <div style={{ fontFamily: 'monospace', fontWeight: 700, color: 'var(--govt-blue-primary)' }}>
                        {item.id}
                      </div>
                      <div style={{ fontSize: '0.72rem', color: 'var(--govt-gray-dark)' }}>
                        {formatDate(item.captured_at)}
                      </div>
                    </td>
                    <td style={{ padding: '0.9rem 1rem' }}>
                      <div style={{ fontWeight: 600, color: 'var(--govt-blue-dark)', fontSize: '0.85rem' }}>
                        {item.project_name}
                      </div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--govt-gray-text)' }}>
                        {item.scheme} • {item.location}
                      </div>
                    </td>
                    <td style={{ padding: '0.9rem 1rem', maxWidth: '240px' }}>
                      <div style={{
                        fontFamily: 'monospace',
                        fontSize: '0.72rem',
                        backgroundColor: 'var(--govt-gray-light)',
                        padding: '0.25rem 0.45rem',
                        borderRadius: 'var(--radius-sm)',
                        wordBreak: 'break-all',
                        color: 'var(--govt-blue-dark)'
                      }}>
                        {item.sha256}
                      </div>
                    </td>
                    <td style={{ padding: '0.9rem 1rem' }}>
                      <span style={{
                        fontSize: '0.75rem',
                        fontWeight: 700,
                        color: item.geofence_status === 'COMPLIANT' ? 'var(--govt-success-text)' : 'var(--govt-danger-text)'
                      }}>
                        {item.geofence_status === 'COMPLIANT' ? '✓ In Bounds' : '⚠ Out of Bounds'}
                      </span>
                    </td>
                    <td style={{ padding: '0.9rem 1rem' }}>
                      {item.has_duplicate_anomaly ? (
                        <span style={{
                          padding: '0.15rem 0.5rem',
                          borderRadius: 'var(--radius-sm)',
                          fontSize: '0.72rem',
                          fontWeight: 700,
                          backgroundColor: 'var(--govt-danger-light)',
                          color: 'var(--govt-danger-text)'
                        }}>
                          ⚠ Duplicate Flagged
                        </span>
                      ) : (
                        <span style={{ fontSize: '0.75rem', color: 'var(--govt-gray-dark)' }}>
                          ✓ Unique
                        </span>
                      )}
                    </td>
                    <td style={{ padding: '0.9rem 1.25rem', textAlign: 'right' }}>
                      <div style={{ display: 'inline-flex', gap: '0.5rem' }}>
                        <Link
                          to={`/evidence/${item.id}`}
                          style={{
                            fontSize: '0.8rem',
                            fontWeight: 600,
                            color: 'var(--govt-blue-primary)',
                            textDecoration: 'none'
                          }}
                        >
                          Inspect
                        </Link>
                        {item.case_id && (
                          <Link
                            to={`/review/case?id=${item.case_id}`}
                            style={{
                              fontSize: '0.8rem',
                              fontWeight: 600,
                              color: 'var(--govt-blue-dark)',
                              textDecoration: 'none'
                            }}
                          >
                            Case →
                          </Link>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        /* Cards View */
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
          gap: '1.25rem'
        }}>
          {filteredData.map(item => (
            <div key={item.id} style={{
              backgroundColor: 'var(--govt-white)',
              borderRadius: 'var(--radius-lg)',
              boxShadow: 'var(--shadow-sm)',
              border: '1px solid var(--govt-gray-medium)',
              padding: '1.25rem',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'space-between'
            }}>
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.4rem' }}>
                  <span style={{ fontFamily: 'monospace', fontWeight: 700, color: 'var(--govt-blue-primary)', fontSize: '0.82rem' }}>
                    {item.id}
                  </span>
                  <span style={{
                    fontSize: '0.72rem',
                    fontWeight: 700,
                    color: item.geofence_status === 'COMPLIANT' ? 'var(--govt-success-text)' : 'var(--govt-danger-text)'
                  }}>
                    {item.geofence_status}
                  </span>
                </div>
                <h4 style={{ margin: '0 0 0.35rem', fontSize: '0.92rem', fontWeight: 700, color: 'var(--govt-blue-dark)' }}>
                  {item.activity}
                </h4>
                <p style={{ margin: '0 0 0.75rem', fontSize: '0.78rem', color: 'var(--govt-gray-text)' }}>
                  {item.project_name} ({item.scheme})
                </p>
                <div style={{
                  backgroundColor: 'var(--govt-gray-off-white)',
                  padding: '0.45rem 0.6rem',
                  borderRadius: 'var(--radius-sm)',
                  fontFamily: 'monospace',
                  fontSize: '0.72rem',
                  wordBreak: 'break-all',
                  marginBottom: '0.75rem',
                  color: 'var(--govt-blue-dark)'
                }}>
                  {item.sha256.slice(0, 36)}...
                </div>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingTop: '0.75rem', borderTop: '1px solid var(--govt-gray-medium)' }}>
                <span style={{ fontSize: '0.72rem', color: 'var(--govt-gray-dark)' }}>
                  {formatDate(item.captured_at)}
                </span>
                <Link
                  to={`/evidence/${item.id}`}
                  style={{
                    fontSize: '0.8rem',
                    fontWeight: 600,
                    color: 'var(--govt-blue-primary)',
                    textDecoration: 'none'
                  }}
                >
                  View Details →
                </Link>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default Search;
