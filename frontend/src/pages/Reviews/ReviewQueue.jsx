import React, { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useApp } from '../../context/AppContext';
import { IntegrityArc } from '../../components/ui/IntegrityArc';
import {
  Inbox,
  Filter,
  CheckSquare,
  Square,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Clock,
  ArrowUpDown,
  SlidersHorizontal,
  Download,
  Eye,
  Info,
  MapPin,
  Sparkles,
  Layers,
  Check,
  Search,
} from 'lucide-react';

export default function ReviewQueue() {
  const navigate = useNavigate();
  const {
    evidenceList,
    density,
    setDensity,
    selectedEvidenceIds,
    toggleSelectEvidence,
    selectAllEvidence,
    clearSelection,
    approveEvidence,
    rejectEvidence,
    flagEvidence,
    batchApprove,
    batchFlag,
    addToast,
  } = useApp();

  const [activeTab, setActiveTab] = useState('ALL');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedRiskFilter, setSelectedRiskFilter] = useState('ALL');
  const [selectedStatusFilter, setSelectedStatusFilter] = useState('ALL');
  const [activeRowIndex, setActiveRowIndex] = useState(0);

  // Decision Modal State (for 20-character rationale requirement)
  const [decisionModal, setDecisionModal] = useState(null); // { id, action: 'REJECT' | 'FLAG', item }
  const [decisionRationale, setDecisionRationale] = useState('');

  // Filter pipeline
  const filteredList = (evidenceList || []).filter((item) => {
    if (activeTab === 'PENDING' && item.auditStatus !== 'PENDING' && item.auditStatus !== 'FLAGGED') return false;
    if (activeTab === 'CRITICAL' && item.riskLevel !== 'CRITICAL' && item.riskLevel !== 'HIGH') return false;
    if (activeTab === 'DUPLICATES' && !item.detectedAnomalies?.some((a) => a.type?.includes('DUPLICATE'))) return false;
    if (
      activeTab === 'GEOFENCE' &&
      !item.detectedAnomalies?.some((a) => a.type?.includes('LOCATION') || a.type?.includes('IMPOSSIBLE'))
    )
      return false;
    if (activeTab === 'PMGSY' && !item.scheme?.includes('PMGSY')) return false;
    if (activeTab === 'JJM' && !item.scheme?.includes('Jal Jeevan')) return false;

    if (selectedRiskFilter !== 'ALL' && item.riskLevel !== selectedRiskFilter) return false;
    if (selectedStatusFilter !== 'ALL' && item.auditStatus !== selectedStatusFilter) return false;

    if (searchQuery.trim() !== '') {
      const q = searchQuery.toLowerCase();
      const match =
        item.id?.toLowerCase().includes(q) ||
        item.title?.toLowerCase().includes(q) ||
        item.projectName?.toLowerCase().includes(q) ||
        item.scheme?.toLowerCase().includes(q) ||
        item.location?.district?.toLowerCase().includes(q) ||
        item.location?.state?.toLowerCase().includes(q) ||
        item.sha256?.toLowerCase().includes(q);
      if (!match) return false;
    }

    return true;
  });

  useEffect(() => {
    setActiveRowIndex((prev) => Math.min(prev, Math.max(filteredList.length - 1, 0)));
  }, [filteredList.length]);

  // Keyboard navigation & hotkeys
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (['INPUT', 'TEXTAREA'].includes(e.target?.tagName)) return;
      if (filteredList.length === 0) return;

      const currentItem = filteredList[activeRowIndex];
      if (e.key === 'j' || e.key === 'ArrowDown') {
        e.preventDefault();
        setActiveRowIndex((prev) => Math.min(prev + 1, filteredList.length - 1));
      } else if (e.key === 'k' || e.key === 'ArrowUp') {
        e.preventDefault();
        setActiveRowIndex((prev) => Math.max(prev - 1, 0));
      } else if (e.key === 'Enter' && currentItem) {
        e.preventDefault();
        navigate(`/evidence/${currentItem.id}`);
      } else if (e.key === 'a' && currentItem) {
        e.preventDefault();
        approveEvidence(currentItem.id, 'Keyboard shortcut approval upon visual check');
      } else if (e.key === 'r' && currentItem) {
        e.preventDefault();
        setDecisionModal({ id: currentItem.id, action: 'REJECT', item: currentItem });
        setDecisionRationale('');
      } else if (e.key === 'f' && currentItem) {
        e.preventDefault();
        setDecisionModal({ id: currentItem.id, action: 'FLAG', item: currentItem });
        setDecisionRationale('');
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [activeRowIndex, filteredList, approveEvidence, navigate]);

  const isAllSelected =
    filteredList.length > 0 && filteredList.every((item) => selectedEvidenceIds.includes(item.id));

  const toggleSelectAll = () => {
    if (isAllSelected) {
      clearSelection();
    } else {
      selectAllEvidence(filteredList.map((item) => item.id));
    }
  };

  const handleExportCsv = () => {
    const headers = ['Evidence ID', 'Project ID', 'Scheme', 'State', 'District', 'Integrity Score', 'Risk Level', 'Audit Status', 'SHA256'];
    const rows = filteredList.map((e) => [
      e.id,
      e.projectId,
      `"${e.scheme}"`,
      `"${e.location?.state}"`,
      `"${e.location?.district}"`,
      e.integrityScore,
      e.riskLevel,
      e.auditStatus,
      e.sha256,
    ]);
    const csvContent =
      'data:text/csv;charset=utf-8,' + [headers.join(','), ...rows.map((r) => r.join(','))].join('\n');
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement('a');
    link.setAttribute('href', encodedUri);
    link.setAttribute('download', `PRISM_Review_Queue_${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);

    addToast({
      title: 'Review Queue Exported',
      description: `CSV file with ${filteredList.length} evidence records generated.`,
      type: 'success',
    });
  };

  const submitDecision = () => {
    if (!decisionModal) return;
    if (decisionRationale.trim().length < 20) {
      addToast({
        title: 'Rationale Required',
        description: 'Statutory rules require minimum 20 characters explanation.',
        type: 'error',
      });
      return;
    }

    if (decisionModal.action === 'REJECT') {
      rejectEvidence(decisionModal.id, decisionRationale);
    } else if (decisionModal.action === 'FLAG') {
      flagEvidence(decisionModal.id, decisionRationale);
    }
    setDecisionModal(null);
    setDecisionRationale('');
  };

  return (
    <div style={{ padding: '1.5rem 2rem', maxWidth: '1440px', margin: '0 auto' }}>
      {/* Top Header & Fast Filter Strip */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '1rem',
          paddingBottom: '1rem',
          borderBottom: '1px solid var(--govt-gray-medium, #e2e8f0)',
          marginBottom: '1.25rem',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <h1
              style={{
                margin: 0,
                fontSize: '1.5rem',
                fontWeight: 800,
                color: 'var(--govt-blue-dark, #0f172a)',
                letterSpacing: '-0.02em',
              }}
            >
              Evidence Review Queue
            </h1>
            <span
              style={{
                fontSize: '0.75rem',
                padding: '0.2rem 0.6rem',
                borderRadius: '4px',
                backgroundColor: 'var(--govt-gray-light)',
                border: '1px solid var(--govt-gray-medium)',
                color: 'var(--govt-gray-title)',
                fontWeight: 700,
                fontFamily: 'monospace',
              }}
            >
              {filteredList.length} records
            </span>
          </div>
          <p style={{ margin: '0.35rem 0 0', fontSize: '0.8rem', color: 'var(--govt-gray-dark)' }}>
            Keyboard-first triage queue: Use <kbd style={{ padding: '0.1rem 0.35rem', borderRadius: '3px', backgroundColor: 'var(--govt-gray-light)', border: '1px solid var(--govt-gray-medium)', fontFamily: 'monospace' }}>j</kbd>/<kbd style={{ padding: '0.1rem 0.35rem', borderRadius: '3px', backgroundColor: 'var(--govt-gray-light)', border: '1px solid var(--govt-gray-medium)', fontFamily: 'monospace' }}>k</kbd> to move, <kbd style={{ padding: '0.1rem 0.35rem', borderRadius: '3px', backgroundColor: 'var(--govt-gray-light)', border: '1px solid var(--govt-gray-medium)', fontFamily: 'monospace' }}>a</kbd> approve, <kbd style={{ padding: '0.1rem 0.35rem', borderRadius: '3px', backgroundColor: 'var(--govt-gray-light)', border: '1px solid var(--govt-gray-medium)', fontFamily: 'monospace' }}>r</kbd> reject, <kbd style={{ padding: '0.1rem 0.35rem', borderRadius: '3px', backgroundColor: 'var(--govt-gray-light)', border: '1px solid var(--govt-gray-medium)', fontFamily: 'monospace' }}>f</kbd> flag, <kbd style={{ padding: '0.1rem 0.35rem', borderRadius: '3px', backgroundColor: 'var(--govt-gray-light)', border: '1px solid var(--govt-gray-medium)', fontFamily: 'monospace' }}>Enter</kbd> inspect.
          </p>
        </div>

        {/* View Controls & Density Switcher */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <div
            style={{
              display: 'inline-flex',
              backgroundColor: 'var(--govt-gray-light)',
              borderRadius: '6px',
              padding: '2px',
              border: '1px solid var(--govt-gray-medium)',
            }}
          >
            <button
              type="button"
              onClick={() => setDensity('comfortable')}
              style={{
                padding: '0.35rem 0.75rem',
                borderRadius: '4px',
                border: 'none',
                cursor: 'pointer',
                fontSize: '0.75rem',
                fontWeight: density === 'comfortable' ? 700 : 500,
                backgroundColor: density === 'comfortable' ? '#ffffff' : 'transparent',
                color: density === 'comfortable' ? 'var(--govt-blue-primary)' : 'var(--govt-gray-dark)',
                boxShadow: density === 'comfortable' ? 'var(--shadow-xs)' : 'none',
              }}
            >
              Comfortable
            </button>
            <button
              type="button"
              onClick={() => setDensity('compact')}
              style={{
                padding: '0.35rem 0.75rem',
                borderRadius: '4px',
                border: 'none',
                cursor: 'pointer',
                fontSize: '0.75rem',
                fontWeight: density === 'compact' ? 700 : 500,
                backgroundColor: density === 'compact' ? '#ffffff' : 'transparent',
                color: density === 'compact' ? 'var(--govt-blue-primary)' : 'var(--govt-gray-dark)',
                boxShadow: density === 'compact' ? 'var(--shadow-xs)' : 'none',
              }}
            >
              Compact
            </button>
          </div>

          <button
            type="button"
            onClick={handleExportCsv}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.35rem',
              padding: '0.45rem 0.85rem',
              borderRadius: '6px',
              backgroundColor: '#ffffff',
              border: '1px solid var(--govt-gray-medium)',
              fontSize: '0.775rem',
              fontWeight: 600,
              color: 'var(--govt-gray-title)',
              cursor: 'pointer',
            }}
          >
            <Download size={14} />
            <span>Export CSV</span>
          </button>
        </div>
      </div>

      {/* Tabs Row */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          gap: '0.5rem',
          borderBottom: '1px solid var(--govt-gray-medium)',
          paddingBottom: '0.5rem',
          marginBottom: '1rem',
        }}
      >
        {[
          { id: 'ALL', label: 'All Submissions' },
          { id: 'PENDING', label: 'Pending Action' },
          { id: 'CRITICAL', label: 'Critical Risk' },
          { id: 'DUPLICATES', label: 'Duplicate Warnings' },
          { id: 'GEOFENCE', label: 'Geofence / Travel' },
          { id: 'PMGSY', label: 'PMGSY Roads' },
          { id: 'JJM', label: 'Jal Jeevan Water' },
        ].map((tab) => {
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveTab(tab.id)}
              style={{
                padding: '0.4rem 0.85rem',
                borderRadius: '6px',
                border: 'none',
                fontSize: '0.8rem',
                fontWeight: isActive ? 700 : 500,
                backgroundColor: isActive ? 'var(--govt-blue-primary)' : 'transparent',
                color: isActive ? '#ffffff' : 'var(--govt-gray-dark)',
                cursor: 'pointer',
                transition: 'all 0.15s ease',
              }}
            >
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Filters Toolbar */}
      <div
        style={{
          backgroundColor: '#ffffff',
          border: '1px solid var(--govt-gray-medium)',
          borderRadius: '8px',
          padding: '0.75rem 1rem',
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '1rem',
          marginBottom: '1rem',
          fontSize: '0.8rem',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flex: 1, minWidth: '220px' }}>
          <Search size={15} color="var(--govt-gray-dark)" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search by ID, scheme, district, SHA-256..."
            style={{
              width: '100%',
              maxWidth: '320px',
              border: 'none',
              outline: 'none',
              fontSize: '0.8rem',
              color: 'var(--govt-gray-title)',
            }}
          />
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
            <span style={{ color: 'var(--govt-gray-dark)', fontWeight: 600 }}>Risk:</span>
            <select
              value={selectedRiskFilter}
              onChange={(e) => setSelectedRiskFilter(e.target.value)}
              style={{
                padding: '0.35rem 0.65rem',
                borderRadius: '4px',
                border: '1px solid var(--govt-gray-medium)',
                backgroundColor: '#ffffff',
                fontSize: '0.775rem',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              <option value="ALL">All Risk Levels</option>
              <option value="LOW">Low Risk</option>
              <option value="MEDIUM">Medium Risk</option>
              <option value="HIGH">High Risk</option>
              <option value="CRITICAL">Critical Flag</option>
            </select>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
            <span style={{ color: 'var(--govt-gray-dark)', fontWeight: 600 }}>Status:</span>
            <select
              value={selectedStatusFilter}
              onChange={(e) => setSelectedStatusFilter(e.target.value)}
              style={{
                padding: '0.35rem 0.65rem',
                borderRadius: '4px',
                border: '1px solid var(--govt-gray-medium)',
                backgroundColor: '#ffffff',
                fontSize: '0.775rem',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              <option value="ALL">All Statuses</option>
              <option value="PENDING">Pending</option>
              <option value="APPROVED">Approved</option>
              <option value="REJECTED">Rejected</option>
              <option value="FLAGGED">Flagged</option>
              <option value="OVERRIDDEN">Overridden</option>
            </select>
          </div>
        </div>
      </div>

      {/* Batch Operations Bar */}
      {selectedEvidenceIds.length > 0 && (
        <div
          style={{
            backgroundColor: 'var(--govt-blue-light, #eff6ff)',
            border: '1px solid var(--govt-blue-accent, #2563eb)',
            borderRadius: '8px',
            padding: '0.65rem 1rem',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            marginBottom: '1rem',
            fontSize: '0.8rem',
            animation: 'fadeIn 0.15s ease',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <CheckSquare size={16} color="var(--govt-blue-primary)" />
            <span style={{ fontWeight: 700, color: 'var(--govt-blue-dark)' }}>
              {selectedEvidenceIds.length} item(s) selected
            </span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <button
              type="button"
              onClick={() => batchApprove(selectedEvidenceIds)}
              style={{
                padding: '0.35rem 0.75rem',
                borderRadius: '4px',
                backgroundColor: 'var(--govt-success)',
                color: '#ffffff',
                fontSize: '0.75rem',
                fontWeight: 700,
                border: 'none',
                cursor: 'pointer',
              }}
            >
              Batch Approve
            </button>
            <button
              type="button"
              onClick={() => batchFlag(selectedEvidenceIds)}
              style={{
                padding: '0.35rem 0.75rem',
                borderRadius: '4px',
                backgroundColor: 'var(--govt-warning)',
                color: '#ffffff',
                fontSize: '0.75rem',
                fontWeight: 700,
                border: 'none',
                cursor: 'pointer',
              }}
            >
              Batch Flag
            </button>
            <button
              type="button"
              onClick={clearSelection}
              style={{
                background: 'none',
                border: 'none',
                color: 'var(--govt-gray-dark)',
                fontSize: '0.75rem',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              Clear
            </button>
          </div>
        </div>
      )}

      {/* Evidence Table */}
      <div
        style={{
          backgroundColor: '#ffffff',
          border: '1px solid var(--govt-gray-medium)',
          borderRadius: 'var(--radius-lg, 12px)',
          boxShadow: 'var(--shadow-sm)',
          overflow: 'hidden',
        }}
      >
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem', textAlign: 'left' }}>
            <thead>
              <tr
                style={{
                  backgroundColor: 'var(--govt-gray-off-white)',
                  borderBottom: '1px solid var(--govt-gray-medium)',
                  color: 'var(--govt-gray-dark)',
                  textTransform: 'uppercase',
                  fontSize: '0.725rem',
                  letterSpacing: '0.04em',
                }}
              >
                <th style={{ padding: '0.75rem 1rem', width: '40px' }}>
                  <input
                    type="checkbox"
                    checked={isAllSelected}
                    onChange={toggleSelectAll}
                    style={{ cursor: 'pointer' }}
                  />
                </th>
                <th style={{ padding: '0.75rem 1rem' }}>Evidence ID</th>
                <th style={{ padding: '0.75rem 1rem' }}>Photo & Description</th>
                <th style={{ padding: '0.75rem 1rem' }}>Project & Location</th>
                <th style={{ padding: '0.75rem 1rem' }}>Integrity</th>
                <th style={{ padding: '0.75rem 1rem' }}>Detected Signals</th>
                <th style={{ padding: '0.75rem 1rem' }}>Status</th>
                <th style={{ padding: '0.75rem 1rem', textAlign: 'right' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredList.length === 0 ? (
                <tr>
                  <td colSpan={8} style={{ padding: '2.5rem', textAlign: 'center', color: 'var(--govt-gray-dark)' }}>
                    No evidence submissions match the selected filters.
                  </td>
                </tr>
              ) : (
                filteredList.map((item, idx) => {
                  const isRowActive = idx === activeRowIndex;
                  const isChecked = selectedEvidenceIds.includes(item.id);

                  return (
                    <tr
                      key={item.id}
                      onClick={() => setActiveRowIndex(idx)}
                      style={{
                        borderBottom: '1px solid var(--govt-gray-light)',
                        backgroundColor: isRowActive ? 'var(--govt-blue-light, #eff6ff)' : isChecked ? '#f8fafc' : '#ffffff',
                        transition: 'background-color 0.1s ease',
                      }}
                    >
                      <td style={{ padding: density === 'compact' ? '0.4rem 1rem' : '0.85rem 1rem' }}>
                        <input
                          type="checkbox"
                          checked={isChecked}
                          onChange={() => toggleSelectEvidence(item.id)}
                          style={{ cursor: 'pointer' }}
                        />
                      </td>

                      <td style={{ padding: density === 'compact' ? '0.4rem 1rem' : '0.85rem 1rem' }}>
                        <Link
                          to={`/evidence/${item.id}`}
                          style={{
                            fontFamily: 'monospace',
                            fontWeight: 700,
                            color: 'var(--govt-blue-primary)',
                            textDecoration: 'none',
                          }}
                        >
                          {item.id}
                        </Link>
                        {density !== 'compact' && (
                          <div style={{ fontSize: '0.7rem', color: 'var(--govt-gray-dark)', marginTop: '2px' }}>
                            {new Date(item.capturedAt).toLocaleDateString()}
                          </div>
                        )}
                      </td>

                      <td style={{ padding: density === 'compact' ? '0.4rem 1rem' : '0.85rem 1rem' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                          <img
                            src={item.imageUrl}
                            alt=""
                            style={{
                              width: density === 'compact' ? '32px' : '44px',
                              height: density === 'compact' ? '32px' : '44px',
                              borderRadius: '4px',
                              objectFit: 'cover',
                              backgroundColor: '#0f172a',
                              flexShrink: 0,
                            }}
                          />
                          <div style={{ minWidth: 0 }}>
                            <div
                              style={{
                                fontWeight: 600,
                                color: 'var(--govt-gray-title)',
                                whiteSpace: 'nowrap',
                                overflow: 'hidden',
                                textOverflow: 'ellipsis',
                                maxWidth: '240px',
                              }}
                            >
                              {item.title}
                            </div>
                            {density !== 'compact' && (
                              <div style={{ fontSize: '0.725rem', color: 'var(--govt-gray-dark)', fontStyle: 'italic' }}>
                                "{item.claimText?.substring(0, 48)}..."
                              </div>
                            )}
                          </div>
                        </div>
                      </td>

                      <td style={{ padding: density === 'compact' ? '0.4rem 1rem' : '0.85rem 1rem' }}>
                        <div style={{ fontWeight: 600, color: 'var(--govt-blue-dark)' }}>{item.scheme}</div>
                        <div style={{ fontSize: '0.725rem', color: 'var(--govt-gray-dark)' }}>
                          {item.location?.district}, {item.location?.state}
                        </div>
                      </td>

                      <td style={{ padding: density === 'compact' ? '0.4rem 1rem' : '0.85rem 1rem' }}>
                        <IntegrityArc score={item.integrityScore} size="sm" showLabel />
                      </td>

                      <td style={{ padding: density === 'compact' ? '0.4rem 1rem' : '0.85rem 1rem' }}>
                        {item.detectedAnomalies && item.detectedAnomalies.length > 0 ? (
                          <span
                            style={{
                              display: 'inline-block',
                              padding: '0.15rem 0.5rem',
                              borderRadius: '4px',
                              fontSize: '0.7rem',
                              fontWeight: 700,
                              backgroundColor: 'rgba(220, 38, 38, 0.1)',
                              color: 'var(--govt-danger)',
                            }}
                          >
                            ⚠ {item.detectedAnomalies[0].title?.substring(0, 32)}
                          </span>
                        ) : (
                          <span style={{ fontSize: '0.725rem', color: 'var(--govt-success)', fontWeight: 600 }}>
                            ✓ 7 Signals Pass
                          </span>
                        )}
                      </td>

                      <td style={{ padding: density === 'compact' ? '0.4rem 1rem' : '0.85rem 1rem' }}>
                        <span
                          style={{
                            padding: '0.15rem 0.5rem',
                            borderRadius: '4px',
                            fontSize: '0.7rem',
                            fontWeight: 700,
                            textTransform: 'uppercase',
                            backgroundColor:
                              item.auditStatus === 'APPROVED'
                                ? 'rgba(5, 150, 105, 0.12)'
                                : item.auditStatus === 'REJECTED' || item.auditStatus === 'FLAGGED'
                                ? 'rgba(220, 38, 38, 0.12)'
                                : 'var(--govt-gray-light)',
                            color:
                              item.auditStatus === 'APPROVED'
                                ? 'var(--govt-success)'
                                : item.auditStatus === 'REJECTED' || item.auditStatus === 'FLAGGED'
                                ? 'var(--govt-danger)'
                                : 'var(--govt-gray-title)',
                          }}
                        >
                          {item.auditStatus}
                        </span>
                      </td>

                      <td style={{ padding: density === 'compact' ? '0.4rem 1rem' : '0.85rem 1rem', textAlign: 'right' }}>
                        <div style={{ display: 'inline-flex', alignItems: 'center', gap: '0.35rem' }}>
                          <button
                            type="button"
                            onClick={() => approveEvidence(item.id)}
                            title="Quick Approve"
                            style={{
                              padding: '0.3rem 0.6rem',
                              borderRadius: '4px',
                              backgroundColor: 'var(--govt-success)',
                              color: '#ffffff',
                              border: 'none',
                              fontSize: '0.725rem',
                              fontWeight: 700,
                              cursor: 'pointer',
                            }}
                          >
                            Approve
                          </button>
                          <button
                            type="button"
                            onClick={() => {
                              setDecisionModal({ id: item.id, action: 'FLAG', item });
                              setDecisionRationale('');
                            }}
                            title="Flag for Inspection"
                            style={{
                              padding: '0.3rem 0.6rem',
                              borderRadius: '4px',
                              backgroundColor: 'var(--govt-warning)',
                              color: '#ffffff',
                              border: 'none',
                              fontSize: '0.725rem',
                              fontWeight: 700,
                              cursor: 'pointer',
                            }}
                          >
                            Flag
                          </button>
                          <button
                            type="button"
                            onClick={() => {
                              setDecisionModal({ id: item.id, action: 'REJECT', item });
                              setDecisionRationale('');
                            }}
                            title="Reject Evidence"
                            style={{
                              padding: '0.3rem 0.6rem',
                              borderRadius: '4px',
                              backgroundColor: 'var(--govt-danger)',
                              color: '#ffffff',
                              border: 'none',
                              fontSize: '0.725rem',
                              fontWeight: 700,
                              cursor: 'pointer',
                            }}
                          >
                            Reject
                          </button>
                          <Link
                            to={`/evidence/${item.id}`}
                            title="Deep Inspect"
                            style={{
                              padding: '0.3rem 0.5rem',
                              borderRadius: '4px',
                              backgroundColor: 'var(--govt-gray-light)',
                              border: '1px solid var(--govt-gray-medium)',
                              color: 'var(--govt-blue-primary)',
                              fontSize: '0.725rem',
                              fontWeight: 700,
                              textDecoration: 'none',
                            }}
                          >
                            Inspect
                          </Link>
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Decision Rationale Modal (Mandating >= 20 characters as required by doc) */}
      {decisionModal && (
        <div
          role="dialog"
          aria-modal="true"
          style={{
            position: 'fixed',
            inset: 0,
            zIndex: 9999,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            backgroundColor: 'rgba(15, 23, 42, 0.6)',
            padding: '1rem',
          }}
        >
          <div
            style={{
              width: '100%',
              maxWidth: '480px',
              backgroundColor: '#ffffff',
              borderRadius: 'var(--radius-lg, 12px)',
              padding: '1.5rem',
              boxShadow: 'var(--shadow-xl)',
              display: 'flex',
              flexDirection: 'column',
              gap: '1rem',
            }}
          >
            <h3 style={{ margin: 0, fontSize: '1.05rem', fontWeight: 700, color: 'var(--govt-blue-dark)' }}>
              {decisionModal.action === 'REJECT' ? 'Record Evidence Rejection' : 'Flag for Physical Inspection'}
            </h3>
            <p style={{ margin: 0, fontSize: '0.8rem', color: 'var(--govt-gray-dark)' }}>
              Statutory regulations mandate entering a detailed justification (minimum 20 characters) for item{' '}
              <strong>{decisionModal.id}</strong>.
            </p>

            <div>
              <textarea
                rows={4}
                value={decisionRationale}
                onChange={(e) => setDecisionRationale(e.target.value)}
                placeholder="Enter mandatory audit rationale (minimum 20 characters)..."
                style={{
                  width: '100%',
                  padding: '0.75rem',
                  borderRadius: '6px',
                  border: '1px solid var(--govt-gray-medium)',
                  fontSize: '0.825rem',
                  fontFamily: 'inherit',
                  outline: 'none',
                  boxSizing: 'border-box',
                }}
              />
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  fontSize: '0.725rem',
                  marginTop: '0.25rem',
                  color: decisionRationale.trim().length >= 20 ? 'var(--govt-success)' : 'var(--govt-danger)',
                }}
              >
                <span>{decisionRationale.trim().length}/20 characters minimum</span>
                {decisionRationale.trim().length >= 20 && <span>✓ Requirement satisfied</span>}
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem', marginTop: '0.5rem' }}>
              <button
                type="button"
                onClick={() => setDecisionModal(null)}
                style={{
                  padding: '0.5rem 1rem',
                  borderRadius: '6px',
                  backgroundColor: 'var(--govt-gray-light)',
                  border: '1px solid var(--govt-gray-medium)',
                  fontSize: '0.8rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={submitDecision}
                disabled={decisionRationale.trim().length < 20}
                style={{
                  padding: '0.5rem 1rem',
                  borderRadius: '6px',
                  backgroundColor:
                    decisionModal.action === 'REJECT' ? 'var(--govt-danger)' : 'var(--govt-warning)',
                  color: '#ffffff',
                  fontSize: '0.8rem',
                  fontWeight: 700,
                  border: 'none',
                  cursor: decisionRationale.trim().length < 20 ? 'not-allowed' : 'pointer',
                  opacity: decisionRationale.trim().length < 20 ? 0.5 : 1,
                }}
              >
                Confirm {decisionModal.action === 'REJECT' ? 'Rejection' : 'Flag'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
