import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { projectApi } from '../../services/api';

export default function CreateProject() {
  const navigate = useNavigate();
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [created, setCreated] = useState(null);

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const { data } = await projectApi.create({ name: name.trim() });
      setCreated(data);
    } catch (cause) {
      setError(cause.response?.data?.detail || cause.message || 'Project creation failed.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <main style={{ maxWidth: 760, margin: '0 auto', padding: '2rem' }}>
      <Link to="/projects">← Projects</Link>
      <h1 style={{ color: 'var(--govt-blue-dark)' }}>Create project</h1>
      <p style={{ color: 'var(--govt-gray-dark)' }}>Create a project record in PRISM. The backend assigns ownership from the authenticated principal unless an authorized delegation is supplied.</p>
      {error && <p role="alert" style={{ color: '#991b1b', background: '#fef2f2', padding: 12, borderRadius: 8 }}>{error}</p>}
      {created ? (
        <section style={{ background: '#fff', padding: 20, border: '1px solid var(--govt-gray-medium)', borderRadius: 10 }}>
          <h2>Project created</h2><p>{created.name}</p><code>{created.id}</code>
          <div style={{ display: 'flex', gap: 10, marginTop: 16 }}>
            <button type="button" onClick={() => navigate(`/projects/${created.id}`)}>Open project</button>
            <button type="button" onClick={() => { setCreated(null); setName(''); }}>Create another</button>
          </div>
        </section>
      ) : (
        <form onSubmit={submit} style={{ display: 'grid', gap: 12, padding: 20, background: '#fff', border: '1px solid var(--govt-gray-medium)', borderRadius: 10 }}>
          <label htmlFor="project-name">Project name</label>
          <input id="project-name" value={name} onChange={(event) => setName(event.target.value)} minLength={1} maxLength={256} required style={{ padding: 10, border: '1px solid var(--govt-gray-medium)', borderRadius: 6 }} />
          <button type="submit" disabled={busy || !name.trim()} style={{ justifySelf: 'start' }}>{busy ? 'Creating…' : 'Create project'}</button>
        </form>
      )}
    </main>
  );
}
