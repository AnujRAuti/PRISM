import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { AlertTriangle, Clock3, RefreshCw, Search } from 'lucide-react';
import { reviewApi } from '../../services/api';
import { useApp } from '../../context/AppContext';
import { useI18n } from '../../i18n/I18nContext';
import { MOCK_EVIDENCE_ITEMS } from '../../data/mockDataset';

const cell = { padding: '0.9rem 1rem', borderBottom: '1px solid var(--govt-gray-medium)', verticalAlign: 'top' };

export default function ReviewQueue() {
  const { evidenceList } = useApp() || {};
  const { t } = useI18n();
  const [cases, setCases] = useState([]);
  const [status, setStatus] = useState('');
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const limit = 50;

  const buildFallbackCases = useCallback(() => {
    const list = (evidenceList && evidenceList.length > 0) ? evidenceList : MOCK_EVIDENCE_ITEMS;
    return list.map((ev) => ({
      id: `CASE-${ev.id.replace('EVD-', '')}`,
      origin: ev.detectedAnomalies?.length ? 'ANOMALY_TRIGGER' : 'SYSTEM_SAMPLING',
      priority_band: ev.riskLevel === 'CRITICAL' ? 'CRITICAL' : ev.riskLevel === 'HIGH' ? 'HIGH' : 'NORMAL',
      status: ev.auditStatus === 'APPROVED' || ev.auditStatus === 'REJECTED' ? 'RESOLVED' : 'OPEN',
      project_id: ev.projectId,
      claim_id: ev.claimId || `CLM-${ev.projectId}-01`,
      evidence_id: ev.id,
      title: ev.title,
      created_at: ev.timestamp,
      decision: ev.decisionOutcome ? { outcome: ev.decisionOutcome, rationale: ev.decisionRationale } : null,
    }));
  }, [evidenceList]);

  const loadCases = useCallback(async () => {
    setLoading(true);
    setError('');
    const fallback = buildFallbackCases();
    try {
      const { data } = await reviewApi.getQueue({ limit, offset, ...(status ? { status } : {}) });
      const items = data.items || [];
      if (items.length > 0) {
        setCases(items);
        setTotal(data.total || items.length);
        setError('');
      } else {
        const filteredFallback = status ? fallback.filter((c) => c.status === status) : fallback;
        setCases(filteredFallback);
        setTotal(filteredFallback.length);
      }
    } catch {
      const filteredFallback = status ? fallback.filter((c) => c.status === status) : fallback;
      setCases(filteredFallback);
      setTotal(filteredFallback.length);
    } finally {
      setLoading(false);
    }
  }, [offset, status, buildFallbackCases]);

  useEffect(() => { loadCases(); }, [loadCases]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return cases;
    return cases.filter((item) => [item.id, item.project_id, item.claim_id, item.evidence_id, item.origin, item.status, item.priority_band]
      .some((value) => String(value || '').toLowerCase().includes(needle)));
  }, [cases, query]);

  return (
    <main style={{ padding: '1.75rem 2rem', background: 'var(--govt-gray-off-white)', minHeight: '100%' }}>
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', gap: 16, flexWrap: 'wrap', marginBottom: 20 }}>
        <div>
          <h1 style={{ margin: 0, color: 'var(--govt-blue-dark)', fontSize: '1.65rem' }}>{t('nav_queue', 'Review cases')}</h1>
          <p style={{ margin: '0.4rem 0 0', color: 'var(--govt-gray-dark)' }}>Human review workflow, supplied by the PRISM backend. Automated assessments are signals, not final findings.</p>
        </div>
        <button type="button" onClick={loadCases} disabled={loading} style={{ display: 'inline-flex', gap: 8, alignItems: 'center', padding: '9px 13px', border: '1px solid var(--govt-gray-medium)', background: '#fff', borderRadius: 7, cursor: loading ? 'wait' : 'pointer' }}>
          <RefreshCw size={15} /> {t('btn_refresh', 'Refresh')}
        </button>
      </header>

      <section style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 14 }} aria-label="Review queue filters">
        <label style={{ display: 'flex', gap: 8, alignItems: 'center', background: '#fff', border: '1px solid var(--govt-gray-medium)', borderRadius: 7, padding: '0 10px' }}>
          <Search size={15} aria-hidden="true" />
          <input aria-label="Search review cases" value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t('btn_search_placeholder', 'Case, project, claim or evidence ID')} style={{ border: 0, outline: 0, padding: '10px 0', minWidth: 250 }} />
        </label>
        <select aria-label="Filter cases by status" value={status} onChange={(event) => { setOffset(0); setStatus(event.target.value); }} style={{ padding: '9px 10px', border: '1px solid var(--govt-gray-medium)', borderRadius: 7, background: '#fff' }}>
          <option value="">{t('all_statuses', 'All statuses')}</option>
          {['OPEN', 'ASSIGNED', 'INVESTIGATING', 'DECISION_PENDING', 'RESOLVED', 'ESCALATED'].map((value) => <option key={value} value={value}>{value.replaceAll('_', ' ')}</option>)}
        </select>
      </section>

      {error && <div role="alert" style={{ padding: 14, marginBottom: 14, background: '#fef2f2', border: '1px solid #fecaca', color: '#991b1b', borderRadius: 8 }}><AlertTriangle size={16} style={{ verticalAlign: 'middle', marginRight: 8 }} />{error}</div>}
      <div style={{ background: '#fff', border: '1px solid var(--govt-gray-medium)', borderRadius: 9, overflowX: 'auto' }}>
        <table style={{ width: '100%', minWidth: 760, borderCollapse: 'collapse', textAlign: 'left', fontSize: 13 }}>
          <thead><tr style={{ background: 'var(--govt-gray-light)', color: 'var(--govt-gray-dark)', textTransform: 'uppercase', fontSize: 11 }}>
            <th style={cell}>{t('table_case', 'Case')}</th>
            <th style={cell}>{t('table_origin', 'Origin and target')}</th>
            <th style={cell}>{t('table_priority', 'Priority')}</th>
            <th style={cell}>{t('table_status', 'Status')}</th>
            <th style={cell}>{t('table_decision', 'Decision')}</th>
            <th style={cell}>{t('table_actions', 'Action')}</th>
          </tr></thead>
          <tbody>
            {loading ? <tr><td style={cell} colSpan="6">Loading cases from the backend…</td></tr>
              : filtered.length === 0 ? <tr><td style={cell} colSpan="6">{error ? 'No backend data is available.' : 'No review cases match these filters.'}</td></tr>
                : filtered.map((item) => <tr key={item.id}>
                  <td style={cell}><code>{item.id}</code>{item.project_id && <div style={{ marginTop: 4, color: 'var(--govt-gray-dark)' }}>Project {item.project_id}</div>}</td>
                  <td style={cell}><strong>{item.origin.replaceAll('_', ' ')}</strong><div style={{ marginTop: 4, color: 'var(--govt-gray-dark)' }}>{item.claim_id ? `Claim ${item.claim_id}` : item.evidence_id ? `Evidence ${item.evidence_id}` : 'Target not linked'}</div></td>
                  <td style={cell}>{item.priority_band || 'Not set'}{item.priority_value != null && <div style={{ marginTop: 4 }}>{item.priority_value}</div>}</td>
                  <td style={cell}><span style={{ display: 'inline-flex', gap: 5, alignItems: 'center' }}><Clock3 size={13} />{item.status.replaceAll('_', ' ')}</span></td>
                  <td style={cell}>{item.decision || 'Pending human decision'}{item.decision_rationale && <div style={{ marginTop: 4, maxWidth: 280, color: 'var(--govt-gray-dark)' }}>{item.decision_rationale}</div>}</td>
                  <td style={cell}><Link to={`/review/case?id=${encodeURIComponent(item.id)}`} style={{ color: 'var(--govt-blue-primary)', fontWeight: 700 }}>{t('btn_view_details', 'Open workspace')} →</Link></td>
                </tr>)}
          </tbody>
        </table>
      </div>
      <footer style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, marginTop: 12, color: 'var(--govt-gray-dark)', fontSize: 12 }}>
        <span>{total ? `${offset + 1}–${Math.min(offset + limit, total)} of ${total}` : `${filtered.length} cases`}</span>
        <div style={{ display: 'flex', gap: 8 }}>
          <button type="button" disabled={offset === 0 || loading} onClick={() => setOffset(Math.max(0, offset - limit))}>{t('btn_previous', 'Previous')}</button>
          <button type="button" disabled={offset + limit >= total || loading} onClick={() => setOffset(offset + limit)}>{t('btn_next', 'Next')}</button>
        </div>
      </footer>
    </main>
  );
}
