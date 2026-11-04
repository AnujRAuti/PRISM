import { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { projectApi } from '../../services/api';

const box = { background: '#fff', border: '1px solid var(--govt-gray-medium)', borderRadius: 9, padding: 18, marginTop: 16 };
const field = { display: 'grid', gap: 5, marginBottom: 10 };
const input = { padding: 9, border: '1px solid var(--govt-gray-medium)', borderRadius: 6, font: 'inherit' };

export default function ProjectDetail() {
  const { id } = useParams();
  const [project, setProject] = useState(null);
  const [activities, setActivities] = useState([]);
  const [claims, setClaims] = useState([]);
  const [name, setName] = useState('');
  const [claimTitle, setClaimTitle] = useState('');
  const [claimDescription, setClaimDescription] = useState('');
  const [activityVerb, setActivityVerb] = useState('');
  const [activityDetails, setActivityDetails] = useState('{}');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setError('');
    try {
      const [projectResponse, activityResponse, claimResponse] = await Promise.all([
        projectApi.getById(id), projectApi.getActivities(id, { limit: 100 }), projectApi.getClaims(id, { limit: 100 }),
      ]);
      setProject(projectResponse.data);
      setName(projectResponse.data.name);
      setActivities(activityResponse.data.items || []);
      setClaims(claimResponse.data.items || []);
    } catch (cause) {
      setError(cause.response?.data?.detail || cause.message || 'Project details could not be loaded.');
    }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  const submit = async (operation) => {
    setBusy(true);
    setError('');
    try { await operation(); await load(); }
    catch (cause) { setError(cause.response?.data?.detail || cause.message || 'Backend operation failed.'); }
    finally { setBusy(false); }
  };

  return (
    <main style={{ maxWidth: 1100, margin: '0 auto', padding: '1.75rem 2rem' }}>
      <Link to="/projects">← Projects</Link>
      {error && <p role="alert" style={{ background: '#fef2f2', color: '#991b1b', padding: 12, borderRadius: 8, marginTop: 14 }}>{error}</p>}
      {!project ? <p>{error ? 'Unable to retrieve this project.' : 'Loading project…'}</p> : <>
        <section style={box}>
          <h1 style={{ marginTop: 0, color: 'var(--govt-blue-dark)' }}>{project.name}</h1>
          <p><strong>Project ID:</strong> <code>{project.id}</code></p>
          <p><strong>Owner:</strong> {project.owner_id}</p>
          <p><strong>Created:</strong> {project.created_at ? new Date(project.created_at).toLocaleString() : 'Not provided'}</p>
          <form onSubmit={(event) => { event.preventDefault(); submit(() => projectApi.update(id, { name: name.trim() })); }} style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <input aria-label="Project name" value={name} onChange={(event) => setName(event.target.value)} minLength={1} maxLength={256} required style={{ ...input, flex: '1 1 280px' }} />
            <button type="submit" disabled={busy || name.trim() === project.name}>Save name</button>
          </form>
        </section>

        <section style={box}>
          <h2>Claims</h2>
          {claims.length ? <ul>{claims.map((claim) => <li key={claim.id}><strong>{claim.title}</strong> — {claim.description || 'No description'} <code>{claim.id}</code></li>)}</ul> : <p>No claims are linked to this project.</p>}
          <form onSubmit={(event) => { event.preventDefault(); submit(async () => { await projectApi.createClaim(id, { title: claimTitle, description: claimDescription || null }); setClaimTitle(''); setClaimDescription(''); }); }}>
            <label style={field}>Claim title<input required maxLength={512} value={claimTitle} onChange={(event) => setClaimTitle(event.target.value)} style={input} /></label>
            <label style={field}>Description<textarea value={claimDescription} onChange={(event) => setClaimDescription(event.target.value)} rows={3} style={input} /></label>
            <button disabled={busy || !claimTitle.trim()} type="submit">Create claim</button>
          </form>
        </section>

        <section style={box}>
          <h2>Project activities</h2>
          {activities.length ? <ul>{activities.map((activity) => <li key={activity.id}><strong>{activity.verb}</strong> · {activity.created_at ? new Date(activity.created_at).toLocaleString() : ''}<pre>{JSON.stringify(activity.details || {}, null, 2)}</pre></li>)}</ul> : <p>No activities are recorded for this project.</p>}
          <form onSubmit={(event) => { event.preventDefault(); submit(async () => { const details = JSON.parse(activityDetails); await projectApi.createActivity(id, { verb: activityVerb, details }); setActivityVerb(''); setActivityDetails('{}'); }); }}>
            <label style={field}>Activity verb<input required maxLength={128} value={activityVerb} onChange={(event) => setActivityVerb(event.target.value)} style={input} /></label>
            <label style={field}>Details (JSON)<textarea value={activityDetails} onChange={(event) => setActivityDetails(event.target.value)} rows={4} style={{ ...input, fontFamily: 'monospace' }} /></label>
            <button disabled={busy || !activityVerb.trim()} type="submit">Record activity</button>
          </form>
        </section>
      </>}
    </main>
  );
}
