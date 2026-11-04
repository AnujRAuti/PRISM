import { useState, useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { EvidenceIcon, CheckIcon, AlertIcon } from '../../components/common/Icon';
import { evidenceApi, projectApi } from '../../services/api';

function UploadEvidence() {
  const navigate = useNavigate();
  const location = useLocation();
  const initialProjectId = new URLSearchParams(location.search).get('project_id') || '';

  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [error, setError] = useState(null);
  const [uploadSuccess, setUploadSuccess] = useState(null);
  const [projects, setProjects] = useState([]);

  const [formData, setFormData] = useState({
    project_id: initialProjectId,
    claim_id: '',
    file: null,
    filename: '',
    fileSize: 0,
    previewUrl: null,
    description: '',
    gps_lat: '',
    gps_lng: '',
  });

  useEffect(() => {
    let active = true;
    projectApi.getAll({ limit: 100 }).then(({ data }) => {
      if (active) setProjects(data.items || []);
    }).catch((cause) => {
      if (active) setError(cause.response?.data?.detail || cause.message || 'Could not load project options.');
    });
    return () => { active = false; };
  }, []);

  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (file) {
      // 10 MiB constraint per Section 9.4 & ADR §19.2
      if (file.size > 10 * 1024 * 1024) {
        setError('File exceeds maximum allowable upload size of 10 MiB (Section 9.4).');
        return;
      }
      const validTypes = ['image/jpeg', 'image/png', 'image/webp'];
      if (!validTypes.includes(file.type)) {
        setError('Unsupported media type. Approved formats are JPEG, PNG, and WebP.');
        return;
      }
      setError(null);
      const preview = URL.createObjectURL(file);
      setFormData(prev => ({
        ...prev,
        file,
        filename: file.name,
        fileSize: file.size,
        previewUrl: preview,
      }));
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!formData.file) {
      setError('Please select an evidence image file.');
      return;
    }
    setLoading(true);
    setError(null);

    try {
      if (Boolean(formData.gps_lat) !== Boolean(formData.gps_lng)) throw new Error('Enter both coordinates or leave both blank.');
      const { data: uploaded } = await evidenceApi.upload(formData.file, null, (event) => {
        if (event.total) setUploadProgress(Math.round((event.loaded / event.total) * 100));
      });
      setUploadSuccess({ id: uploaded.evidence_id, status: uploaded.status, content_type: uploaded.content_type, size: uploaded.size });
      if (formData.project_id) {
        await evidenceApi.updateContext(uploaded.evidence_id, { project_id: formData.project_id, claim_id: formData.claim_id || null });
      }
      if (formData.gps_lat && formData.gps_lng) {
        await evidenceApi.updateLocation(uploaded.evidence_id, { latitude: Number(formData.gps_lat), longitude: Number(formData.gps_lng) });
      }
    } catch (cause) {
      setError(cause.response?.data?.detail || cause.message || 'Evidence upload failed.');
    } finally {
      setLoading(false);
    }
  };

  const formatBytes = (bytes) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  return (
    <div style={{
      padding: '1.75rem 2rem',
      width: '100%',
      boxSizing: 'border-box',
      backgroundColor: 'var(--govt-gray-off-white)',
    }}>
      {/* Header */}
      <div style={{ marginBottom: '1.75rem' }}>
        <h1 style={{
          margin: 0,
          color: 'var(--govt-blue-dark)',
          fontSize: '1.65rem',
          fontWeight: 700,
          letterSpacing: '-0.02em'
        }}>
          Upload evidence to PRISM
        </h1>
        <p style={{
          margin: '0.35rem 0 0 0',
          color: 'var(--govt-gray-dark)',
          fontSize: '0.875rem'
        }}>
          Upload an image to the backend quarantine pipeline. Project context and coordinates are sent through their dedicated API operations when supplied.
        </p>
      </div>

      {uploadSuccess ? (
        /* Success State */
        <div style={{
          backgroundColor: 'var(--govt-white)',
          borderRadius: 'var(--radius-lg)',
          boxShadow: 'var(--shadow-sm)',
          border: '1px solid var(--govt-success-border)',
          padding: '2rem',
          maxWidth: '680px',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1rem' }}>
            <span style={{
              width: '36px',
              height: '36px',
              borderRadius: '50%',
              backgroundColor: 'var(--govt-success-light)',
              color: 'var(--govt-success-text)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontWeight: 700
            }}>✓</span>
            <div>
              <h3 style={{ margin: 0, color: 'var(--govt-success-text)', fontSize: '1.15rem', fontWeight: 700 }}>
                Evidence Received into Quarantine
              </h3>
              <p style={{ margin: '0.2rem 0 0', fontSize: '0.8rem', color: 'var(--govt-gray-dark)' }}>
                Assigned Evidence Identifier: <strong>{uploadSuccess.id}</strong>
              </p>
            </div>
          </div>

          <div style={{
            backgroundColor: 'var(--govt-gray-off-white)',
            border: '1px solid var(--govt-gray-medium)',
            borderRadius: 'var(--radius-md)',
            padding: '1rem',
            marginBottom: '1.5rem',
            fontSize: '0.8rem',
            display: 'flex',
            flexDirection: 'column',
            gap: '0.5rem'
          }}>
            <div><span style={{ color: 'var(--govt-gray-dark)' }}>Backend status:</span> <strong>{uploadSuccess.status}</strong></div>
            <div><span style={{ color: 'var(--govt-gray-dark)' }}>Media type and size:</span> <strong>{uploadSuccess.content_type} · {formatBytes(uploadSuccess.size)}</strong></div>
            <div><span style={{ color: 'var(--govt-gray-dark)' }}>Project context:</span> <strong>{formData.project_id || 'Not linked'}</strong></div>
          </div>

          <div style={{ display: 'flex', gap: '0.75rem' }}>
            <button
              type="button"
              onClick={() => navigate(`/evidence/${uploadSuccess.id}`)}
              style={{
                padding: '0.625rem 1.25rem',
                backgroundColor: 'var(--govt-blue-primary)',
                color: '#ffffff',
                border: 'none',
                borderRadius: 'var(--radius-md)',
                fontSize: '0.875rem',
                fontWeight: 600,
                cursor: 'pointer'
              }}
            >
              Open Evidence Record →
            </button>
            <button
              type="button"
              onClick={() => { setUploadSuccess(null); setFormData(p => ({ ...p, file: null, previewUrl: null })); }}
              style={{
                padding: '0.625rem 1.25rem',
                backgroundColor: 'var(--govt-white)',
                color: 'var(--govt-gray-text)',
                border: '1px solid var(--govt-gray-medium)',
                borderRadius: 'var(--radius-md)',
                fontSize: '0.875rem',
                fontWeight: 600,
                cursor: 'pointer'
              }}
            >
              Upload Another Item
            </button>
          </div>
        </div>
      ) : (
        /* Form State */
        <div style={{
          backgroundColor: 'var(--govt-white)',
          borderRadius: 'var(--radius-lg)',
          boxShadow: 'var(--shadow-sm)',
          border: '1px solid var(--govt-gray-medium)',
          padding: '1.75rem 2rem',
          maxWidth: '780px',
        }}>
          {error && (
            <div style={{
              backgroundColor: 'var(--govt-danger-light)',
              border: '1px solid var(--govt-danger-border)',
              color: 'var(--govt-danger-text)',
              padding: '0.75rem 1rem',
              borderRadius: 'var(--radius-md)',
              marginBottom: '1.25rem',
              fontSize: '0.85rem'
            }}>
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
            {/* Project association */}
            <div>
              <label htmlFor="project_id" style={{ display: 'block', fontSize: '0.82rem', fontWeight: 700, color: 'var(--govt-blue-dark)', marginBottom: '0.4rem' }}>
                Project Context (optional)
              </label>
              <select
                id="project_id"
                value={formData.project_id}
                onChange={(e) => setFormData(p => ({ ...p, project_id: e.target.value }))}
                style={{
                  width: '100%',
                  padding: '0.625rem 0.85rem',
                  borderRadius: 'var(--radius-md)',
                  border: '1px solid var(--govt-gray-medium)',
                  fontSize: '0.875rem',
                  backgroundColor: 'var(--govt-white)'
                }}
              >
                <option value="">No project association</option>{projects.map((project) => (
                  <option key={project.id} value={project.id}>{project.name}</option>
                ))}
              </select>
              <span style={{ fontSize: '0.72rem', color: 'var(--govt-gray-dark)', marginTop: '0.3rem', display: 'block' }}>
                The selected project and optional claim are sent to the backend after upload. Access is checked by backend permissions.
              </span>
            </div>

            {/* File Upload Area */}
            <div>
              <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 700, color: 'var(--govt-blue-dark)', marginBottom: '0.4rem' }}>
                Evidence Image File (Max 10 MiB) <span style={{ color: 'var(--govt-danger)' }}>*</span>
              </label>
              <div
                style={{
                  border: '2px dashed var(--govt-gray-medium)',
                  borderRadius: 'var(--radius-lg)',
                  padding: '1.75rem',
                  textAlign: 'center',
                  backgroundColor: 'var(--govt-gray-off-white)',
                  cursor: 'pointer'
                }}
                onClick={() => document.getElementById('evidence-file-input').click()}
              >
                <input
                  id="evidence-file-input"
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  onChange={handleFileChange}
                  style={{ display: 'none' }}
                />
                {formData.previewUrl ? (
                  <div>
                    <img
                      src={formData.previewUrl}
                      alt="Preview"
                      style={{ maxHeight: '140px', borderRadius: 'var(--radius-md)', marginBottom: '0.75rem' }}
                    />
                    <p style={{ margin: 0, fontSize: '0.85rem', fontWeight: 600, color: 'var(--govt-blue-dark)' }}>
                      {formData.filename} ({formatBytes(formData.fileSize)})
                    </p>
                    <span style={{ fontSize: '0.75rem', color: 'var(--govt-blue-primary)' }}>Click to replace file</span>
                  </div>
                ) : (
                  <div>
                    <span style={{ fontSize: '1.75rem', color: 'var(--govt-blue-primary)' }}>📷</span>
                    <p style={{ margin: '0.5rem 0 0', fontSize: '0.875rem', fontWeight: 600, color: 'var(--govt-blue-dark)' }}>
                      Click to browse or drop an inspection photo here
                    </p>
                    <p style={{ margin: '0.25rem 0 0', fontSize: '0.75rem', color: 'var(--govt-gray-dark)' }}>
                      Accepted formats: JPEG, PNG, WebP (Strict 10 MiB limit)
                    </p>
                  </div>
                )}
              </div>
            </div>

            {/* Geographic Coordinates */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
              <div>
                <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 700, color: 'var(--govt-blue-dark)', marginBottom: '0.4rem' }}>
                  Latitude (°N)
                </label>
                <input
                  type="text"
                  value={formData.gps_lat}
                  onChange={(e) => setFormData(p => ({ ...p, gps_lat: e.target.value }))}
                  style={{
                    width: '100%',
                    padding: '0.625rem 0.85rem',
                    borderRadius: 'var(--radius-md)',
                    border: '1px solid var(--govt-gray-medium)',
                    fontSize: '0.875rem',
                    boxSizing: 'border-box'
                  }}
                />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 700, color: 'var(--govt-blue-dark)', marginBottom: '0.4rem' }}>
                  Longitude (°E)
                </label>
                <input
                  type="text"
                  value={formData.gps_lng}
                  onChange={(e) => setFormData(p => ({ ...p, gps_lng: e.target.value }))}
                  style={{
                    width: '100%',
                    padding: '0.625rem 0.85rem',
                    borderRadius: 'var(--radius-md)',
                    border: '1px solid var(--govt-gray-medium)',
                    fontSize: '0.875rem',
                    boxSizing: 'border-box'
                  }}
                />
              </div>
            </div>

            {/* Quarantine Notice */}
            <div style={{
              padding: '0.75rem 1rem',
              backgroundColor: 'var(--govt-warning-light)',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--govt-warning-border)',
              display: 'flex',
              gap: '0.6rem',
              fontSize: '0.78rem',
              color: 'var(--govt-warning-text)'
            }}>
              <span>ℹ</span>
              <div>
                <strong>Quarantine Isolation Policy:</strong> The backend stores the original in quarantine and starts server-side integrity processing. Upload acknowledgement does not imply that analysis has completed.
              </div>
            </div>

            {/* Submit Button */}
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '0.5rem' }}>
              <button
                type="button"
                onClick={() => navigate(-1)}
                style={{
                  padding: '0.625rem 1.25rem',
                  backgroundColor: 'var(--govt-white)',
                  color: 'var(--govt-gray-text)',
                  border: '1px solid var(--govt-gray-medium)',
                  borderRadius: 'var(--radius-md)',
                  fontSize: '0.875rem',
                  fontWeight: 600,
                  cursor: 'pointer'
                }}
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={loading || !formData.file}
                style={{
                  padding: '0.625rem 1.5rem',
                  backgroundColor: loading || !formData.file ? 'var(--govt-gray-medium)' : 'var(--govt-blue-primary)',
                  color: '#ffffff',
                  border: 'none',
                  borderRadius: 'var(--radius-md)',
                  fontSize: '0.875rem',
                  fontWeight: 600,
                  cursor: loading || !formData.file ? 'not-allowed' : 'pointer'
                }}
              >
                {loading ? `Uploading (${uploadProgress}%)...` : 'Submit to Quarantine'}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}

export default UploadEvidence;
