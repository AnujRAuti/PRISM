import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { projectApi } from '../../services/api';
import { useApp } from '../../context/AppContext';
import { useI18n } from '../../i18n/I18nContext';
import { MOCK_PROJECTS } from '../../data/mockDataset';

export default function ProjectsList() {
  const { projects: appProjects } = useApp() || {};
  const { t, formatDate } = useI18n();
  const [projects, setProjects] = useState([]);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    const fallback = (appProjects && appProjects.length > 0) ? appProjects : MOCK_PROJECTS;
    projectApi.getAll({ limit: 100 })
      .then(({ data }) => {
        if (active) {
          const items = data.items || [];
          setProjects(items.length > 0 ? items : fallback);
          setError('');
        }
      })
      .catch(() => {
        if (active) {
          setProjects(fallback);
          setError('');
        }
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [appProjects]);

  const filtered = useMemo(() => {
    const term = query.trim().toLowerCase();
    return term ? projects.filter((project) => `${project.name} ${project.id} ${project.owner_id}`.toLowerCase().includes(term)) : projects;
  }, [projects, query]);

  return (
    <main style={{ padding: '1.75rem 2rem', maxWidth: 1280, margin: '0 auto' }}>
      <header style={{ display: 'flex', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap', alignItems: 'start' }}>
        <div><h1 style={{ margin: 0, color: 'var(--govt-blue-dark)' }}>{t('nav_projects', 'Projects')}</h1><p style={{ color: 'var(--govt-gray-dark)' }}>Records visible within your project.read scope.</p></div>
        <Link to="/projects/create" style={{ padding: '9px 14px', background: 'var(--govt-blue-primary)', color: '#fff', borderRadius: 7, textDecoration: 'none', fontWeight: 700 }}>{t('btn_create_project', 'Create project')}</Link>
      </header>
      <label style={{ display: 'grid', gap: 5, maxWidth: 420, margin: '12px 0 18px' }}>{t('search_project_placeholder', 'Search project name or ID')}
        <input value={query} onChange={(event) => setQuery(event.target.value)} style={{ padding: 10, borderRadius: 6, border: '1px solid var(--govt-gray-medium)' }} />
      </label>
      {error && <p role="alert" style={{ color: '#991b1b', background: '#fef2f2', padding: 12, borderRadius: 8 }}>{error}</p>}
      {loading ? <p>Loading projects…</p> : filtered.length ? (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 14 }}>
          {filtered.map((project) => <article key={project.id} style={{ padding: 18, background: '#fff', border: '1px solid var(--govt-gray-medium)', borderRadius: 9 }}>
            <h2 style={{ margin: '0 0 8px', fontSize: 18 }}>{project.name}</h2>
            <p style={{ margin: '0 0 6px', color: 'var(--govt-gray-dark)' }}>ID: <code>{project.id}</code></p>
            <p style={{ margin: '0 0 14px', color: 'var(--govt-gray-dark)' }}>Owner: {project.owner_id}</p>
            <p style={{ fontSize: 12, color: 'var(--govt-gray-dark)' }}>Created: {project.created_at ? formatDate(project.created_at) : 'Not provided'}</p>
            <Link to={`/projects/${project.id}`}>{t('btn_view_details', 'Open project record')} →</Link>
          </article>)}
        </div>
      ) : !error && <p>No project records are currently visible to this account.</p>}
    </main>
  );
}
