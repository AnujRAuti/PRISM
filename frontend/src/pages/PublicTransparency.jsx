import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { publicationApi } from '../services/api';

export default function PublicTransparency() {
  const { publicId } = useParams();
  const [projects, setProjects] = useState([]);
  const [detail, setDetail] = useState(null);
  const [related, setRelated] = useState({ activities: [], claims: [], evidence: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError('');
    const request = publicId
      ? Promise.all([
        publicationApi.publicProject(publicId),
        publicationApi.publicActivities(publicId),
        publicationApi.publicClaims(publicId),
        publicationApi.publicEvidence(publicId),
      ]).then(([project, activities, claims, evidence]) => {
        if (active) {
          setDetail(project.data);
          setRelated({ activities: activities.data, claims: claims.data, evidence: evidence.data });
        }
      })
      : publicationApi.publicProjects({ limit: 100 }).then(({ data }) => {
        if (active) { setProjects(data); setDetail(null); }
      });
    request.catch((cause) => { if (active) setError(cause.response?.data?.detail || cause.message || 'Public PRISM data is unavailable.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [publicId]);

  return (
    <main style={{ minHeight: '100vh', background: 'var(--govt-gray-off-white)', padding: '32px max(20px, calc((100vw - 1100px) / 2))', color: 'var(--govt-blue-dark)' }}>
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12, marginBottom: 24 }}>
        <div><Link to="/public" style={{ color: 'var(--govt-blue-primary)', fontWeight: 700 }}>PRISM Public Transparency</Link><p style={{ margin: '5px 0 0', color: 'var(--govt-gray-dark)' }}>Only records explicitly published through the authorized review process appear here.</p></div>
        <Link to="/login" style={{ color: 'var(--govt-blue-primary)' }}>Staff sign in</Link>
      </header>
      {error && <div role="alert" style={{ padding: 14, marginBottom: 16, borderRadius: 8, background: '#fef2f2', color: '#991b1b' }}>{error}</div>}
      {loading ? <p>Loading published records…</p> : detail ? (
        <section style={{ background: '#fff', padding: 24, borderRadius: 10, border: '1px solid var(--govt-gray-medium)' }}>
          <Link to="/public">← All published projects</Link>
          <h1 style={{ marginBottom: 8 }}>{detail.name}</h1>
          <p>{detail.description || 'No public description was included in this publication.'}</p>
          <p><strong>Status:</strong> {detail.status} · <strong>Published:</strong> {detail.published_at || 'Not supplied'}</p>
          {detail.provenance && <p><strong>Publication version:</strong> {detail.provenance.publication_version} · <strong>Approval:</strong> {detail.provenance.human_approval_status || 'Not supplied'}</p>}
          <h2>Published activities</h2>{related.activities.length ? <ul>{related.activities.map((item) => <li key={item.public_id}>{item.verb} · {item.occurred_at || 'Date not supplied'}</li>)}</ul> : <p>No activities published.</p>}
          <h2>Published claims</h2>{related.claims.length ? <ul>{related.claims.map((item) => <li key={item.public_id}><strong>{item.title}</strong> — {item.description || 'No public description.'}</li>)}</ul> : <p>No claims published.</p>}
          <h2>Published evidence</h2>{related.evidence.length ? <ul>{related.evidence.map((item) => <li key={item.public_id}>Evidence {item.public_id} · {item.status} · {item.collected_at || 'Date not supplied'} ({item.media.length} media item(s))</li>)}</ul> : <p>No evidence published.</p>}
        </section>
      ) : (
        <section>
          <h1>Published public infrastructure projects</h1>
          {projects.length ? <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 14 }}>{projects.map((project) => (
            <article key={project.public_id} style={{ background: '#fff', padding: 20, borderRadius: 9, border: '1px solid var(--govt-gray-medium)' }}>
              <h2 style={{ marginTop: 0, fontSize: 18 }}>{project.name}</h2><p>{project.description || 'No public description was included in this publication.'}</p><p><strong>{project.status}</strong></p>
              <Link to={`/public/projects/${encodeURIComponent(project.public_id)}`}>View published details →</Link>
            </article>
          ))}</div> : !error && <p>No projects have been published for public access.</p>}
        </section>
      )}
    </main>
  );
}
