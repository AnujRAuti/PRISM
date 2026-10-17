import React, { useState, useEffect } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import { useApp } from '../../context/AppContext';
import { Search, MapPin, Camera, ShieldCheck, AlertCircle, Clock, CheckCircle2, FileText, ArrowRight, UploadCloud, Eye, Lock } from 'lucide-react';

export default function CitizenPortal() {
  const [searchParams, setSearchParams] = useSearchParams();
  const initialTab = searchParams.get('tab') || 'discover';
  const [activeTab, setActiveTab] = useState(initialTab);

  const { projects, complaints, fileCitizenReport, currentUser } = useApp();

  // Search & Filter state for Discover
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedScheme, setSelectedScheme] = useState('ALL');

  // Form state for Filing Report
  const [reportProject, setReportProject] = useState(projects[0]?.id || '');
  const [reportCategory, setReportCategory] = useState('Pavement Defect & Early Wear');
  const [reportDescription, setReportDescription] = useState('');
  const [reportLocation, setReportLocation] = useState('Detected via Mobile GPS: 18.2814° N, 74.0156° E (Purandar Block)');
  const [reportPhoto, setReportPhoto] = useState('/images/projects/road-pothole.jpg');
  const [isPrivate, setIsPrivate] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [submittedToken, setSubmittedToken] = useState(null);

  // Sync tab with URL
  useEffect(() => {
    const tab = searchParams.get('tab');
    if (tab && ['discover', 'report', 'track'].includes(tab)) {
      setActiveTab(tab);
    }
  }, [searchParams]);

  const handleTabChange = (tab) => {
    setActiveTab(tab);
    setSearchParams({ tab });
  };

  const handleSelectProjectForReport = (projId) => {
    setReportProject(projId);
    handleTabChange('report');
  };

  const handleSubmitReport = (e) => {
    e.preventDefault();
    if (!reportDescription || reportDescription.trim().length < 10) {
      alert('Please provide a brief description of the observed civic issue (minimum 10 characters).');
      return;
    }

    setSubmitting(true);
    setTimeout(() => {
      const selectedProjObj = projects.find((p) => p.id === reportProject);
      const res = fileCitizenReport({
        projectId: reportProject,
        projectName: selectedProjObj ? selectedProjObj.title : 'Public Infrastructure Project',
        category: reportCategory,
        description: reportDescription,
        photoUrl: reportPhoto,
        location: reportLocation,
        isPrivate,
      });

      setSubmitting(false);
      setSubmittedToken(res.trackingId);
      setReportDescription('');
    }, 600);
  };

  // Filter projects for Discover tab
  const filteredProjects = projects.filter((p) => {
    const matchesSearch =
      searchTerm === '' ||
      p.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
      p.district.toLowerCase().includes(searchTerm.toLowerCase()) ||
      p.state.toLowerCase().includes(searchTerm.toLowerCase()) ||
      p.scheme.toLowerCase().includes(searchTerm.toLowerCase());

    const matchesScheme = selectedScheme === 'ALL' || p.scheme.includes(selectedScheme);

    return matchesSearch && matchesScheme;
  });

  return (
    <div style={{ maxWidth: '1200px', margin: '0 auto', paddingBottom: '3rem' }}>
      {/* GovTech Header Banner */}
      <div
        style={{
          backgroundColor: 'var(--govt-white)',
          borderRadius: 'var(--radius-lg)',
          border: '1px solid var(--govt-gray-medium)',
          padding: '1.5rem 2rem',
          marginBottom: '1.5rem',
          boxShadow: 'var(--shadow-sm)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1rem' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '0.4rem' }}>
              <span
                style={{
                  fontSize: '0.75rem',
                  fontWeight: 700,
                  color: 'var(--govt-success)',
                  backgroundColor: 'rgba(22, 101, 52, 0.1)',
                  padding: '0.2rem 0.6rem',
                  borderRadius: '999px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.35rem',
                }}
              >
                <ShieldCheck size={14} /> Digital Public Infrastructure (DPI)
              </span>
              <span style={{ fontSize: '0.8rem', color: 'var(--govt-gray-dark)' }}>
                • Public Works Transparency & Citizen Feedback
              </span>
            </div>
            <h1 style={{ fontSize: '1.6rem', fontWeight: 800, color: 'var(--govt-blue-dark)', margin: 0 }}>
              Citizen Civic Transparency & Grievance Portal
            </h1>
            <p style={{ margin: '0.4rem 0 0', color: 'var(--govt-gray-dark)', fontSize: '0.875rem' }}>
              Discover state-funded projects in your locality, inspect verified progress evidence, and submit ground reports.
            </p>
          </div>

          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.85rem',
              backgroundColor: 'var(--govt-gray-off-white)',
              padding: '0.6rem 1rem',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--govt-gray-medium)',
            }}
          >
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--govt-blue-dark)' }}>
                {currentUser?.name || 'Ramesh Sharma'}
              </div>
              <div style={{ fontSize: '0.7rem', color: 'var(--govt-gray-dark)' }}>
                {currentUser?.isAadhaarVerified ? '✓ Aadhaar Verified Resident' : 'Resident Contributor'}
              </div>
            </div>
            <div
              style={{
                width: '36px',
                height: '36px',
                borderRadius: '50%',
                backgroundColor: 'var(--govt-blue-primary)',
                color: '#fff',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontWeight: 700,
                fontSize: '0.9rem',
              }}
            >
              {(currentUser?.name || 'C').charAt(0)}
            </div>
          </div>
        </div>

        {/* Navigation Tabs */}
        <div
          style={{
            display: 'flex',
            gap: '0.75rem',
            marginTop: '1.5rem',
            borderTop: '1px solid var(--govt-gray-medium)',
            paddingTop: '1.25rem',
          }}
        >
          <button
            type="button"
            onClick={() => handleTabChange('discover')}
            style={{
              padding: '0.6rem 1.25rem',
              borderRadius: 'var(--radius-md)',
              fontWeight: activeTab === 'discover' ? 700 : 500,
              fontSize: '0.875rem',
              cursor: 'pointer',
              border: 'none',
              backgroundColor: activeTab === 'discover' ? 'var(--govt-blue-primary)' : 'var(--govt-gray-off-white)',
              color: activeTab === 'discover' ? '#ffffff' : 'var(--govt-gray-dark)',
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              transition: 'all 0.15s ease',
            }}
          >
            <Search size={16} /> 1. Discover Projects
          </button>

          <button
            type="button"
            onClick={() => handleTabChange('report')}
            style={{
              padding: '0.6rem 1.25rem',
              borderRadius: 'var(--radius-md)',
              fontWeight: activeTab === 'report' ? 700 : 500,
              fontSize: '0.875rem',
              cursor: 'pointer',
              border: 'none',
              backgroundColor: activeTab === 'report' ? 'var(--govt-blue-primary)' : 'var(--govt-gray-off-white)',
              color: activeTab === 'report' ? '#ffffff' : 'var(--govt-gray-dark)',
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              transition: 'all 0.15s ease',
            }}
          >
            <Camera size={16} /> 2. Report Civic Issue
          </button>

          <button
            type="button"
            onClick={() => handleTabChange('track')}
            style={{
              padding: '0.6rem 1.25rem',
              borderRadius: 'var(--radius-md)',
              fontWeight: activeTab === 'track' ? 700 : 500,
              fontSize: '0.875rem',
              cursor: 'pointer',
              border: 'none',
              backgroundColor: activeTab === 'track' ? 'var(--govt-blue-primary)' : 'var(--govt-gray-off-white)',
              color: activeTab === 'track' ? '#ffffff' : 'var(--govt-gray-dark)',
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              transition: 'all 0.15s ease',
            }}
          >
            <Clock size={16} /> 3. Track My Reports ({complaints.length})
          </button>
        </div>
      </div>

      {/* TAB 1: DISCOVER PUBLIC PROJECTS */}
      {activeTab === 'discover' && (
        <div>
          {/* Search bar & filter pills */}
          <div
            style={{
              display: 'flex',
              gap: '1rem',
              marginBottom: '1.25rem',
              flexWrap: 'wrap',
              backgroundColor: 'var(--govt-white)',
              padding: '1rem',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--govt-gray-medium)',
            }}
          >
            <div style={{ flex: 1, minWidth: '240px', position: 'relative' }}>
              <Search
                size={16}
                style={{ position: 'absolute', left: '0.85rem', top: '50%', transform: 'translateY(-50%)', color: '#94a3b8' }}
              />
              <input
                type="text"
                placeholder="Search by project name, district, state or scheme..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                style={{
                  width: '100%',
                  padding: '0.55rem 0.85rem 0.55rem 2.4rem',
                  fontSize: '0.875rem',
                  borderRadius: 'var(--radius-md)',
                  border: '1px solid var(--govt-gray-medium)',
                  outline: 'none',
                  boxSizing: 'border-box',
                }}
              />
            </div>

            <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
              {['ALL', 'PMGSY', 'Jal Jeevan', 'Samagra Shiksha', 'PM-KUSUM'].map((sch) => (
                <button
                  key={sch}
                  type="button"
                  onClick={() => setSelectedScheme(sch)}
                  style={{
                    padding: '0.45rem 0.85rem',
                    borderRadius: '999px',
                    fontSize: '0.775rem',
                    fontWeight: selectedScheme === sch ? 700 : 500,
                    border: '1px solid',
                    borderColor: selectedScheme === sch ? 'var(--govt-blue-primary)' : 'var(--govt-gray-medium)',
                    backgroundColor: selectedScheme === sch ? 'var(--govt-blue-light)' : 'transparent',
                    color: selectedScheme === sch ? 'var(--govt-blue-primary)' : 'var(--govt-gray-dark)',
                    cursor: 'pointer',
                  }}
                >
                  {sch}
                </button>
              ))}
            </div>
          </div>

          {/* Projects Cards Grid */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))',
              gap: '1.25rem',
            }}
          >
            {filteredProjects.map((p) => (
              <div
                key={p.id}
                style={{
                  backgroundColor: 'var(--govt-white)',
                  borderRadius: 'var(--radius-lg)',
                  border: '1px solid var(--govt-gray-medium)',
                  overflow: 'hidden',
                  boxShadow: 'var(--shadow-xs)',
                  display: 'flex',
                  flexDirection: 'column',
                }}
              >
                <div style={{ position: 'relative', height: '170px', backgroundColor: '#0f172a' }}>
                  <img
                    src={p.coverPhoto}
                    alt={p.title}
                    style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                  />
                  <span
                    style={{
                      position: 'absolute',
                      top: '0.75rem',
                      left: '0.75rem',
                      fontSize: '0.7rem',
                      fontWeight: 700,
                      backgroundColor: 'rgba(15, 23, 42, 0.85)',
                      color: '#fff',
                      padding: '0.2rem 0.5rem',
                      borderRadius: '4px',
                      fontFamily: 'var(--font-family-mono)',
                    }}
                  >
                    {p.id}
                  </span>
                  <span
                    style={{
                      position: 'absolute',
                      top: '0.75rem',
                      right: '0.75rem',
                      fontSize: '0.7rem',
                      fontWeight: 700,
                      backgroundColor: 'var(--govt-success)',
                      color: '#fff',
                      padding: '0.2rem 0.55rem',
                      borderRadius: '999px',
                    }}
                  >
                    Statutory Sanction Active
                  </span>
                </div>

                <div style={{ padding: '1.25rem', flex: 1, display: 'flex', flexDirection: 'column' }}>
                  <div style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--govt-blue-primary)', marginBottom: '0.25rem' }}>
                    {p.scheme}
                  </div>
                  <h3 style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--govt-blue-dark)', margin: '0 0 0.5rem 0', lineHeight: 1.3 }}>
                    {p.title}
                  </h3>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', color: 'var(--govt-gray-dark)', fontSize: '0.8rem', marginBottom: '0.85rem' }}>
                    <MapPin size={14} />
                    <span>{p.district}, {p.state}</span>
                  </div>

                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: '1fr 1fr',
                      gap: '0.5rem',
                      backgroundColor: 'var(--govt-gray-off-white)',
                      padding: '0.75rem',
                      borderRadius: 'var(--radius-md)',
                      marginBottom: '1rem',
                      fontSize: '0.775rem',
                    }}
                  >
                    <div>
                      <span style={{ color: 'var(--govt-gray-dark)', display: 'block' }}>Sanctioned Budget:</span>
                      <strong style={{ color: 'var(--govt-blue-dark)' }}>{p.budget}</strong>
                    </div>
                    <div>
                      <span style={{ color: 'var(--govt-gray-dark)', display: 'block' }}>Geofence Radius:</span>
                      <strong style={{ color: 'var(--govt-blue-dark)' }}>{p.geofenceRadiusMeters} meters</strong>
                    </div>
                    <div>
                      <span style={{ color: 'var(--govt-gray-dark)', display: 'block' }}>Submissions:</span>
                      <strong>{p.totalSubmissions} verified photos</strong>
                    </div>
                    <div>
                      <span style={{ color: 'var(--govt-gray-dark)', display: 'block' }}>Executing Agency:</span>
                      <span style={{ color: 'var(--govt-gray-dark)', fontSize: '0.725rem' }}>{p.contractor}</span>
                    </div>
                  </div>

                  <div style={{ marginTop: 'auto', display: 'flex', gap: '0.5rem' }}>
                    <Link
                      to={`/projects/${p.id}`}
                      style={{
                        flex: 1,
                        padding: '0.5rem 0.75rem',
                        textAlign: 'center',
                        fontSize: '0.8rem',
                        fontWeight: 600,
                        borderRadius: 'var(--radius-md)',
                        border: '1px solid var(--govt-gray-medium)',
                        color: 'var(--govt-blue-dark)',
                        textDecoration: 'none',
                        backgroundColor: '#fff',
                      }}
                    >
                      Inspect Dossier
                    </Link>

                    <button
                      type="button"
                      onClick={() => handleSelectProjectForReport(p.id)}
                      style={{
                        flex: 1.2,
                        padding: '0.5rem 0.75rem',
                        fontSize: '0.8rem',
                        fontWeight: 700,
                        borderRadius: 'var(--radius-md)',
                        border: 'none',
                        backgroundColor: 'var(--govt-blue-primary)',
                        color: '#fff',
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        gap: '0.35rem',
                      }}
                    >
                      <Camera size={14} /> Report Issue
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* TAB 2: FILE CIVIC GRIEVANCE / CITIZEN REPORT */}
      {activeTab === 'report' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 0.8fr', gap: '1.5rem' }}>
          {/* Submission Form Card */}
          <div
            style={{
              backgroundColor: 'var(--govt-white)',
              borderRadius: 'var(--radius-lg)',
              border: '1px solid var(--govt-gray-medium)',
              padding: '1.75rem',
              boxShadow: 'var(--shadow-sm)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
              <span style={{ backgroundColor: 'rgba(239, 68, 68, 0.1)', color: 'var(--govt-danger)', padding: '0.2rem 0.5rem', borderRadius: '4px', fontSize: '0.7rem', fontWeight: 700 }}>
                STATUTORY CITIZEN INTAKE
              </span>
              <span style={{ fontSize: '0.75rem', color: 'var(--govt-gray-dark)' }}>Pursuant to Section 86 Public Accountability</span>
            </div>
            <h2 style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--govt-blue-dark)', margin: '0 0 1rem 0' }}>
              Submit Ground Civic Observation & Evidence
            </h2>

            {submittedToken ? (
              <div
                style={{
                  backgroundColor: 'rgba(22, 101, 52, 0.08)',
                  border: '1px solid rgba(22, 101, 52, 0.25)',
                  borderRadius: 'var(--radius-md)',
                  padding: '1.5rem',
                  textAlign: 'center',
                }}
              >
                <CheckCircle2 size={42} style={{ color: 'var(--govt-success)', margin: '0 auto 0.75rem auto' }} />
                <h3 style={{ fontSize: '1.15rem', fontWeight: 700, color: 'var(--govt-success)', margin: '0 0 0.5rem 0' }}>
                  Grievance Ingested into PRISM Audit Ledger
                </h3>
                <p style={{ fontSize: '0.875rem', color: 'var(--govt-gray-dark)', margin: '0 0 1rem 0' }}>
                  Your report has been cryptographically signed and routed to the jurisdictional Junior Engineer.
                </p>

                <div
                  style={{
                    backgroundColor: '#fff',
                    padding: '0.75rem 1.25rem',
                    borderRadius: 'var(--radius-md)',
                    border: '1px dashed var(--govt-success)',
                    display: 'inline-block',
                    marginBottom: '1.25rem',
                  }}
                >
                  <span style={{ fontSize: '0.75rem', color: 'var(--govt-gray-dark)', display: 'block' }}>
                    Official Tracking Number:
                  </span>
                  <span style={{ fontSize: '1.2rem', fontWeight: 800, color: 'var(--govt-blue-dark)', fontFamily: 'var(--font-family-mono)' }}>
                    {submittedToken}
                  </span>
                </div>

                <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'center' }}>
                  <button
                    type="button"
                    onClick={() => handleTabChange('track')}
                    style={{
                      padding: '0.6rem 1.25rem',
                      backgroundColor: 'var(--govt-blue-primary)',
                      color: '#fff',
                      border: 'none',
                      borderRadius: 'var(--radius-md)',
                      fontWeight: 700,
                      fontSize: '0.85rem',
                      cursor: 'pointer',
                    }}
                  >
                    View Status in Tracking Log →
                  </button>
                  <button
                    type="button"
                    onClick={() => setSubmittedToken(null)}
                    style={{
                      padding: '0.6rem 1rem',
                      backgroundColor: 'transparent',
                      color: 'var(--govt-gray-dark)',
                      border: '1px solid var(--govt-gray-medium)',
                      borderRadius: 'var(--radius-md)',
                      fontWeight: 600,
                      fontSize: '0.85rem',
                      cursor: 'pointer',
                    }}
                  >
                    File Another Report
                  </button>
                </div>
              </div>
            ) : (
              <form onSubmit={handleSubmitReport}>
                {/* 1. Target Project */}
                <div style={{ marginBottom: '1.25rem' }}>
                  <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 700, color: 'var(--govt-blue-dark)', marginBottom: '0.4rem' }}>
                    1. Select Public Works Project *
                  </label>
                  <select
                    value={reportProject}
                    onChange={(e) => setReportProject(e.target.value)}
                    style={{
                      width: '100%',
                      padding: '0.6rem 0.85rem',
                      borderRadius: 'var(--radius-md)',
                      border: '1px solid var(--govt-gray-medium)',
                      fontSize: '0.85rem',
                      backgroundColor: '#fff',
                    }}
                  >
                    {projects.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.scheme} • {p.title} ({p.district})
                      </option>
                    ))}
                  </select>
                </div>

                {/* 2. Category */}
                <div style={{ marginBottom: '1.25rem' }}>
                  <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 700, color: 'var(--govt-blue-dark)', marginBottom: '0.4rem' }}>
                    2. Observed Defect or Issue Category *
                  </label>
                  <select
                    value={reportCategory}
                    onChange={(e) => setReportCategory(e.target.value)}
                    style={{
                      width: '100%',
                      padding: '0.6rem 0.85rem',
                      borderRadius: 'var(--radius-md)',
                      border: '1px solid var(--govt-gray-medium)',
                      fontSize: '0.85rem',
                      backgroundColor: '#fff',
                    }}
                  >
                    <option value="Pavement Defect & Early Wear">Pavement Defect / Pothole / Premature Bitumen Wear</option>
                    <option value="Water Pump Dry / Inactive Tap">Dry Tap / Missing Solar Dual Pump / Low Pressure</option>
                    <option value="Building Structural Crack & Masonry">Building Structural Crack / Roof Leakage / Incomplete Masonry</option>
                    <option value="Non-Functional Solar Streetlight">Non-Functional Solar Streetlight / Battery Missing</option>
                    <option value="Contractor Abandonment & Delay">Site Abandonment / Excessive Construction Delay</option>
                  </select>
                </div>

                {/* 3. Photo Evidence */}
                <div style={{ marginBottom: '1.25rem' }}>
                  <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 700, color: 'var(--govt-blue-dark)', marginBottom: '0.4rem' }}>
                    3. Ground Photographic Evidence (Auto-hashed SHA-256) *
                  </label>
                  <div
                    style={{
                      border: '1.5px dashed var(--govt-gray-medium)',
                      borderRadius: 'var(--radius-md)',
                      padding: '1rem',
                      textAlign: 'center',
                      backgroundColor: 'var(--govt-gray-off-white)',
                    }}
                  >
                    <img
                      src={reportPhoto}
                      alt="Ground Evidence Preview"
                      style={{ maxHeight: '140px', borderRadius: 'var(--radius-sm)', objectFit: 'cover', marginBottom: '0.5rem' }}
                    />
                    <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'center' }}>
                      <button
                        type="button"
                        onClick={() => setReportPhoto('/images/projects/road-pothole.jpg')}
                        style={{
                          fontSize: '0.75rem',
                          padding: '0.35rem 0.75rem',
                          borderRadius: '4px',
                          border: '1px solid var(--govt-gray-medium)',
                          backgroundColor: reportPhoto.includes('pothole') ? 'var(--govt-blue-primary)' : '#fff',
                          color: reportPhoto.includes('pothole') ? '#fff' : 'var(--govt-gray-dark)',
                          cursor: 'pointer',
                        }}
                      >
                        Sample 1 (Road Defect)
                      </button>
                      <button
                        type="button"
                        onClick={() => setReportPhoto('/images/projects/water-pump.jpg')}
                        style={{
                          fontSize: '0.75rem',
                          padding: '0.35rem 0.75rem',
                          borderRadius: '4px',
                          border: '1px solid var(--govt-gray-medium)',
                          backgroundColor: reportPhoto.includes('water-pump') ? 'var(--govt-blue-primary)' : '#fff',
                          color: reportPhoto.includes('water-pump') ? '#fff' : 'var(--govt-gray-dark)',
                          cursor: 'pointer',
                        }}
                      >
                        Sample 2 (Dry Pump)
                      </button>
                      <button
                        type="button"
                        onClick={() => setReportPhoto('/images/projects/school-before.jpg')}
                        style={{
                          fontSize: '0.75rem',
                          padding: '0.35rem 0.75rem',
                          borderRadius: '4px',
                          border: '1px solid var(--govt-gray-medium)',
                          backgroundColor: reportPhoto.includes('school') ? 'var(--govt-blue-primary)' : '#fff',
                          color: reportPhoto.includes('school') ? '#fff' : 'var(--govt-gray-dark)',
                          cursor: 'pointer',
                        }}
                      >
                        Sample 3 (School Structure)
                      </button>
                    </div>
                  </div>
                </div>

                {/* 4. Location Context */}
                <div style={{ marginBottom: '1.25rem' }}>
                  <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 700, color: 'var(--govt-blue-dark)', marginBottom: '0.4rem' }}>
                    4. Geographic Location Context (GPS)
                  </label>
                  <input
                    type="text"
                    value={reportLocation}
                    onChange={(e) => setReportLocation(e.target.value)}
                    style={{
                      width: '100%',
                      padding: '0.6rem 0.85rem',
                      borderRadius: 'var(--radius-md)',
                      border: '1px solid var(--govt-gray-medium)',
                      fontSize: '0.825rem',
                      backgroundColor: 'var(--govt-gray-off-white)',
                      boxSizing: 'border-box',
                    }}
                  />
                </div>

                {/* 5. Statement Text */}
                <div style={{ marginBottom: '1.25rem' }}>
                  <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 700, color: 'var(--govt-blue-dark)', marginBottom: '0.4rem' }}>
                    5. Detailed Citizen Statement / Ground Observations *
                  </label>
                  <textarea
                    rows={4}
                    placeholder="Describe specific physical observations (e.g. location marker, length of damaged patch, days pump has been non-functional)..."
                    value={reportDescription}
                    onChange={(e) => setReportDescription(e.target.value)}
                    style={{
                      width: '100%',
                      padding: '0.75rem',
                      borderRadius: 'var(--radius-md)',
                      border: '1px solid var(--govt-gray-medium)',
                      fontSize: '0.85rem',
                      boxSizing: 'border-box',
                      fontFamily: 'inherit',
                    }}
                  />
                </div>

                {/* 6. Privacy Mode (BE-022 Statutory Citizen Protection) */}
                <div
                  style={{
                    backgroundColor: 'rgba(59, 130, 246, 0.05)',
                    border: '1px solid rgba(59, 130, 246, 0.2)',
                    borderRadius: 'var(--radius-md)',
                    padding: '0.85rem',
                    marginBottom: '1.5rem',
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: '0.75rem',
                  }}
                >
                  <input
                    type="checkbox"
                    id="privacyToggle"
                    checked={isPrivate}
                    onChange={(e) => setIsPrivate(e.target.checked)}
                    style={{ marginTop: '0.2rem', cursor: 'pointer' }}
                  />
                  <div>
                    <label htmlFor="privacyToggle" style={{ fontSize: '0.825rem', fontWeight: 700, color: 'var(--govt-blue-dark)', cursor: 'pointer' }}>
                      Citizen Privacy Protection (CITIZEN_OWNED_PRIVATE per BE-022)
                    </label>
                    <p style={{ margin: '0.2rem 0 0', fontSize: '0.725rem', color: 'var(--govt-gray-dark)', lineHeight: 1.3 }}>
                      Your personal phone and contact details will remain strictly confidential and will never appear on public transparency portals. Only the public works observations will be published.
                    </p>
                  </div>
                </div>

                <button
                  type="submit"
                  disabled={submitting}
                  style={{
                    width: '100%',
                    padding: '0.75rem',
                    backgroundColor: 'var(--govt-blue-primary)',
                    color: '#fff',
                    border: 'none',
                    borderRadius: 'var(--radius-md)',
                    fontWeight: 700,
                    fontSize: '0.9rem',
                    cursor: submitting ? 'not-allowed' : 'pointer',
                    boxShadow: 'var(--shadow-sm)',
                  }}
                >
                  {submitting ? 'Cryptographically Signing & Ingesting...' : 'Submit Citizen Report →'}
                </button>
              </form>
            )}
          </div>

          {/* Right Guidance Column */}
          <div>
            <div
              style={{
                backgroundColor: 'var(--govt-white)',
                borderRadius: 'var(--radius-lg)',
                border: '1px solid var(--govt-gray-medium)',
                padding: '1.5rem',
                marginBottom: '1.25rem',
              }}
            >
              <h3 style={{ fontSize: '0.95rem', fontWeight: 700, color: 'var(--govt-blue-dark)', margin: '0 0 0.85rem 0' }}>
                Citizen Protection & Whistleblower Rights
              </h3>
              <ul style={{ paddingLeft: '1.25rem', margin: 0, fontSize: '0.8rem', color: 'var(--govt-gray-dark)', lineHeight: 1.6 }}>
                <li><strong>No Retaliation:</strong> Submissions are classified as public audits under Section 86 oversight rules.</li>
                <li><strong>Cryptographic Ingestion:</strong> Photos receive immediate SHA-256 binary seals upon upload to prevent evidence tampering.</li>
                <li><strong>Mandatory Department Action:</strong> Jurisdictional Junior Engineers must inspect verified reports within 72 hours.</li>
                <li><strong>Unverified Status:</strong> Reports enter the review pipeline to provide intelligence without pre-judging contractor performance.</li>
              </ul>
            </div>

            <div
              style={{
                backgroundColor: 'var(--govt-blue-light)',
                borderRadius: 'var(--radius-lg)',
                border: '1px solid var(--govt-blue-primary)',
                padding: '1.25rem',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.4rem' }}>
                <Clock size={16} style={{ color: 'var(--govt-blue-primary)' }} />
                <strong style={{ fontSize: '0.85rem', color: 'var(--govt-blue-dark)' }}>Inspection Turnaround</strong>
              </div>
              <p style={{ margin: 0, fontSize: '0.775rem', color: 'var(--govt-gray-dark)', lineHeight: 1.4 }}>
                Current state average resolution time for citizen grievances is <strong>4.2 days</strong> with photographic proof of resolution required for ticket closure.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* TAB 3: TRACK MY SUBMISSIONS */}
      {activeTab === 'track' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          {complaints.map((c) => (
            <div
              key={c.id}
              style={{
                backgroundColor: 'var(--govt-white)',
                borderRadius: 'var(--radius-lg)',
                border: '1px solid var(--govt-gray-medium)',
                padding: '1.5rem',
                boxShadow: 'var(--shadow-xs)',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1rem', marginBottom: '1rem' }}>
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '0.25rem' }}>
                    <span
                      style={{
                        fontFamily: 'var(--font-family-mono)',
                        fontSize: '0.85rem',
                        fontWeight: 700,
                        color: 'var(--govt-blue-primary)',
                      }}
                    >
                      {c.trackingId}
                    </span>
                    <span
                      style={{
                        fontSize: '0.7rem',
                        fontWeight: 700,
                        padding: '0.2rem 0.55rem',
                        borderRadius: '999px',
                        backgroundColor:
                          c.status === 'VERIFIED_RESOLVED'
                            ? 'rgba(22, 101, 52, 0.1)'
                            : c.status === 'IN_REVIEW'
                            ? 'rgba(59, 130, 246, 0.1)'
                            : 'rgba(234, 88, 12, 0.1)',
                        color:
                          c.status === 'VERIFIED_RESOLVED'
                            ? 'var(--govt-success)'
                            : c.status === 'IN_REVIEW'
                            ? 'var(--govt-blue-primary)'
                            : 'var(--govt-warning)',
                      }}
                    >
                      {c.statusLabel}
                    </span>
                  </div>
                  <h3 style={{ fontSize: '1.05rem', fontWeight: 700, color: 'var(--govt-blue-dark)', margin: 0 }}>
                    {c.projectName}
                  </h3>
                  <div style={{ fontSize: '0.8rem', color: 'var(--govt-gray-dark)', marginTop: '0.2rem' }}>
                    Category: <strong>{c.category}</strong> • Filed on: {new Date(c.filedAt).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}
                  </div>
                </div>

                <div style={{ textAlign: 'right', fontSize: '0.75rem', color: 'var(--govt-gray-dark)' }}>
                  <div>Privacy Mode: <strong>{c.isPrivate ? 'Protected' : 'Public'}</strong></div>
                  <div>Contributor: {c.filedBy}</div>
                </div>
              </div>

              {/* Progress Milestones Bar */}
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                  padding: '0.85rem',
                  backgroundColor: 'var(--govt-gray-off-white)',
                  borderRadius: 'var(--radius-md)',
                  marginBottom: '1rem',
                  fontSize: '0.75rem',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', color: 'var(--govt-success)', fontWeight: 700 }}>
                  <CheckCircle2 size={16} /> 1. Ingested & Hashed
                </div>
                <span style={{ color: 'var(--govt-gray-medium)' }}>→</span>
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.35rem',
                    color: c.status === 'IN_REVIEW' || c.status === 'VERIFIED_RESOLVED' ? 'var(--govt-blue-primary)' : 'var(--govt-gray-dark)',
                    fontWeight: c.status === 'IN_REVIEW' ? 700 : 500,
                  }}
                >
                  <Clock size={16} /> 2. JE Inspection Scheduled
                </div>
                <span style={{ color: 'var(--govt-gray-medium)' }}>→</span>
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.35rem',
                    color: c.status === 'VERIFIED_RESOLVED' ? 'var(--govt-success)' : 'var(--govt-gray-dark)',
                    fontWeight: c.status === 'VERIFIED_RESOLVED' ? 700 : 500,
                  }}
                >
                  <ShieldCheck size={16} /> 3. Rectification Verified
                </div>
              </div>

              {/* Grievance Statement */}
              <div style={{ fontSize: '0.85rem', color: 'var(--govt-gray-text)', marginBottom: '0.85rem', lineHeight: 1.4 }}>
                <strong>Citizen Statement:</strong> &ldquo;{c.description}&rdquo;
              </div>

              {/* Official Department Response */}
              {c.departmentResponse && (
                <div
                  style={{
                    backgroundColor: 'rgba(30, 41, 59, 0.03)',
                    borderLeft: '3.5px solid var(--govt-blue-primary)',
                    padding: '0.75rem 1rem',
                    borderRadius: '0 var(--radius-sm) var(--radius-sm) 0',
                    fontSize: '0.8rem',
                  }}
                >
                  <strong style={{ color: 'var(--govt-blue-dark)', display: 'block', marginBottom: '0.2rem' }}>
                    Department Inspection Action:
                  </strong>
                  <span style={{ color: 'var(--govt-gray-dark)' }}>{c.departmentResponse}</span>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
