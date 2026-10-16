import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

function UploadEvidence() {
  const navigate = useNavigate();
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(false);
  const [projects, setProjects] = useState([]);
  const [activities, setActivities] = useState([]);
  const [formData, setFormData] = useState({
    project_id: '',
    activity_id: '',
    claim_id: '',
    file: null,
    filename: '',
    description: '',
    location: '',
    captured_at: new Date().toISOString().slice(0, 16),
  });

  // Mock projects for development
  useEffect(() => {
    setProjects([
      { id: 'PRJ-001', name: 'Rural Road Construction - Phase 1' },
      { id: 'PRJ-002', name: 'Solar Street Light Installation' },
      { id: 'PRJ-003', name: 'Water Tank Construction' },
      { id: 'PRJ-004', name: 'School Building Renovation' },
      { id: 'PRJ-005', name: 'Community Health Center' },
    ]);
  }, []);

  // Update activities when project changes
  useEffect(() => {
    if (formData.project_id) {
      setActivities([
        { id: 'ACT-001', name: 'Site Survey', stage: 'Initial' },
        { id: 'ACT-002', name: 'Foundation Work', stage: 'Construction' },
        { id: 'ACT-003', name: 'Base Layer', stage: 'Construction' },
        { id: 'ACT-004', name: 'Surface Work', stage: 'Construction' },
        { id: 'ACT-005', name: 'Final Inspection', stage: 'Completion' },
      ]);
    } else {
      setActivities([]);
    }
  }, [formData.project_id]);

  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (file) {
      if (file.size > 10 * 1024 * 1024) { // 10MB limit
        alert('File size exceeds 10MB limit');
        return;
      }
      if (!file.type.startsWith('image/')) {
        alert('Please select an image file (JPG, PNG, GIF)');
        return;
      }
      setFormData(prev => ({
        ...prev,
        file: file,
        filename: file.name
      }));
    }
  };

  const handleNext = () => {
    if (step === 1) {
      if (!formData.project_id) {
        alert('Please select a project');
        return;
      }
      setStep(2);
    } else if (step === 2) {
      if (!formData.file) {
        alert('Please select a file to upload');
        return;
      }
      setStep(3);
    } else if (step === 3) {
      setStep(4);
    }
  };

  const handleBack = () => {
    setStep(prev => Math.max(1, prev - 1));
  };

  const handleSubmit = async () => {
    setLoading(true);
    // Simulate API call
    setTimeout(() => {
      alert('Evidence uploaded successfully!');
      navigate('/evidence');
    }, 1500);
  };

  const formatFileSize = (bytes) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  return (
    <div style={{
      padding: '1.5rem',
      maxWidth: '900px',
      margin: '0 auto',
      backgroundColor: 'var(--govt-gray-off-white)',
      minHeight: 'calc(100vh - 60px)'
    }}>
      {/* Header */}
      <div style={{ marginBottom: '2rem' }}>
        <h2 style={{
          margin: 0,
          color: 'var(--govt-blue-primary)',
          fontSize: '1.75rem'
        }}>
          Upload Evidence
        </h2>
        <p style={{
          margin: '0.5rem 0 0 0',
          color: 'var(--govt-gray-dark)'
        }}>
          Submit photographic evidence for project monitoring
        </p>
      </div>

      {/* Progress Steps */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        marginBottom: '2rem'
      }}>
        {[1, 2, 3, 4].map((s) => (
          <div key={s} style={{ flex: 1, textAlign: 'center' }}>
            <div style={{
              width: '36px',
              height: '36px',
              margin: '0 auto 0.5rem auto',
              backgroundColor: step >= s ? 'var(--govt-blue-primary)' : 'var(--govt-gray-light)',
              color: step >= s ? '#ffffff' : 'var(--govt-gray-dark)',
              borderRadius: '50%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontWeight: '600',
              fontSize: '0.9rem'
            }}>
              {s}
            </div>
            <div style={{
              fontSize: '0.8rem',
              color: step >= s ? 'var(--govt-blue-primary)' : 'var(--govt-gray-dark)'
            }}>
              {s === 1 ? 'Project' : s === 2 ? 'File' : s === 3 ? 'Metadata' : 'Review'}
            </div>
          </div>
        ))}
      </div>

      {/* Progress Bar */}
      <div style={{
        height: '4px',
        backgroundColor: 'var(--govt-gray-light)',
        borderRadius: '2px',
        overflow: 'hidden',
        marginBottom: '2rem'
      }}>
        <div style={{
          width: `${(step / 4) * 100}%`,
          height: '100%',
          backgroundColor: 'var(--govt-blue-primary)',
          transition: 'width 0.3s ease'
        }} />
      </div>

      {/* Step Content */}
      <div style={{
        backgroundColor: 'var(--govt-white)',
        borderRadius: 'var(--radius-md)',
        boxShadow: 'var(--shadow-md)',
        padding: '2rem'
      }}>
        {step === 1 && (
          <div>
            <h3 style={{ color: 'var(--govt-blue-primary)', marginBottom: '1rem' }}>
              Step 1: Select Project & Activity
            </h3>
            <p style={{ color: 'var(--govt-gray-dark)', marginBottom: '1.5rem', fontSize: '0.9rem' }}>
              Choose the project and activity this evidence is associated with
            </p>

            <div style={{ marginBottom: '1.25rem' }}>
              <label style={{
                display: 'block',
                marginBottom: '0.5rem',
                fontWeight: '600',
                color: 'var(--govt-gray-text)'
              }}>
                Select Project <span style={{ color: 'var(--govt-danger)' }}>*</span>
              </label>
              <select
                style={{
                  width: '100%',
                  padding: '0.625rem',
                  border: '1px solid var(--govt-gray-medium)',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: '1rem'
                }}
                value={formData.project_id}
                onChange={(e) => setFormData(prev => ({ ...prev, project_id: e.target.value }))}
              >
                <option value="">Choose a project...</option>
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
            </div>

            <div style={{ marginBottom: '1.25rem' }}>
              <label style={{
                display: 'block',
                marginBottom: '0.5rem',
                fontWeight: '600',
                color: 'var(--govt-gray-text)'
              }}>
                Select Activity <span style={{ color: 'var(--govt-danger)' }}>*</span>
              </label>
              <select
                style={{
                  width: '100%',
                  padding: '0.625rem',
                  border: '1px solid var(--govt-gray-medium)',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: '1rem'
                }}
                value={formData.activity_id}
                onChange={(e) => setFormData(prev => ({ ...prev, activity_id: e.target.value }))}
              >
                <option value="">Choose an activity...</option>
                {activities.map((a) => (
                  <option key={a.id} value={a.id}>{a.name} - {a.stage}</option>
                ))}
              </select>
            </div>
          </div>
        )}

        {step === 2 && (
          <div>
            <h3 style={{ color: 'var(--govt-blue-primary)', marginBottom: '1rem' }}>
              Step 2: Upload File
            </h3>
            <p style={{ color: 'var(--govt-gray-dark)', marginBottom: '1.5rem', fontSize: '0.9rem' }}>
              Select the evidence file to upload (JPG, PNG, GIF - Max 10MB)
            </p>

            <div style={{
              border: '2px dashed var(--govt-gray-medium)',
              borderRadius: 'var(--radius-md)',
              padding: '3rem 2rem',
              textAlign: 'center',
              backgroundColor: 'var(--govt-gray-off-white)',
              transition: 'all 0.2s ease'
            }}>
              <input
                type="file"
                accept="image/*"
                onChange={handleFileChange}
                style={{ display: 'none' }}
                id="file-upload"
              />
              <label
                htmlFor="file-upload"
                style={{
                  cursor: 'pointer',
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  gap: '1rem'
                }}
                onMouseOver={(e) => e.currentTarget.style.borderColor = 'var(--govt-blue-primary)'}
                onMouseOut={(e) => e.currentTarget.style.borderColor = 'var(--govt-gray-medium)'}
              >
                <div style={{
                  width: '60px',
                  height: '60px',
                  backgroundColor: 'var(--govt-blue-light)',
                  borderRadius: '50%',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: 'var(--govt-blue-primary)'
                }}>
                  <svg width="32" height="32" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h4l2 2h7a2 2 0 0 1 2 2z" stroke="currentColor" strokeWidth="2"/>
                    <path d="M8 15a4 4 0 1 0 0-8 4 4 0 0 0 0 8z" stroke="currentColor" strokeWidth="2"/>
                  </svg>
                </div>
                <div>
                  <p style={{ margin: '0 0 0.5rem 0', fontSize: '1rem', color: 'var(--govt-blue-primary)' }}>
                    Click to select or drag and drop
                  </p>
                  <p style={{ margin: 0, fontSize: '0.8rem', color: 'var(--govt-gray-dark)' }}>
                    JPG, PNG, GIF (Max 10MB)
                  </p>
                </div>
              </label>

              {formData.file && (
                <div style={{
                  marginTop: '1rem',
                  padding: '1rem',
                  backgroundColor: 'var(--govt-blue-light)',
                  borderRadius: 'var(--radius-sm)',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '1rem'
                }}>
                  <div style={{
                    width: '40px',
                    height: '40px',
                    backgroundColor: '#ffffff',
                    borderRadius: 'var(--radius-sm)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center'
                  }}>
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                      <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" stroke="var(--govt-success)" strokeWidth="2"/>
                      <polyline points="9 22 9 12 15 12 15 22" stroke="var(--govt-success)" strokeWidth="2"/>
                    </svg>
                  </div>
                  <div style={{ flex: 1 }}>
                    <p style={{ margin: 0, fontSize: '0.9rem', fontWeight: '500', color: 'var(--govt-blue-primary)' }}>
                      {formData.filename}
                    </p>
                    <p style={{ margin: 0, fontSize: '0.8rem', color: 'var(--govt-gray-text)' }}>
                      {formatFileSize(formData.file.size)}
                    </p>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {step === 3 && (
          <div>
            <h3 style={{ color: 'var(--govt-blue-primary)', marginBottom: '1rem' }}>
              Step 3: Add Metadata
            </h3>
            <p style={{ color: 'var(--govt-gray-dark)', marginBottom: '1.5rem', fontSize: '0.9rem' }}>
              Enter additional details about this evidence
            </p>

            <div style={{ marginBottom: '1.25rem' }}>
              <label style={{
                display: 'block',
                marginBottom: '0.5rem',
                fontWeight: '600',
                color: 'var(--govt-gray-text)'
              }}>
                Capture Timestamp
              </label>
              <input
                type="datetime-local"
                value={formData.captured_at}
                onChange={(e) => setFormData(prev => ({ ...prev, captured_at: e.target.value }))}
                style={{
                  width: '100%',
                  padding: '0.625rem',
                  border: '1px solid var(--govt-gray-medium)',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: '1rem'
                }}
              />
            </div>

            <div style={{ marginBottom: '1.25rem' }}>
              <label style={{
                display: 'block',
                marginBottom: '0.5rem',
                fontWeight: '600',
                color: 'var(--govt-gray-text)'
              }}>
                Location (Optional)
              </label>
              <input
                type="text"
                placeholder="Enter location (e.g., Village Name, GPS coordinates)"
                value={formData.location}
                onChange={(e) => setFormData(prev => ({ ...prev, location: e.target.value }))}
                style={{
                  width: '100%',
                  padding: '0.625rem',
                  border: '1px solid var(--govt-gray-medium)',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: '1rem'
                }}
              />
            </div>

            <div style={{ marginBottom: '1.25rem' }}>
              <label style={{
                display: 'block',
                marginBottom: '0.5rem',
                fontWeight: '600',
                color: 'var(--govt-gray-text)'
              }}>
                Description (Optional)
              </label>
              <textarea
                placeholder="Describe what this evidence shows..."
                value={formData.description}
                onChange={(e) => setFormData(prev => ({ ...prev, description: e.target.value }))}
                style={{
                  width: '100%',
                  padding: '0.625rem',
                  border: '1px solid var(--govt-gray-medium)',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: '1rem',
                  minHeight: '100px',
                  resize: 'vertical'
                }}
              />
            </div>
          </div>
        )}

        {step === 4 && (
          <div>
            <h3 style={{ color: 'var(--govt-blue-primary)', marginBottom: '1rem' }}>
              Step 4: Review & Submit
            </h3>
            <p style={{ color: 'var(--govt-gray-dark)', marginBottom: '1.5rem', fontSize: '0.9rem' }}>
              Please review your evidence submission before sending
            </p>

            <div style={{
              backgroundColor: 'var(--govt-gray-off-white)',
              borderRadius: 'var(--radius-sm)',
              padding: '1.5rem',
              marginBottom: '1.5rem'
            }}>
              <div style={{ marginBottom: '1rem' }}>
                <strong style={{ color: 'var(--govt-gray-text)' }}>Project:</strong>{' '}
                {projects.find(p => p.id === formData.project_id)?.name || '-'}
              </div>
              <div style={{ marginBottom: '1rem' }}>
                <strong style={{ color: 'var(--govt-gray-text)' }}>Activity:</strong>{' '}
                {activities.find(a => a.id === formData.activity_id)?.name || '-'}
              </div>
              <div style={{ marginBottom: '1rem' }}>
                <strong style={{ color: 'var(--govt-gray-text)' }}>File:</strong>{' '}
                {formData.filename} ({formatFileSize(formData.file?.size || 0)})
              </div>
              {formData.location && (
                <div style={{ marginBottom: '1rem' }}>
                  <strong style={{ color: 'var(--govt-gray-text)' }}>Location:</strong>{' '}
                  {formData.location}
                </div>
              )}
              {formData.description && (
                <div>
                  <strong style={{ color: 'var(--govt-gray-text)' }}>Description:</strong>{' '}
                  {formData.description}
                </div>
              )}
            </div>

            <div style={{
              backgroundColor: 'var(--govt-blue-light)',
              border: '1px solid var(--govt-blue-primary)',
              borderRadius: 'var(--radius-sm)',
              padding: '1rem',
              marginBottom: '1.5rem'
            }}>
              <p style={{ margin: 0, fontSize: '0.9rem', color: 'var(--govt-gray-text)' }}>
                <strong>Note:</strong> By submitting this evidence, you confirm that it is accurate and was captured in the context of the selected project.
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Action Buttons */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        marginTop: '1.5rem'
      }}>
        <button
          onClick={handleBack}
          disabled={step === 1}
          style={{
            padding: '0.75rem 1.5rem',
            backgroundColor: step === 1 ? 'var(--govt-gray-light)' : 'var(--govt-gray-light)',
            border: '1px solid var(--govt-gray-medium)',
            borderRadius: 'var(--radius-sm)',
            fontSize: '1rem',
            cursor: step === 1 ? 'not-allowed' : 'pointer',
            color: step === 1 ? 'var(--govt-gray-dark)' : 'var(--govt-gray-text)'
          }}
        >
          Back
        </button>
        {step < 4 ? (
          <button
            onClick={handleNext}
            style={{
              padding: '0.75rem 1.5rem',
              backgroundColor: 'var(--govt-blue-primary)',
              color: '#ffffff',
              border: 'none',
              borderRadius: 'var(--radius-sm)',
              fontSize: '1rem',
              fontWeight: '600',
              cursor: 'pointer'
            }}
          >
            Next
          </button>
        ) : (
          <button
            onClick={handleSubmit}
            disabled={loading}
            style={{
              padding: '0.75rem 1.5rem',
              backgroundColor: 'var(--govt-success)',
              color: '#ffffff',
              border: 'none',
              borderRadius: 'var(--radius-sm)',
              fontSize: '1rem',
              fontWeight: '600',
              cursor: 'pointer'
            }}
          >
            {loading ? 'Submitting...' : 'Submit Evidence'}
          </button>
        )}
      </div>
    </div>
  );
}

export default UploadEvidence;
