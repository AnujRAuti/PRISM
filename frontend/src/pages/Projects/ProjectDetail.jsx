import React from 'react';
import { useParams, Link } from 'react-router-dom';
import { useApp } from '../../context/AppContext';
import { IntegrityArc } from '../../components/ui/IntegrityArc';
import { getProjectImage } from '../../data/mockDataset';
import {
  FolderGit2,
  MapPin,
  Calendar,
  Building2,
  CheckCircle2,
  AlertTriangle,
  FileCheck,
  ArrowRight,
  ExternalLink,
  Layers,
  Clock,
  ArrowLeft,
} from 'lucide-react';

export default function ProjectDetail() {
  const { id } = useParams();
  const { projects, evidenceList } = useApp();

  const project =
    (projects || []).find((p) => p.id === id) ||
    projects?.[0] || {
      id: id || 'PRJ-PMGSY-MH-401',
      name: 'Purandar Taluka Rural Bitumen Road Reconstruction',
      scheme: 'PMGSY (Rural Roads)',
      ministry: 'Ministry of Rural Development',
      district: 'Pune',
      state: 'Maharashtra',
      block: 'Purandar',
      budgetInr: 34500000,
      contractor: 'Sahyadri Infrastructure Ltd.',
      startDate: '2026-03-01',
      endDate: '2026-08-30',
      geofenceRadiusMeters: 150,
      evidenceHealthScore: 94,
      totalSubmissions: 12,
      flaggedCount: 0,
      requiredEvidenceList: [],
      activities: [],
    };

  const projectEvidence = (evidenceList || []).filter((e) => e.projectId === project.id);

  return (
    <div style={{ padding: '1.5rem 2rem', maxWidth: '1440px', margin: '0 auto' }}>
      {/* Top Header */}
      <div style={{ marginBottom: '1.25rem' }}>
        <Link
          to="/projects"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.35rem',
            padding: '0.35rem 0.65rem',
            borderRadius: '4px',
            backgroundColor: 'var(--govt-gray-light)',
            border: '1px solid var(--govt-gray-medium)',
            color: 'var(--govt-gray-title)',
            fontSize: '0.775rem',
            fontWeight: 600,
            textDecoration: 'none',
            marginBottom: '0.75rem',
          }}
        >
          <ArrowLeft size={13} />
          <span>Back to Projects Directory</span>
        </Link>
      </div>

      {/* Project Master Dossier Header */}
      <div
        style={{
          backgroundColor: '#ffffff',
          border: '1px solid var(--govt-gray-medium)',
          borderRadius: 'var(--radius-lg, 12px)',
          padding: '1.5rem',
          boxShadow: 'var(--shadow-sm)',
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          gap: '1.5rem',
          marginBottom: '1.5rem',
        }}
      >
        <div style={{ maxWidth: '800px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.35rem' }}>
            <span
              style={{
                fontFamily: 'monospace',
                fontSize: '0.75rem',
                fontWeight: 700,
                padding: '0.15rem 0.5rem',
                borderRadius: '4px',
                backgroundColor: 'var(--govt-gray-light)',
                border: '1px solid var(--govt-gray-medium)',
              }}
            >
              {project.id}
            </span>
            <span style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--govt-blue-primary)' }}>
              {project.scheme}
            </span>
            <span style={{ fontSize: '0.75rem', color: 'var(--govt-gray-dark)' }}>{project.ministry}</span>
          </div>

          <h1
            style={{
              margin: '0.25rem 0 0.5rem',
              fontSize: '1.35rem',
              fontWeight: 800,
              color: 'var(--govt-blue-dark)',
            }}
          >
            {project.name}
          </h1>

          <div
            style={{
              display: 'flex',
              flexWrap: 'wrap',
              gap: '1rem',
              fontSize: '0.8rem',
              color: 'var(--govt-gray-dark)',
            }}
          >
            <span style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
              <MapPin size={13} /> {project.block}, {project.district}, {project.state}
            </span>
            <span style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
              <Building2 size={13} /> Contractor: {project.contractor}
            </span>
            <span style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
              <Calendar size={13} /> {project.startDate} to {project.endDate}
            </span>
          </div>
        </div>

        {/* Health Index Arc */}
        <div
          style={{
            backgroundColor: 'var(--govt-gray-off-white)',
            border: '1px solid var(--govt-gray-medium)',
            borderRadius: '8px',
            padding: '1rem 1.5rem',
            textAlign: 'center',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: '0.4rem',
          }}
        >
          <span style={{ fontSize: '0.7rem', fontWeight: 700, textTransform: 'uppercase', color: 'var(--govt-gray-dark)' }}>
            Evidence Health Index
          </span>
          <IntegrityArc score={project.evidenceHealthScore} size="md" showRiskBadge />
        </div>
      </div>

      {/* 2-Column Section: Evidence Requirements Engine + Project Activities */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(12, 1fr)', gap: '1.5rem' }}>
        {/* Left 5 Cols: Domain Evidence Requirements Engine */}
        <div style={{ gridColumn: 'span 5', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div
            style={{
              backgroundColor: '#ffffff',
              border: '1px solid var(--govt-gray-medium)',
              borderRadius: 'var(--radius-lg, 12px)',
              padding: '1.25rem',
              boxShadow: 'var(--shadow-sm)',
            }}
          >
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                borderBottom: '1px solid var(--govt-gray-medium)',
                paddingBottom: '0.75rem',
                marginBottom: '0.85rem',
              }}
            >
              <h3 style={{ margin: 0, fontSize: '0.9rem', fontWeight: 700, color: 'var(--govt-blue-dark)' }}>
                Mandatory Evidence Checklist
              </h3>
              <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--govt-gray-dark)' }}>
                {project.requiredEvidenceList?.length || 0} Criteria
              </span>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              {(project.requiredEvidenceList || []).map((req) => (
                <div
                  key={req.key}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '0.65rem 0.85rem',
                    borderRadius: '6px',
                    backgroundColor: 'var(--govt-gray-off-white)',
                    border: '1px solid var(--govt-gray-light)',
                    fontSize: '0.8rem',
                  }}
                >
                  <span style={{ fontWeight: 500, color: 'var(--govt-gray-title)' }}>{req.label}</span>
                  <span
                    style={{
                      fontSize: '0.7rem',
                      fontWeight: 700,
                      padding: '0.15rem 0.5rem',
                      borderRadius: '4px',
                      backgroundColor:
                        req.status === 'FULFILLED'
                          ? 'rgba(5, 150, 105, 0.12)'
                          : req.status === 'PARTIAL'
                          ? 'rgba(217, 119, 6, 0.12)'
                          : 'rgba(220, 38, 38, 0.12)',
                      color:
                        req.status === 'FULFILLED'
                          ? 'var(--govt-success)'
                          : req.status === 'PARTIAL'
                          ? 'var(--govt-warning)'
                          : 'var(--govt-danger)',
                    }}
                  >
                    {req.status}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Right 7 Cols: Submitted Evidence Submissions */}
        <div style={{ gridColumn: 'span 7' }}>
          <div
            style={{
              backgroundColor: '#ffffff',
              border: '1px solid var(--govt-gray-medium)',
              borderRadius: 'var(--radius-lg, 12px)',
              padding: '1.25rem',
              boxShadow: 'var(--shadow-sm)',
            }}
          >
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                borderBottom: '1px solid var(--govt-gray-medium)',
                paddingBottom: '0.75rem',
                marginBottom: '0.85rem',
              }}
            >
              <h3 style={{ margin: 0, fontSize: '0.9rem', fontWeight: 700, color: 'var(--govt-blue-dark)' }}>
                Associated Cryptographic Evidence
              </h3>
              <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--govt-gray-dark)' }}>
                {projectEvidence.length} items
              </span>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              {projectEvidence.length === 0 ? (
                <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--govt-gray-dark)', fontSize: '0.8rem' }}>
                  No evidence records linked to this project yet.
                </div>
              ) : (
                projectEvidence.map((ev) => (
                  <div
                    key={ev.id}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '0.75rem',
                      borderRadius: '6px',
                      border: '1px solid var(--govt-gray-medium)',
                      backgroundColor: '#ffffff',
                      fontSize: '0.8rem',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                      <img
                        src={ev.imageUrl}
                        alt=""
                        style={{ width: '40px', height: '40px', borderRadius: '4px', objectFit: 'cover' }}
                      />
                      <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                          <span style={{ fontFamily: 'monospace', fontWeight: 700, color: 'var(--govt-blue-dark)' }}>
                            {ev.id}
                          </span>
                          <span style={{ fontSize: '0.7rem', color: 'var(--govt-gray-dark)' }}>
                            • {new Date(ev.capturedAt).toLocaleDateString()}
                          </span>
                        </div>
                        <span style={{ fontWeight: 600, color: 'var(--govt-gray-title)' }}>{ev.title}</span>
                      </div>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                      <IntegrityArc score={ev.integrityScore} size="sm" showLabel />
                      <Link
                        to={`/evidence/${ev.id}`}
                        style={{
                          padding: '0.35rem 0.65rem',
                          borderRadius: '4px',
                          backgroundColor: 'var(--govt-gray-light)',
                          border: '1px solid var(--govt-gray-medium)',
                          color: 'var(--govt-blue-primary)',
                          fontSize: '0.75rem',
                          fontWeight: 700,
                          textDecoration: 'none',
                        }}
                      >
                        Inspect
                      </Link>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
