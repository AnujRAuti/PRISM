import { useMemo, useState } from 'react';
import backendOpenApi from '../../data/backend-openapi.json';
import api, { operationsApi } from '../../services/api';

const methods = ['get', 'post', 'put', 'patch', 'delete', 'options', 'head'];
const labelStyle = { display: 'grid', gap: 5, fontSize: 13, color: 'var(--govt-gray-dark)' };
const inputStyle = { width: '100%', padding: '9px 10px', border: '1px solid var(--govt-gray-medium)', borderRadius: 6, font: 'inherit', boxSizing: 'border-box' };

function resolveSchema(schema, depth = 0) {
  if (!schema || depth > 3) return {};
  if (schema.$ref) {
    const key = schema.$ref.split('/').at(-1);
    return resolveSchema(backendOpenApi.components?.schemas?.[key], depth + 1);
  }
  if (schema.allOf) return Object.assign({}, ...schema.allOf.map((part) => resolveSchema(part, depth + 1)));
  return schema;
}

function sampleValue(schema, depth = 0) {
  const resolved = resolveSchema(schema, depth);
  if (resolved.enum?.length) return resolved.enum[0];
  if (resolved.default !== undefined) return resolved.default;
  if (resolved.type === 'object' || resolved.properties) {
    const required = new Set(resolved.required || []);
    return Object.fromEntries(Object.entries(resolved.properties || {})
      .filter(([key]) => required.has(key))
      .map(([key, child]) => [key, sampleValue(child, depth + 1)]));
  }
  if (resolved.type === 'array') return [];
  if (resolved.type === 'integer' || resolved.type === 'number') return resolved.minimum ?? 0;
  if (resolved.type === 'boolean') return false;
  if (resolved.format === 'uuid') return '00000000-0000-4000-8000-000000000001';
  if (resolved.format === 'date-time') return new Date().toISOString();
  if (resolved.format === 'binary') return undefined;
  return resolved.minLength ? 'example' : '';
}

const operations = Object.entries(backendOpenApi.paths).flatMap(([path, pathItem]) =>
  methods.filter((method) => pathItem[method]).map((method) => ({
    path,
    method,
    operation: pathItem[method],
    parameters: [...(pathItem.parameters || []), ...(pathItem[method].parameters || [])],
  })),
);

export default function BackendApiWorkbench() {
  const [search, setSearch] = useState('');
  const [selectedKey, setSelectedKey] = useState(`${operations[0]?.method}:${operations[0]?.path}`);
  const [pathValues, setPathValues] = useState({});
  const [queryValues, setQueryValues] = useState({});
  const [bodyText, setBodyText] = useState('');
  const [files, setFiles] = useState({});
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase();
    if (!needle) return operations;
    return operations.filter(({ path, method, operation }) =>
      `${method} ${path} ${operation.summary || ''} ${(operation.tags || []).join(' ')}`.toLowerCase().includes(needle));
  }, [search]);

  const selected = operations.find(({ method, path }) => `${method}:${path}` === selectedKey) || filtered[0];
  const requestContent = selected?.operation.requestBody?.content || {};
  const mediaType = Object.keys(requestContent)[0] || 'application/json';
  const bodySchema = requestContent[mediaType]?.schema;
  const resolvedBodySchema = resolveSchema(bodySchema);
  const bodyProperties = Object.entries(resolvedBodySchema.properties || {});
  const multipart = mediaType.includes('multipart/form-data');

  const chooseOperation = (event) => {
    const next = operations.find(({ method, path }) => `${method}:${path}` === event.target.value);
    setSelectedKey(event.target.value);
    setPathValues({});
    setQueryValues({});
    setFiles({});
    setBodyText(next?.operation.requestBody ? JSON.stringify(sampleValue(Object.values(next.operation.requestBody.content || {})[0]?.schema), null, 2) : '');
    setResult(null);
    setError('');
  };

  const execute = async (event) => {
    event.preventDefault();
    if (!selected) return;
    setBusy(true);
    setError('');
    setResult(null);
    try {
      let path = selected.path;
      for (const match of path.matchAll(/\{([^}]+)\}/g)) {
        const value = pathValues[match[1]]?.trim();
        if (!value) throw new Error(`Enter the path value for ${match[1]}.`);
        path = path.replace(`{${match[1]}}`, encodeURIComponent(value));
      }
      const params = Object.fromEntries(Object.entries(queryValues).filter(([, value]) => value !== ''));
      let data;
      if (selected.operation.requestBody) {
        if (multipart) {
          data = new FormData();
          for (const [key, schema] of bodyProperties) {
            const value = files[key];
            if (value) data.append(key, value);
            else if (resolvedBodySchema.required?.includes(key)) {
              throw new Error(`Choose a file for required field ${key}.`);
            }
          }
        } else if (mediaType.includes('application/json') || mediaType.endsWith('+json')) {
          data = JSON.parse(bodyText || '{}');
        } else {
          data = bodyText;
        }
      }
      const cleanPath = path.replace(/^\/api\/v1/, '') || '/';
      const client = path.startsWith('/api/v1/') ? api : operationsApi;
      const response = await client.request({ method: selected.method, url: cleanPath, params, data });
      setResult({ status: response.status, data: response.data, headers: response.headers });
    } catch (requestError) {
      const status = requestError.response?.status;
      const data = requestError.response?.data;
      setError([status ? `HTTP ${status}` : '', data ? JSON.stringify(data, null, 2) : requestError.message].filter(Boolean).join('\n'));
    } finally {
      setBusy(false);
    }
  };

  if (!selected) return null;

  return (
    <section style={{ display: 'grid', gridTemplateColumns: 'minmax(260px, 0.8fr) minmax(0, 2fr)', gap: 18, alignItems: 'start' }}>
      <aside style={{ background: 'var(--govt-white)', border: '1px solid var(--govt-gray-medium)', borderRadius: 10, padding: 16 }}>
        <h2 style={{ margin: '0 0 12px', fontSize: 16, color: 'var(--govt-blue-dark)' }}>Backend capabilities</h2>
        <p style={{ margin: '0 0 12px', fontSize: 12, lineHeight: 1.5, color: 'var(--govt-gray-dark)' }}>
          Execute the published API contract. Server permissions remain authoritative; a 401 or 403 means the signed-in account lacks valid credentials or scope.
        </p>
        <input aria-label="Search backend operations" placeholder="Search operations" value={search} onChange={(event) => setSearch(event.target.value)} style={{ ...inputStyle, marginBottom: 10 }} />
        <select aria-label="Backend operation" size="18" value={selectedKey} onChange={chooseOperation} style={{ ...inputStyle, height: 380 }}>
          {filtered.map(({ path, method, operation }) => (
            <option key={`${method}:${path}`} value={`${method}:${path}`}>{method.toUpperCase()} · {operation.summary || path}</option>
          ))}
        </select>
        <p style={{ fontSize: 11, color: 'var(--govt-gray-dark)' }}>{filtered.length} of {operations.length} operations</p>
      </aside>

      <div style={{ background: 'var(--govt-white)', border: '1px solid var(--govt-gray-medium)', borderRadius: 10, padding: 18, minWidth: 0 }}>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'baseline' }}>
          <strong style={{ color: 'var(--govt-blue-primary)' }}>{selected.method.toUpperCase()}</strong>
          <code style={{ overflowWrap: 'anywhere' }}>{selected.path}</code>
        </div>
        <p style={{ color: 'var(--govt-gray-dark)', lineHeight: 1.5 }}>{selected.operation.description || selected.operation.summary}</p>
        <form onSubmit={execute} style={{ display: 'grid', gap: 14 }}>
          {selected.parameters.filter((parameter) => parameter.in === 'path').map((parameter) => (
            <label key={`${parameter.in}:${parameter.name}`} style={labelStyle}>{parameter.name} (path){parameter.required ? ' *' : ''}
              <input required={parameter.required} value={pathValues[parameter.name] || ''} onChange={(event) => setPathValues({ ...pathValues, [parameter.name]: event.target.value })} style={inputStyle} />
            </label>
          ))}
          {selected.parameters.filter((parameter) => parameter.in === 'query').map((parameter) => (
            <label key={`${parameter.in}:${parameter.name}`} style={labelStyle}>{parameter.name} (query){parameter.required ? ' *' : ''}
              <input required={parameter.required} type={['integer', 'number'].includes(parameter.schema?.type) ? 'number' : 'text'} value={queryValues[parameter.name] || ''} onChange={(event) => setQueryValues({ ...queryValues, [parameter.name]: event.target.value })} style={inputStyle} />
            </label>
          ))}
          {selected.operation.requestBody && (multipart ? (
            <div style={{ display: 'grid', gap: 10 }}>
              <h3 style={{ margin: 0, fontSize: 14 }}>Upload fields</h3>
              {bodyProperties.map(([key, schema]) => (
                <label key={key} style={labelStyle}>{key}{resolvedBodySchema.required?.includes(key) ? ' *' : ''}
                  {resolveSchema(schema).format === 'binary'
                    ? <input required={resolvedBodySchema.required?.includes(key)} type="file" onChange={(event) => setFiles({ ...files, [key]: event.target.files?.[0] || null })} />
                    : <input value={files[key] || ''} onChange={(event) => setFiles({ ...files, [key]: event.target.value })} style={inputStyle} />}
                </label>
              ))}
            </div>
          ) : (
            <label style={labelStyle}>Request body ({mediaType})
              <textarea rows={12} spellCheck="false" value={bodyText} onChange={(event) => setBodyText(event.target.value)} style={{ ...inputStyle, fontFamily: 'monospace', resize: 'vertical' }} />
            </label>
          ))}
          <button type="submit" disabled={busy} style={{ justifySelf: 'start', border: 0, borderRadius: 6, padding: '10px 16px', background: busy ? '#64748b' : 'var(--govt-blue-primary)', color: '#fff', fontWeight: 700, cursor: busy ? 'wait' : 'pointer' }}>
            {busy ? 'Sending…' : `Run ${selected.method.toUpperCase()} operation`}
          </button>
        </form>
        {error && <pre role="alert" style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', color: '#991b1b', background: '#fef2f2', padding: 12, borderRadius: 8, marginTop: 16 }}>{error}</pre>}
        {result && <div style={{ marginTop: 18 }}><strong>HTTP {result.status}</strong><pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', maxHeight: 520, overflow: 'auto', color: '#0f172a', background: '#f8fafc', padding: 12, borderRadius: 8 }}>{JSON.stringify(result.data, null, 2)}</pre></div>}
      </div>
    </section>
  );
}
