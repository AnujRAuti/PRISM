import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { evidenceApi, projectApi } from '../../services/api';
import { formatDate, formatFileSize } from '../../utils/helpers';

export default function EvidenceDetail() {
  const { id } = useParams();
  const [evidence, setEvidence] = useState(null);
  const [projectName, setProjectName] = useState('');
  const [downloadUrl, setDownloadUrl] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [analysis, setAnalysis] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const { data } = await evidenceApi.getById(id);
        if (!active) return;
        setEvidence(data);
        if (data.project_id) {
          try {
            const project = await projectApi.getById(data.project_id);
            if (active) setProjectName(project.data.name);
          } catch { /* Project access may be narrower than evidence access. */ }
        }
      } catch (cause) {
        if (active) setError(cause.response?.data?.detail || cause.message || 'Could not load evidence.');
      } finally { if (active) setLoading(false); }
    })();
    return () => { active = false; };
  }, [id]);

  async function fetchDownload() {
    setBusy(true); setError('');
    try {
      const { data } = await evidenceApi.download(id);
      setDownloadUrl(data.download_url);
      window.open(data.download_url, '_blank', 'noopener,noreferrer');
    } catch (cause) { setError(cause.response?.data?.detail || cause.message || 'Download authorization failed.'); }
    finally { setBusy(false); }
  }

  async function runAnalysis() {
    setBusy(true); setError('');
    try {
      const { data } = await evidenceApi.createAnalysisJob({ evidence_id: id, job_type: 'fingerprint' });
      setAnalysis(data);
    } catch (cause) { setError(cause.response?.data?.detail || cause.message || 'Analysis job could not be created.'); }
    finally { setBusy(false); }
  }

  if (loading) return <main style={{ padding: '2rem' }} aria-live="polite">Loading evidence from PRISM…</main>;
  if (error && !evidence) return <main style={{ padding: '2rem' }}><p role="alert">{error}</p><Link to="/evidence">Back to evidence</Link></main>;
  if (!evidence) return null;

  return <main style={{ maxWidth: 960, margin: '0 auto', padding: '2rem' }}>
    <Link to="/reviews">← Back to review queue</Link>
    <h1 style={{ color: 'var(--govt-blue-dark)' }}>{evidence.filename}</h1>
    <p>Evidence record <code>{evidence.id}</code></p>
    {error && <p role="alert" style={{ color: 'var(--govt-danger)' }}>{error}</p>}
    <section aria-label="Evidence metadata" style={{ background: 'white', border: '1px solid var(--govt-gray-medium)', borderRadius: 8, padding: '1rem' }}>
      <dl style={{ display: 'grid', gridTemplateColumns: 'minmax(150px, 1fr) 2fr', gap: '.75rem' }}>
        <dt>Status</dt><dd>{evidence.status}</dd>
        <dt>Content type</dt><dd>{evidence.content_type || 'Not provided'}</dd>
        <dt>File size</dt><dd>{formatFileSize(evidence.file_size)}</dd>
        <dt>Uploaded</dt><dd>{evidence.created_at ? formatDate(evidence.created_at) : 'Not provided'}</dd>
        <dt>Project</dt><dd>{projectName || evidence.project_id || 'No project linked'}</dd>
        <dt>Claim</dt><dd>{evidence.claim_id || 'No claim linked'}</dd>
      </dl>
      <button type="button" disabled={busy} onClick={fetchDownload}>Download original file</button>{' '}
      <button type="button" disabled={busy} onClick={runAnalysis}>Start fingerprint analysis</button>
      {analysis && <pre role="status" style={{ whiteSpace: 'pre-wrap' }}>{JSON.stringify(analysis, null, 2)}</pre>}
      {downloadUrl && <p>Download URL issued by storage service.</p>}
    </section>
    <p style={{ marginTop: '1rem', color: 'var(--govt-gray-dark)' }}>Integrity scores, location, reviewer decisions, and vision findings appear when provided by the backend analysis and review records.</p>
  </main>;
}
