import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { projectApi } from '../../services/api';
import { getIndianStates } from '../../utils/helpers';

function CreateProject() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [formData, setFormData] = useState({
    name: '',
    scheme: '',
    description: '',
    location: '',
    state: '',
    district: '',
    start_date: '',
    end_date: '',
    geofence: '',
  });

  const schemes = [
    'Pradhan Mantri Gram Sadak Yojana',
    'Jal Jeevan Mission',
    'Solar Energy Programme',
    'Samagra Shiksha Abhiyan',
    'National Health Mission',
    'Mahatma Gandhi National Rural Employment Guarantee Act',
    'Swachh Bharat Mission',
    'Pradhan Mantri Awas Yojana',
    'Smart Cities Mission',
    'AMRUT Mission',
  ];

  const states = getIndianStates();

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: value
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      // Will be replaced with actual API call
      // const response = await projectApi.create(formData);
      // navigate(`/projects/${response.data.id}`);

      // Simulating API call
      setTimeout(() => {
        alert('Project created successfully!');
        navigate('/projects');
      }, 1000);
    } catch (err) {
      setError(err.response?.data?.message || 'Failed to create project');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-4">
      {/* Header */}
      <div className="row mb-4">
        <div className="col">
          <h2 className="mb-1">Create New Project</h2>
          <p className="text-muted mb-0">Add a new government project to the system</p>
        </div>
      </div>

      {/* Form */}
      <div className="card">
        <div className="card-header bg-blue-dark text-white">
          <h4 className="mb-0">Project Information</h4>
        </div>
        <div className="card-body">
          {error && (
            <div className="alert alert-danger" role="alert">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit}>
            <div className="row g-3">
              {/* Project Name */}
              <div className="col-md-8">
                <label htmlFor="name" className="form-label">
                  Project Name <span className="text-danger">*</span>
                </label>
                <input
                  type="text"
                  className="form-control"
                  id="name"
                  name="name"
                  value={formData.name}
                  onChange={handleChange}
                  required
                  placeholder="Enter project name"
                />
              </div>

              {/* Scheme */}
              <div className="col-md-4">
                <label htmlFor="scheme" className="form-label">
                  Government Scheme <span className="text-danger">*</span>
                </label>
                <select
                  className="form-control"
                  id="scheme"
                  name="scheme"
                  value={formData.scheme}
                  onChange={handleChange}
                  required
                >
                  <option value="">Select Scheme</option>
                  {schemes.map((scheme, index) => (
                    <option key={index} value={scheme}>{scheme}</option>
                  ))}
                </select>
              </div>

              {/* Description */}
              <div className="col-12">
                <label htmlFor="description" className="form-label">
                  Description
                </label>
                <textarea
                  className="form-control"
                  id="description"
                  name="description"
                  value={formData.description}
                  onChange={handleChange}
                  rows="3"
                  placeholder="Enter project description"
                />
              </div>

              {/* State */}
              <div className="col-md-4">
                <label htmlFor="state" className="form-label">
                  State <span className="text-danger">*</span>
                </label>
                <select
                  className="form-control"
                  id="state"
                  name="state"
                  value={formData.state}
                  onChange={handleChange}
                  required
                >
                  <option value="">Select State</option>
                  {states.map((state, index) => (
                    <option key={index} value={state}>{state}</option>
                  ))}
                </select>
              </div>

              {/* District */}
              <div className="col-md-4">
                <label htmlFor="district" className="form-label">
                  District
                </label>
                <input
                  type="text"
                  className="form-control"
                  id="district"
                  name="district"
                  value={formData.district}
                  onChange={handleChange}
                  placeholder="Enter district"
                />
              </div>

              {/* Location */}
              <div className="col-md-4">
                <label htmlFor="location" className="form-label">
                  Location/Village
                </label>
                <input
                  type="text"
                  className="form-control"
                  id="location"
                  name="location"
                  value={formData.location}
                  onChange={handleChange}
                  placeholder="Enter location"
                />
              </div>

              {/* Start Date */}
              <div className="col-md-4">
                <label htmlFor="start_date" className="form-label">
                  Start Date <span className="text-danger">*</span>
                </label>
                <input
                  type="date"
                  className="form-control"
                  id="start_date"
                  name="start_date"
                  value={formData.start_date}
                  onChange={handleChange}
                  required
                />
              </div>

              {/* End Date */}
              <div className="col-md-4">
                <label htmlFor="end_date" className="form-label">
                  Expected End Date
                </label>
                <input
                  type="date"
                  className="form-control"
                  id="end_date"
                  name="end_date"
                  value={formData.end_date}
                  onChange={handleChange}
                />
              </div>

              {/* Geofence */}
              <div className="col-md-4">
                <label htmlFor="geofence" className="form-label">
                  Geofence Coordinates
                </label>
                <input
                  type="text"
                  className="form-control"
                  id="geofence"
                  name="geofence"
                  value={formData.geofence}
                  onChange={handleChange}
                  placeholder="e.g., 18.5204,73.8567"
                />
                <small className="text-muted">Enter latitude, longitude for project center</small>
              </div>
            </div>

            {/* Actions */}
            <div className="row mt-4">
              <div className="col-12">
                <hr />
                <div className="d-flex justify-content-end gap-2">
                  <button
                    type="button"
                    className="btn btn-outline-secondary"
                    onClick={() => navigate('/projects')}
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="btn btn-primary"
                    disabled={loading}
                  >
                    {loading ? (
                      <>
                        <span className="spinner spinner-border-sm me-2"></span>
                        Creating...
                      </>
                    ) : (
                      'Create Project'
                    )}
                  </button>
                </div>
              </div>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}

export default CreateProject;
