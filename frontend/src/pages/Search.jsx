import { useState, useEffect, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { formatDate } from '../utils/helpers';
import { DownloadIcon, SearchIcon, FilterIcon, GraphIcon, AlertIcon } from '../components/common/Icon';

function Search() {
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedSchemes, setSelectedSchemes] = useState([]);
  const [selectedStates, setSelectedStates] = useState([]);
  const [selectedStatuses, setSelectedStatuses] = useState([]);
  const [minIntegrity, setMinIntegrity] = useState(0);
  const [maxRisk, setMaxRisk] = useState(100);
  const [anomalyOnly, setAnomalyOnly] = useState(false);
  const [sortBy, setSortBy] = useState('risk_desc'); // 'risk_desc', 'risk_asc', 'date_desc', 'integrity_desc'
  const [viewMode, setViewMode] = useState('cards'); // 'cards' or 'table'
  const [loading, setLoading] = useState(true);

  // Susasan E-Citizen Charter mock repository
  const evidenceData = [
    {
      id: 'EVD-001',
      project_id: 'PRJ-001',
      project_name: 'Rural Road Construction - Phase 1',
      scheme: 'Pradhan Mantri Gram Sadak Yojana',
      department: 'Ministry of Rural Development',
      activity: 'Road Sub-base Gravel Compaction',
      status: 'approved',
      type: 'image',
      captured_at: '2024-02-15T10:30:00Z',
      integrity_score: 92,
      risk_score: 15,
      location: 'Pune District, Maharashtra',
      state: 'Maharashtra',
      officer: 'John Doe (Divisional Inspector)',
      sha256: 'c3ab8ff13720e8ad9047dd39466b3c89',
      has_anomaly: false,
      geofence_status: 'Within Boundary',
    },
    {
      id: 'EVD-002',
      project_id: 'PRJ-001',
      project_name: 'Rural Road Construction - Phase 1',
      scheme: 'Pradhan Mantri Gram Sadak Yojana',
      department: 'Ministry of Rural Development',
      activity: 'Bitumen Asphalt Surface Pouring',
      status: 'approved',
      type: 'image',
      captured_at: '2024-02-18T14:20:00Z',
      integrity_score: 88,
      risk_score: 22,
      location: 'Pune District, Maharashtra',
      state: 'Maharashtra',
      officer: 'Jane Smith (Supervising Engineer)',
      sha256: '7b2a9e40183fdc329810a9f848201ac4',
      has_anomaly: false,
      geofence_status: 'Within Boundary',
    },
    {
      id: 'EVD-003',
      project_id: 'PRJ-002',
      project_name: 'Solar Street Light Installation',
      scheme: 'Solar Energy Programme',
      department: 'Ministry of New & Renewable Energy',
      activity: 'PV Module Luminaire Mounting',
      status: 'flagged',
      type: 'image',
      captured_at: '2024-02-20T09:45:00Z',
      integrity_score: 45,
      risk_score: 78,
      location: 'Surat District, Gujarat',
      state: 'Gujarat',
      officer: 'Raj Kumar (Site Contractor)',
      sha256: '8f43a992e564177b89d4d2320b99ac18',
      has_anomaly: true,
      anomaly_title: 'Cross-Project Visual Duplicate (89% overlap with EVD-001 in PRJ-001)',
      geofence_status: '12.4 km Out of Bounds',
    },
    {
      id: 'EVD-004',
      project_id: 'PRJ-003',
      project_name: 'Community Water Tank Construction',
      scheme: 'Jal Jeevan Mission',
      department: 'Department of Drinking Water & Sanitation',
      activity: 'RCC Storage Tank Foundation Sealing',
      status: 'pending',
      type: 'image',
      captured_at: '2024-02-22T16:10:00Z',
      integrity_score: 75,
      risk_score: 30,
      location: 'Jaipur District, Rajasthan',
      state: 'Rajasthan',
      officer: 'Amit Verma (Field Officer)',
      sha256: 'a12bc9034f828e10091873ea8901bce2',
      has_anomaly: false,
      geofence_status: 'Within Boundary',
    },
    {
      id: 'EVD-005',
      project_id: 'PRJ-005',
      project_name: 'Community Health Sub-Center',
      scheme: 'National Health Mission',
      department: 'Ministry of Health & Family Welfare',
      activity: 'Primary Healthcare Outpatient Ward',
      status: 'approved',
      type: 'image',
      captured_at: '2024-03-01T11:00:00Z',
      integrity_score: 95,
      risk_score: 10,
      location: 'Varanasi District, Uttar Pradesh',
      state: 'Uttar Pradesh',
      officer: 'Priya Sharma (Medical Superintendent)',
      sha256: '9901bfd14820acbd7401928374a81b23',
      has_anomaly: false,
      geofence_status: 'Within Boundary',
    },
  ];

  const availableSchemes = [
    'Pradhan Mantri Gram Sadak Yojana',
    'Solar Energy Programme',
    'Jal Jeevan Mission',
    'National Health Mission',
  ];

  const availableStates = ['Maharashtra', 'Gujarat', 'Rajasthan', 'Uttar Pradesh'];
  const availableStatuses = [
    { label: 'Approved / Verified', value: 'approved', color: 'var(--govt-success)' },
    { label: 'Flagged / Anomaly', value: 'flagged', color: 'var(--govt-danger)' },
    { label: 'Pending Review', value: 'pending', color: 'var(--govt-warning)' },
  ];

  useEffect(() => {
    const timer = setTimeout(() => setLoading(false), 250);
    return () => clearTimeout(timer);
  }, []);

  // Multi-select toggle helper
  const toggleSelection = (list, setList, item) => {
    if (list.includes(item)) {
      setList(list.filter((x) => x !== item));
    } else {
      setList([...list, item]);
    }
  };

  // Reset filters
  const resetAllFilters = () => {
    setSearchTerm('');
    setSelectedSchemes([]);
    setSelectedStates([]);
    setSelectedStatuses([]);
    setMinIntegrity(0);
    setMaxRisk(100);
    setAnomalyOnly(false);
  };

  // Filtered and sorted evidence
  const filteredData = useMemo(() => {
    const res = evidenceData.filter((item) => {
      // Keyword query
      if (searchTerm.trim()) {
        const term = searchTerm.toLowerCase();
        const matches =
          item.id.toLowerCase().includes(term) ||
          item.project_name.toLowerCase().includes(term) ||
          item.scheme.toLowerCase().includes(term) ||
          item.activity.toLowerCase().includes(term) ||
          item.location.toLowerCase().includes(term) ||
          item.officer.toLowerCase().includes(term) ||
          item.sha256.toLowerCase().includes(term);
        if (!matches) return false;
      }

      // Schemes
      if (selectedSchemes.length > 0 && !selectedSchemes.includes(item.scheme)) return false;

      // States
      if (selectedStates.length > 0 && !selectedStates.includes(item.state)) return false;

      // Statuses
      if (selectedStatuses.length > 0 && !selectedStatuses.includes(item.status)) return false;

      // Scores
      if (item.integrity_score < minIntegrity) return false;
      if (item.risk_score > maxRisk) return false;

      // Anomaly
      if (anomalyOnly && !item.has_anomaly) return false;

      return true;
    });

    // Sort
    return res.sort((a, b) => {
      if (sortBy === 'risk_desc') return b.risk_score - a.risk_score;
      if (sortBy === 'risk_asc') return a.risk_score - b.risk_score;
      if (sortBy === 'integrity_desc') return b.integrity_score - a.integrity_score;
      if (sortBy === 'date_desc') return new Date(b.captured_at) - new Date(a.captured_at);
      return 0;
    });
  }, [searchTerm, selectedSchemes, selectedStates, selectedStatuses, minIntegrity, maxRisk, anomalyOnly, sortBy]);

  // Export handlers
  const exportCSV = () => {
    let csv = 'data:text/csv;charset=utf-8,ID,Project,Scheme,Department,Activity,Location,Status,Integrity,Risk,Officer,Date\r\n';
    filteredData.forEach((d) => {
      csv += `"${d.id}","${d.project_name}","${d.scheme}","${d.department}","${d.activity}","${d.location}","${d.status.toUpperCase()}",${d.integrity_score},${d.risk_score},"${d.officer}","${d.captured_at}"\r\n`;
    });
    const encoded = encodeURI(csv);
    const link = document.createElement('a');
    link.href = encoded;
    link.download = `prism_registry_export_${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const exportJSON = () => {
    const dataStr = 'data:text/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(filteredData, null, 2));
    const dl = document.createElement('a');
    dl.href = dataStr;
    dl.download = `prism_evidence_registry_${new Date().toISOString().slice(0, 10)}.json`;
    document.body.appendChild(dl);
    dl.click();
    dl.remove();
  };

  // Active filter count
  const activeFilterCount =
    (searchTerm ? 1 : 0) +
    selectedSchemes.length +
    selectedStates.length +
    selectedStatuses.length +
    (minIntegrity > 0 ? 1 : 0) +
    (maxRisk < 100 ? 1 : 0) +
    (anomalyOnly ? 1 : 0);

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '60vh', flexDirection: 'column' }}>
        <div className="spinner" style={{ width: '40px', height: '40px' }}></div>
        <p style={{ marginTop: '1rem', color: 'var(--govt-gray-dark)', fontSize: '0.9rem' }}>Loading Public Evidence Registry...</p>
      </div>
    );
  }

  return (
    <div style={{ padding: '1.75rem 2rem', width: '100%', boxSizing: 'border-box', backgroundColor: 'var(--govt-gray-off-white)' }}>
      {/* Top Banner: Title & Export Tools */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '1rem',
          marginBottom: '1.5rem',
          paddingBottom: '1.25rem',
          borderBottom: '1px solid var(--govt-gray-medium)',
        }}
      >
        <div>
          <h1 style={{ margin: 0, color: 'var(--govt-blue-dark)', fontSize: '1.65rem', fontWeight: '700', letterSpacing: '-0.02em' }}>
            Public Infrastructure Evidence & Audit Registry
          </h1>
          <p style={{ margin: '0.35rem 0 0 0', color: 'var(--govt-gray-dark)', fontSize: '0.875rem' }}>
            Multi-signal evidence verification, tamper-evident audit records, and anomaly discovery
          </p>
        </div>

        {/* Action Controls */}
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          <button
            onClick={exportCSV}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.4rem',
              backgroundColor: 'var(--govt-white)',
              color: 'var(--govt-blue-primary)',
              border: '1px solid var(--govt-gray-medium)',
              padding: '0.5rem 0.85rem',
              borderRadius: 'var(--radius-md)',
              fontSize: '0.85rem',
              fontWeight: '600',
              cursor: 'pointer',
              boxShadow: 'var(--shadow-xs)',
            }}
          >
            <DownloadIcon />
            CSV Export
          </button>
          <button
            onClick={exportJSON}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.4rem',
              backgroundColor: 'var(--govt-white)',
              color: 'var(--govt-blue-primary)',
              border: '1px solid var(--govt-gray-medium)',
              padding: '0.5rem 0.85rem',
              borderRadius: 'var(--radius-md)',
              fontSize: '0.85rem',
              fontWeight: '600',
              cursor: 'pointer',
              boxShadow: 'var(--shadow-xs)',
            }}
          >
            <DownloadIcon />
            JSON
          </button>
          <button
            onClick={() => window.print()}
            style={{
              backgroundColor: 'var(--govt-blue-primary)',
              color: '#ffffff',
              border: 'none',
              padding: '0.5rem 1rem',
              borderRadius: 'var(--radius-md)',
              fontSize: '0.85rem',
              fontWeight: '600',
              cursor: 'pointer',
              boxShadow: 'var(--shadow-xs)',
            }}
          >
            Print Registry
          </button>
        </div>
      </div>

      {/* Main Two-Column Layout: Susasan Advanced Filter Drawer on Left, Results on Right */}
      <div style={{ display: 'grid', gridTemplateColumns: '310px 1fr', gap: '1.5rem', alignItems: 'start' }}>
        {/* Left Column: Susasan Advanced Filter Panel */}
        <aside
          aria-label="Filter Panel"
          style={{
            backgroundColor: 'var(--govt-white)',
            borderRadius: 'var(--radius-lg)',
            border: '1px solid var(--govt-gray-medium)',
            padding: '1.25rem',
            boxShadow: 'var(--shadow-sm)',
            position: 'sticky',
            top: '84px',
          }}
        >
          {/* Filter Header & Active Count */}
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: '1rem',
              paddingBottom: '0.75rem',
              borderBottom: '1px solid var(--govt-gray-light)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <span style={{ color: 'var(--govt-blue-primary)' }}>
                <FilterIcon />
              </span>
              <strong style={{ fontSize: '0.95rem', color: 'var(--govt-gray-title)' }}>
                Advanced Filters
              </strong>
            </div>

            {activeFilterCount > 0 && (
              <button
                onClick={resetAllFilters}
                style={{
                  backgroundColor: 'transparent',
                  border: 'none',
                  color: 'var(--govt-danger)',
                  fontSize: '0.75rem',
                  fontWeight: '600',
                  cursor: 'pointer',
                  padding: '0',
                }}
              >
                Reset All ({activeFilterCount})
              </button>
            )}
          </div>

          {/* Quick Search Input */}
          <div style={{ position: 'relative', marginBottom: '1.25rem' }}>
            <input
              type="text"
              placeholder="Search keyword, scheme..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              style={{
                width: '100%',
                padding: '0.55rem 0.75rem 0.55rem 2.25rem',
                border: '1px solid var(--govt-gray-medium)',
                borderRadius: 'var(--radius-md)',
                fontSize: '0.85rem',
                boxSizing: 'border-box',
                backgroundColor: 'var(--govt-gray-off-white)',
              }}
            />
            <span
              style={{
                position: 'absolute',
                left: '8px',
                top: '50%',
                transform: 'translateY(-50%)',
                color: 'var(--govt-gray-dark)',
              }}
            >
              <SearchIcon />
            </span>
          </div>

          {/* Accordion 1: Scheme / Municipal Service */}
          <div style={{ marginBottom: '1.25rem' }}>
            <label
              style={{
                display: 'block',
                fontSize: '0.75rem',
                fontWeight: '700',
                color: 'var(--govt-gray-dark)',
                textTransform: 'uppercase',
                letterSpacing: '0.5px',
                marginBottom: '0.5rem',
              }}
            >
              Government Scheme / Charter
            </label>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
              {availableSchemes.map((sc) => {
                const count = evidenceData.filter((e) => e.scheme === sc).length;
                const isChecked = selectedSchemes.includes(sc);
                return (
                  <label
                    key={sc}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      fontSize: '0.825rem',
                      color: isChecked ? 'var(--govt-blue-primary)' : 'var(--govt-gray-text)',
                      fontWeight: isChecked ? '600' : '400',
                      cursor: 'pointer',
                      padding: '0.25rem 0.4rem',
                      borderRadius: 'var(--radius-sm)',
                      backgroundColor: isChecked ? 'var(--govt-blue-light)' : 'transparent',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
                      <input
                        type="checkbox"
                        checked={isChecked}
                        onChange={() => toggleSelection(selectedSchemes, setSelectedSchemes, sc)}
                        style={{ accentColor: 'var(--govt-blue-primary)' }}
                      />
                      <span>{sc}</span>
                    </div>
                    <span style={{ fontSize: '0.72rem', color: 'var(--govt-gray-dark)' }}>({count})</span>
                  </label>
                );
              })}
            </div>
          </div>

          {/* Accordion 2: Administrative Jurisdiction / State */}
          <div style={{ marginBottom: '1.25rem', paddingTop: '0.75rem', borderTop: '1px solid var(--govt-gray-light)' }}>
            <label
              style={{
                display: 'block',
                fontSize: '0.75rem',
                fontWeight: '700',
                color: 'var(--govt-gray-dark)',
                textTransform: 'uppercase',
                letterSpacing: '0.5px',
                marginBottom: '0.5rem',
              }}
            >
              State / Jurisdiction
            </label>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.35rem' }}>
              {availableStates.map((st) => {
                const isChecked = selectedStates.includes(st);
                return (
                  <button
                    key={st}
                    onClick={() => toggleSelection(selectedStates, setSelectedStates, st)}
                    style={{
                      padding: '0.35rem 0.5rem',
                      borderRadius: 'var(--radius-sm)',
                      border: `1px solid ${isChecked ? 'var(--govt-blue-primary)' : 'var(--govt-gray-medium)'}`,
                      backgroundColor: isChecked ? 'var(--govt-blue-light)' : 'var(--govt-white)',
                      color: isChecked ? 'var(--govt-blue-primary)' : 'var(--govt-gray-text)',
                      fontSize: '0.75rem',
                      fontWeight: isChecked ? '700' : '500',
                      cursor: 'pointer',
                      textAlign: 'center',
                    }}
                  >
                    {st}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Accordion 3: Verification Status */}
          <div style={{ marginBottom: '1.25rem', paddingTop: '0.75rem', borderTop: '1px solid var(--govt-gray-light)' }}>
            <label
              style={{
                display: 'block',
                fontSize: '0.75rem',
                fontWeight: '700',
                color: 'var(--govt-gray-dark)',
                textTransform: 'uppercase',
                letterSpacing: '0.5px',
                marginBottom: '0.5rem',
              }}
            >
              Audit Decision Status
            </label>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
              {availableStatuses.map((st) => {
                const isChecked = selectedStatuses.includes(st.value);
                const count = evidenceData.filter((e) => e.status === st.value).length;
                return (
                  <label
                    key={st.value}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      fontSize: '0.825rem',
                      cursor: 'pointer',
                      padding: '0.25rem 0.4rem',
                      borderRadius: 'var(--radius-sm)',
                      backgroundColor: isChecked ? 'var(--govt-gray-light)' : 'transparent',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
                      <input
                        type="checkbox"
                        checked={isChecked}
                        onChange={() => toggleSelection(selectedStatuses, setSelectedStatuses, st.value)}
                        style={{ accentColor: st.color }}
                      />
                      <span style={{ color: st.color, fontWeight: isChecked ? '700' : '500' }}>{st.label}</span>
                    </div>
                    <span style={{ fontSize: '0.72rem', color: 'var(--govt-gray-dark)' }}>({count})</span>
                  </label>
                );
              })}
            </div>
          </div>

          {/* Accordion 4: Score Range Gauges */}
          <div style={{ marginBottom: '1.25rem', paddingTop: '0.75rem', borderTop: '1px solid var(--govt-gray-light)' }}>
            <div style={{ marginBottom: '0.85rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', fontWeight: '700', marginBottom: '0.25rem' }}>
                <span style={{ color: 'var(--govt-gray-dark)' }}>Min Integrity Score:</span>
                <span style={{ color: 'var(--govt-blue-primary)' }}>{minIntegrity}%</span>
              </div>
              <input
                type="range"
                min="0"
                max="100"
                value={minIntegrity}
                onChange={(e) => setMinIntegrity(Number(e.target.value))}
                style={{ width: '100%', accentColor: 'var(--govt-blue-primary)' }}
              />
            </div>

            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', fontWeight: '700', marginBottom: '0.25rem' }}>
                <span style={{ color: 'var(--govt-gray-dark)' }}>Max Fraud Risk:</span>
                <span style={{ color: maxRisk > 50 ? 'var(--govt-danger)' : 'var(--govt-success)' }}>{maxRisk}%</span>
              </div>
              <input
                type="range"
                min="0"
                max="100"
                value={maxRisk}
                onChange={(e) => setMaxRisk(Number(e.target.value))}
                style={{ width: '100%', accentColor: maxRisk > 50 ? 'var(--govt-danger)' : 'var(--govt-success)' }}
              />
            </div>
          </div>

          {/* Anomaly Only Toggle */}
          <div style={{ paddingTop: '0.75rem', borderTop: '1px solid var(--govt-gray-light)' }}>
            <label
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
                fontSize: '0.825rem',
                fontWeight: '700',
                color: 'var(--govt-danger)',
                cursor: 'pointer',
              }}
            >
              <input
                type="checkbox"
                checked={anomalyOnly}
                onChange={(e) => setAnomalyOnly(e.target.checked)}
                style={{ accentColor: 'var(--govt-danger)' }}
              />
              Show Flagged Anomalies Only
            </label>
          </div>
        </aside>

        {/* Right Column: E-Citizen Charter Dossier Results */}
        <main>
          {/* Active Filter Chips & View Bar */}
          <div
            style={{
              backgroundColor: 'var(--govt-white)',
              borderRadius: 'var(--radius-lg)',
              border: '1px solid var(--govt-gray-medium)',
              padding: '0.85rem 1.25rem',
              marginBottom: '1rem',
              boxShadow: 'var(--shadow-xs)',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              flexWrap: 'wrap',
              gap: '0.75rem',
            }}
          >
            {/* Left: Active Filters Chips */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
              <span style={{ fontSize: '0.8rem', color: 'var(--govt-gray-dark)', fontWeight: '600' }}>
                Showing <strong>{filteredData.length}</strong> of {evidenceData.length} Dossiers:
              </span>

              {selectedSchemes.map((sc) => (
                <span
                  key={sc}
                  style={{
                    backgroundColor: 'var(--govt-blue-light)',
                    color: 'var(--govt-blue-primary)',
                    border: '1px solid var(--govt-blue-primary)',
                    borderRadius: 'var(--radius-full)',
                    padding: '0.15rem 0.6rem',
                    fontSize: '0.72rem',
                    fontWeight: '600',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '0.35rem',
                  }}
                >
                  {sc}
                  <button
                    onClick={() => toggleSelection(selectedSchemes, setSelectedSchemes, sc)}
                    style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', padding: 0 }}
                  >
                    ✕
                  </button>
                </span>
              ))}

              {selectedStates.map((st) => (
                <span
                  key={st}
                  style={{
                    backgroundColor: 'var(--govt-gray-light)',
                    color: 'var(--govt-gray-text)',
                    border: '1px solid var(--govt-gray-medium)',
                    borderRadius: 'var(--radius-full)',
                    padding: '0.15rem 0.6rem',
                    fontSize: '0.72rem',
                    fontWeight: '600',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '0.35rem',
                  }}
                >
                  State: {st}
                  <button
                    onClick={() => toggleSelection(selectedStates, setSelectedStates, st)}
                    style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', padding: 0 }}
                  >
                    ✕
                  </button>
                </span>
              ))}

              {anomalyOnly && (
                <span
                  style={{
                    backgroundColor: 'var(--govt-danger-light)',
                    color: 'var(--govt-danger)',
                    border: '1px solid var(--govt-danger)',
                    borderRadius: 'var(--radius-full)',
                    padding: '0.15rem 0.6rem',
                    fontSize: '0.72rem',
                    fontWeight: '600',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '0.35rem',
                  }}
                >
                  Anomalies Only
                  <button
                    onClick={() => setAnomalyOnly(false)}
                    style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', padding: 0 }}
                  >
                    ✕
                  </button>
                </span>
              )}
            </div>

            {/* Right: Sort and View Mode Switcher */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                <span style={{ fontSize: '0.78rem', color: 'var(--govt-gray-dark)' }}>Sort by:</span>
                <select
                  value={sortBy}
                  onChange={(e) => setSortBy(e.target.value)}
                  style={{
                    padding: '0.3rem 0.6rem',
                    border: '1px solid var(--govt-gray-medium)',
                    borderRadius: 'var(--radius-sm)',
                    fontSize: '0.78rem',
                    fontWeight: '600',
                  }}
                >
                  <option value="risk_desc">Highest Fraud Risk</option>
                  <option value="integrity_desc">Highest Integrity Score</option>
                  <option value="date_desc">Newest Submission</option>
                  <option value="risk_asc">Lowest Risk</option>
                </select>
              </div>

              {/* View Toggle */}
              <div style={{ display: 'flex', border: '1px solid var(--govt-gray-medium)', borderRadius: 'var(--radius-sm)', overflow: 'hidden' }}>
                <button
                  onClick={() => setViewMode('cards')}
                  style={{
                    padding: '0.3rem 0.6rem',
                    backgroundColor: viewMode === 'cards' ? 'var(--govt-blue-primary)' : 'var(--govt-white)',
                    color: viewMode === 'cards' ? '#ffffff' : 'var(--govt-gray-text)',
                    border: 'none',
                    fontSize: '0.75rem',
                    fontWeight: '600',
                    cursor: 'pointer',
                  }}
                >
                  Cards
                </button>
                <button
                  onClick={() => setViewMode('table')}
                  style={{
                    padding: '0.3rem 0.6rem',
                    backgroundColor: viewMode === 'table' ? 'var(--govt-blue-primary)' : 'var(--govt-white)',
                    color: viewMode === 'table' ? '#ffffff' : 'var(--govt-gray-text)',
                    border: 'none',
                    fontSize: '0.75rem',
                    fontWeight: '600',
                    cursor: 'pointer',
                  }}
                >
                  Table
                </button>
              </div>
            </div>
          </div>

          {/* Results: Cards View (Susasan E-Citizen Charter Cards) */}
          {viewMode === 'cards' ? (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))', gap: '1rem' }}>
              {filteredData.map((item) => {
                const isFlagged = item.status === 'flagged';
                return (
                  <div
                    key={item.id}
                    style={{
                      backgroundColor: 'var(--govt-white)',
                      borderRadius: 'var(--radius-lg)',
                      border: isFlagged ? '1.5px solid var(--govt-danger-border)' : '1px solid var(--govt-gray-medium)',
                      padding: '1.25rem',
                      boxShadow: isFlagged ? '0 4px 12px rgba(220, 38, 38, 0.08)' : 'var(--shadow-sm)',
                      display: 'flex',
                      flexDirection: 'column',
                      justifyContent: 'space-between',
                      position: 'relative',
                      overflow: 'hidden',
                      transition: 'transform 0.18s ease, box-shadow 0.18s ease',
                    }}
                  >
                    {/* Top Stripe for flagged items */}
                    {isFlagged && (
                      <div
                        style={{
                          position: 'absolute',
                          top: 0,
                          left: 0,
                          right: 0,
                          height: '4px',
                          backgroundColor: 'var(--govt-danger)',
                        }}
                      />
                    )}

                    <div>
                      {/* Badge Row */}
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
                        <span
                          style={{
                            fontSize: '0.7rem',
                            fontWeight: '700',
                            padding: '0.2rem 0.55rem',
                            borderRadius: 'var(--radius-full)',
                            backgroundColor: 'var(--govt-blue-light)',
                            color: 'var(--govt-blue-primary)',
                            letterSpacing: '0.3px',
                          }}
                        >
                          {item.scheme}
                        </span>

                        <span
                          style={{
                            fontSize: '0.7rem',
                            fontWeight: '700',
                            padding: '0.2rem 0.6rem',
                            borderRadius: 'var(--radius-full)',
                            backgroundColor: isFlagged
                              ? 'var(--govt-danger-light)'
                              : item.status === 'approved'
                              ? 'var(--govt-success-light)'
                              : 'var(--govt-warning-light)',
                            color: isFlagged
                              ? 'var(--govt-danger-text)'
                              : item.status === 'approved'
                              ? 'var(--govt-success-text)'
                              : 'var(--govt-warning-text)',
                            border: `1px solid ${
                              isFlagged
                                ? 'var(--govt-danger-border)'
                                : item.status === 'approved'
                                ? 'var(--govt-success-border)'
                                : 'var(--govt-warning-border)'
                            }`,
                            textTransform: 'uppercase',
                          }}
                        >
                          {item.status}
                        </span>
                      </div>

                      {/* Title & Activity */}
                      <h4 style={{ margin: '0 0 0.35rem 0', fontSize: '1.05rem', color: 'var(--govt-gray-title)', fontWeight: '700' }}>
                        <Link to={`/evidence/${item.id}`} style={{ color: 'inherit', textDecoration: 'none' }}>
                          {item.project_name}
                        </Link>
                      </h4>

                      <div style={{ fontSize: '0.85rem', color: 'var(--govt-gray-text)', marginBottom: '0.75rem', fontWeight: '500' }}>
                        <strong>Milestone Claim:</strong> {item.activity}
                      </div>

                      {/* Anomaly Strip if present */}
                      {item.has_anomaly && (
                        <div
                          style={{
                            backgroundColor: 'var(--govt-danger-light)',
                            border: '1px solid var(--govt-danger-border)',
                            borderRadius: 'var(--radius-sm)',
                            padding: '0.5rem 0.65rem',
                            marginBottom: '0.75rem',
                            display: 'flex',
                            gap: '0.45rem',
                            alignItems: 'flex-start',
                          }}
                        >
                          <span style={{ color: 'var(--govt-danger)', flexShrink: 0 }}>
                            <AlertIcon />
                          </span>
                          <span style={{ fontSize: '0.75rem', color: 'var(--govt-danger-text)', fontWeight: '600', lineHeight: 1.3 }}>
                            {item.anomaly_title}
                          </span>
                        </div>
                      )}

                      {/* Metadata Table / Metrics */}
                      <div
                        style={{
                          backgroundColor: 'var(--govt-gray-off-white)',
                          padding: '0.75rem',
                          borderRadius: 'var(--radius-md)',
                          fontSize: '0.78rem',
                          marginBottom: '0.85rem',
                          display: 'grid',
                          gridTemplateColumns: '1fr 1fr',
                          gap: '0.5rem',
                        }}
                      >
                        <div>
                          <span style={{ color: 'var(--govt-gray-dark)', display: 'block', fontSize: '0.7rem' }}>Evidence ID</span>
                          <strong style={{ color: 'var(--govt-blue-primary)', fontFamily: 'var(--font-family-mono)' }}>{item.id}</strong>
                        </div>
                        <div>
                          <span style={{ color: 'var(--govt-gray-dark)', display: 'block', fontSize: '0.7rem' }}>Recorded Location</span>
                          <strong>{item.location}</strong>
                        </div>
                        <div>
                          <span style={{ color: 'var(--govt-gray-dark)', display: 'block', fontSize: '0.7rem' }}>Designated Official</span>
                          <strong>{item.officer}</strong>
                        </div>
                        <div>
                          <span style={{ color: 'var(--govt-gray-dark)', display: 'block', fontSize: '0.7rem' }}>Geofence Check</span>
                          <span style={{ color: item.geofence_status.includes('Out') ? 'var(--govt-danger)' : 'var(--govt-success)', fontWeight: '700' }}>
                            {item.geofence_status}
                          </span>
                        </div>
                      </div>

                      {/* Dual Score Meters */}
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem', marginBottom: '1rem' }}>
                        <div>
                          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.72rem', fontWeight: '700', marginBottom: '0.2rem' }}>
                            <span>Integrity:</span>
                            <span style={{ color: item.integrity_score >= 80 ? 'var(--govt-success)' : 'var(--govt-warning)' }}>
                              {item.integrity_score}%
                            </span>
                          </div>
                          <div style={{ height: '6px', backgroundColor: 'var(--govt-gray-medium)', borderRadius: '3px', overflow: 'hidden' }}>
                            <div
                              style={{
                                width: `${item.integrity_score}%`,
                                height: '100%',
                                backgroundColor: item.integrity_score >= 80 ? 'var(--govt-success)' : 'var(--govt-warning)',
                              }}
                            />
                          </div>
                        </div>

                        <div>
                          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.72rem', fontWeight: '700', marginBottom: '0.2rem' }}>
                            <span>Fraud Risk:</span>
                            <span style={{ color: item.risk_score > 50 ? 'var(--govt-danger)' : 'var(--govt-success)' }}>
                              {item.risk_score}%
                            </span>
                          </div>
                          <div style={{ height: '6px', backgroundColor: 'var(--govt-gray-medium)', borderRadius: '3px', overflow: 'hidden' }}>
                            <div
                              style={{
                                width: `${item.risk_score}%`,
                                height: '100%',
                                backgroundColor: item.risk_score > 50 ? 'var(--govt-danger)' : 'var(--govt-success)',
                              }}
                            />
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Card Actions */}
                    <div style={{ display: 'flex', gap: '0.5rem', borderTop: '1px solid var(--govt-gray-light)', paddingTop: '0.75rem' }}>
                      <Link
                        to={`/evidence/${item.id}`}
                        style={{
                          flex: 1,
                          textAlign: 'center',
                          padding: '0.45rem',
                          backgroundColor: 'var(--govt-blue-primary)',
                          color: '#ffffff',
                          borderRadius: 'var(--radius-sm)',
                          fontSize: '0.8rem',
                          fontWeight: '700',
                          textDecoration: 'none',
                        }}
                      >
                        Inspect Dossier
                      </Link>
                      <Link
                        to={`/graph?highlight=${item.id}`}
                        style={{
                          padding: '0.45rem 0.65rem',
                          backgroundColor: 'var(--govt-blue-light)',
                          color: 'var(--govt-blue-primary)',
                          border: '1px solid var(--govt-blue-primary)',
                          borderRadius: 'var(--radius-sm)',
                          fontSize: '0.8rem',
                          fontWeight: '600',
                          textDecoration: 'none',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '0.35rem',
                        }}
                      >
                        <GraphIcon />
                        Graph
                      </Link>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            /* Table View */
            <div
              style={{
                backgroundColor: 'var(--govt-white)',
                borderRadius: 'var(--radius-lg)',
                border: '1px solid var(--govt-gray-medium)',
                overflow: 'hidden',
                boxShadow: 'var(--shadow-sm)',
              }}
            >
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
                <thead style={{ backgroundColor: 'var(--govt-gray-off-white)', borderBottom: '1px solid var(--govt-gray-medium)' }}>
                  <tr>
                    <th style={{ padding: '0.75rem 1rem', textAlign: 'left', color: 'var(--govt-gray-title)' }}>Dossier ID</th>
                    <th style={{ padding: '0.75rem 1rem', textAlign: 'left', color: 'var(--govt-gray-title)' }}>Project & Milestone</th>
                    <th style={{ padding: '0.75rem 1rem', textAlign: 'left', color: 'var(--govt-gray-title)' }}>Scheme</th>
                    <th style={{ padding: '0.75rem 1rem', textAlign: 'left', color: 'var(--govt-gray-title)' }}>Location</th>
                    <th style={{ padding: '0.75rem 1rem', textAlign: 'center', color: 'var(--govt-gray-title)' }}>Integrity</th>
                    <th style={{ padding: '0.75rem 1rem', textAlign: 'center', color: 'var(--govt-gray-title)' }}>Fraud Risk</th>
                    <th style={{ padding: '0.75rem 1rem', textAlign: 'center', color: 'var(--govt-gray-title)' }}>Status</th>
                    <th style={{ padding: '0.75rem 1rem', textAlign: 'right', color: 'var(--govt-gray-title)' }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredData.map((e) => (
                    <tr key={e.id} style={{ borderBottom: '1px solid var(--govt-gray-light)' }}>
                      <td style={{ padding: '0.75rem 1rem', fontFamily: 'var(--font-family-mono)', fontWeight: '700' }}>
                        <Link to={`/evidence/${e.id}`} style={{ color: 'var(--govt-blue-primary)', textDecoration: 'none' }}>
                          {e.id}
                        </Link>
                      </td>
                      <td style={{ padding: '0.75rem 1rem' }}>
                        <div style={{ fontWeight: '600' }}>{e.project_name}</div>
                        <div style={{ fontSize: '0.75rem', color: 'var(--govt-gray-dark)' }}>{e.activity}</div>
                      </td>
                      <td style={{ padding: '0.75rem 1rem', color: 'var(--govt-gray-dark)', fontSize: '0.8rem' }}>{e.scheme}</td>
                      <td style={{ padding: '0.75rem 1rem' }}>{e.location}</td>
                      <td style={{ padding: '0.75rem 1rem', textAlign: 'center', fontWeight: '700' }}>{e.integrity_score}%</td>
                      <td style={{ padding: '0.75rem 1rem', textAlign: 'center', fontWeight: '700', color: e.risk_score > 50 ? 'var(--govt-danger)' : 'inherit' }}>
                        {e.risk_score}%
                      </td>
                      <td style={{ padding: '0.75rem 1rem', textAlign: 'center' }}>
                        <span
                          style={{
                            fontSize: '0.7rem',
                            fontWeight: '700',
                            padding: '0.15rem 0.5rem',
                            borderRadius: 'var(--radius-full)',
                            backgroundColor: e.status === 'flagged' ? 'var(--govt-danger-light)' : 'var(--govt-success-light)',
                            color: e.status === 'flagged' ? 'var(--govt-danger-text)' : 'var(--govt-success-text)',
                            textTransform: 'uppercase',
                          }}
                        >
                          {e.status}
                        </span>
                      </td>
                      <td style={{ padding: '0.75rem 1rem', textAlign: 'right' }}>
                        <Link
                          to={`/evidence/${e.id}`}
                          style={{
                            fontSize: '0.8rem',
                            fontWeight: '600',
                            color: 'var(--govt-blue-primary)',
                            textDecoration: 'none',
                          }}
                        >
                          Dossier &rarr;
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

export default Search;
