import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { useApp } from '../../context/AppContext';
import { IntegrityArc } from '../../components/ui/IntegrityArc';
import {
  Cpu,
  Upload,
  Play,
  CheckCircle2,
  AlertTriangle,
  ShieldAlert,
  Layers,
  MapPin,
  Clock,
  Camera,
  FileCheck2,
  ArrowRight,
  RotateCcw,
  Sparkles,
} from 'lucide-react';

export default function IngestionSandbox() {
  const { addToast } = useApp();

  const presetScenarios = [
    {
      id: 'SCENARIO-1',
      name: '1. Genuine Road Reconstruction (PMGSY)',
      desc: 'All 7 multi-signals align: GPS within 28m, sequential EXIF, 91% structural asphalt change.',
      expectedScore: 94,
      expectedRisk: 'LOW',
      imageUrl: '/images/projects/road-pothole.jpg',
      claim: 'Completed 40mm thick asphalt concrete wearing coat with thermoplastic line markers across 4.20 km road.',
      lat: 18.2814,
      lng: 74.0156,
      geofenceDevMeters: 28,
      duplicateRisk: 3,
      manipulationRisk: 4,
      anomalies: [],
    },
    {
      id: 'SCENARIO-2',
      name: '2. Recycled Cross-District Water Pump (JJM)',
      desc: 'High duplicate risk: 94.7% embedding match with historical evidence from Jodhpur, 318 km away.',
      expectedScore: 28,
      expectedRisk: 'CRITICAL',
      imageUrl: '/images/projects/water-pump.jpg',
      claim: 'Newly installed 5HP dual solar pumping assembly providing 40,000 litres per day discharge into Chaksu tank.',
      lat: 26.6025,
      lng: 75.9515,
      geofenceDevMeters: 62,
      duplicateRisk: 96,
      manipulationRisk: 62,
      anomalies: [
        {
          title: 'Cross-Project Recycled Evidence (94.7% Visual Match)',
          desc: 'Perceptual & embedding similarity matched with historical record EVD-2025-1832 in Jodhpur (318.4 km away).',
        },
      ],
    },
    {
      id: 'SCENARIO-3',
      name: '3. Impossible Travel Teleportation (SSA)',
      desc: 'Temporal-spatial anomaly: 48.4 km geographic jump within 192 seconds (907 km/h implied velocity).',
      expectedScore: 41,
      expectedRisk: 'HIGH',
      imageUrl: '/images/projects/school-after.jpg',
      claim: 'Completed concrete polymer structural screeding and elastomeric waterproof coating on school roof.',
      lat: 25.6891,
      lng: 83.3912,
      geofenceDevMeters: 58200,
      duplicateRisk: 8,
      manipulationRisk: 12,
      anomalies: [
        {
          title: 'Impossible Travel Anomaly (48.4 km in 3m 12s)',
          desc: 'Physical transit velocity of 907.5 km/h between sequential camera upload coordinates is mathematically infeasible.',
        },
      ],
    },
    {
      id: 'SCENARIO-4',
      name: '4. Fabricated Streetlight Installation (SSA)',
      desc: 'Visual-claim mismatch: Contractor claims 10 solar LED streetlights erected, but vision model detects open barren ground.',
      expectedScore: 19,
      expectedRisk: 'CRITICAL',
      imageUrl: '/images/projects/school-solar-lights.jpg',
      claim: 'Erected 10 standalone 6-meter galvanized octagonal poles with integrated 40W Lumileds LED.',
      lat: 21.9348,
      lng: 86.7416,
      geofenceDevMeters: 45,
      duplicateRisk: 4,
      manipulationRisk: 10,
      anomalies: [
        {
          title: 'Severe Semantic Disconnect (Expected 10 Solar Lights, Found 0)',
          desc: 'Vision models identified open grassland terrain with zero steel poles, solar PV modules, or luminaire fixtures.',
        },
      ],
    },
  ];

  const [activeScenario, setActiveScenario] = useState(presetScenarios[0]);
  const [pipelineStep, setPipelineStep] = useState(0); // 0 = ready, 1-6 = running, 7 = finished
  const [isRunning, setIsRunning] = useState(false);

  const steps = [
    { title: '1. Cryptographic SHA-256 Hashing', desc: 'Generating immutable binary hash signature...' },
    { title: '2. EXIF & Sensor Metadata Extraction', desc: 'Validating camera make, ISO, exposure, and capture timestamp...' },
    { title: '3. Geospatial Geofence Verification', desc: 'Computing Haversine centroid distance against project boundary...' },
    { title: '4. Perceptual Hashing & Cross-Project Search', desc: 'Running pgvector nearest-neighbor search across nationwide corpus...' },
    { title: '5. Visual Manipulation & Object Detection', desc: 'Evaluating JPEG quantization tables and segmenting claimed infrastructure...' },
    { title: '6. Multi-Signal Evidence Fusion Engine', desc: 'Synthesizing weighted integrity & explainable risk score...' },
  ];

  const runPipeline = () => {
    setIsRunning(true);
    setPipelineStep(1);

    const advanceStep = (current) => {
      if (current < 6) {
        setTimeout(() => {
          setPipelineStep(current + 1);
          advanceStep(current + 1);
        }, 550);
      } else {
        setTimeout(() => {
          setPipelineStep(7);
          setIsRunning(false);
          addToast({
            title: 'Evidence Ingestion & Audit Complete',
            description: `Integrity Score: ${activeScenario.expectedScore}/100 (${activeScenario.expectedRisk} Risk).`,
            type: activeScenario.expectedScore > 70 ? 'success' : 'warning',
          });
        }, 600);
      }
    };

    advanceStep(1);
  };

  const resetPipeline = () => {
    setPipelineStep(0);
    setIsRunning(false);
  };

  return (
    <div style={{ padding: '1.5rem 2rem', maxWidth: '1440px', margin: '0 auto' }}>
      {/* Header */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '1rem',
          paddingBottom: '1rem',
          borderBottom: '1px solid var(--govt-gray-medium, #e2e8f0)',
          marginBottom: '1.5rem',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <h1
              style={{
                margin: 0,
                fontSize: '1.5rem',
                fontWeight: 700,
                color: 'var(--govt-blue-dark, #0f172a)',
                letterSpacing: '-0.02em',
              }}
            >
              Live Evidence Ingestion & Fusion Sandbox
            </h1>
            <span
              style={{
                fontSize: '0.75rem',
                padding: '0.2rem 0.6rem',
                borderRadius: '4px',
                backgroundColor: 'var(--govt-blue-light)',
                border: '1px solid var(--govt-blue-accent)',
                color: 'var(--govt-blue-primary)',
                fontWeight: 700,
              }}
            >
              Multi-Signal AI Pipeline
            </span>
          </div>
          <p style={{ margin: '0.35rem 0 0', fontSize: '0.85rem', color: 'var(--govt-gray-dark)' }}>
            Real-time execution of the 7-signal evidence intelligence pipeline. Select a benchmark test case or observe step-by-step verification.
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          {pipelineStep === 7 ? (
            <button
              type="button"
              onClick={resetPipeline}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.4rem',
                padding: '0.5rem 1rem',
                borderRadius: '6px',
                backgroundColor: 'var(--govt-gray-light)',
                border: '1px solid var(--govt-gray-medium)',
                color: 'var(--govt-gray-title)',
                fontSize: '0.825rem',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              <RotateCcw size={15} />
              <span>Reset Sandbox</span>
            </button>
          ) : (
            <button
              type="button"
              onClick={runPipeline}
              disabled={isRunning}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.4rem',
                padding: '0.5rem 1.25rem',
                borderRadius: '6px',
                backgroundColor: 'var(--govt-blue-primary)',
                border: 'none',
                color: '#ffffff',
                fontSize: '0.825rem',
                fontWeight: 700,
                cursor: isRunning ? 'not-allowed' : 'pointer',
                opacity: isRunning ? 0.6 : 1,
                boxShadow: 'var(--shadow-sm)',
              }}
            >
              <Play size={15} fill="#ffffff" />
              <span>{isRunning ? 'Processing Pipeline...' : 'Run Ingestion Pipeline'}</span>
            </button>
          )}
        </div>
      </div>

      {/* Preset Scenarios Selector Bar */}
      <div style={{ marginBottom: '1.5rem' }}>
        <span
          style={{
            fontSize: '0.75rem',
            fontWeight: 700,
            textTransform: 'uppercase',
            letterSpacing: '0.04em',
            color: 'var(--govt-gray-dark)',
            display: 'block',
            marginBottom: '0.6rem',
          }}
        >
          Select Benchmark Test Scenario
        </span>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '1rem' }}>
          {presetScenarios.map((sc) => {
            const isSelected = activeScenario.id === sc.id;
            return (
              <button
                key={sc.id}
                type="button"
                onClick={() => {
                  setActiveScenario(sc);
                  resetPipeline();
                }}
                style={{
                  padding: '1rem',
                  borderRadius: '8px',
                  textAlign: 'left',
                  cursor: 'pointer',
                  backgroundColor: isSelected ? 'var(--govt-blue-light, #eff6ff)' : '#ffffff',
                  border: isSelected ? '1.5px solid var(--govt-blue-accent, #2563eb)' : '1px solid var(--govt-gray-medium, #e2e8f0)',
                  boxShadow: isSelected ? 'var(--shadow-sm)' : 'none',
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'space-between',
                  gap: '0.75rem',
                  transition: 'all 0.15s ease',
                }}
              >
                <div>
                  <span style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--govt-gray-title, #0f172a)', display: 'block' }}>
                    {sc.name}
                  </span>
                  <p style={{ margin: '0.35rem 0 0', fontSize: '0.75rem', color: 'var(--govt-gray-dark, #64748b)', lineHeight: 1.35 }}>
                    {sc.desc}
                  </p>
                </div>
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    fontSize: '0.75rem',
                    borderTop: '1px solid var(--govt-gray-light)',
                    paddingTop: '0.5rem',
                  }}
                >
                  <span style={{ color: 'var(--govt-gray-dark)' }}>Expected:</span>
                  <span
                    style={{
                      fontWeight: 700,
                      color:
                        sc.expectedRisk === 'LOW'
                          ? 'var(--govt-success)'
                          : sc.expectedRisk === 'HIGH'
                          ? 'var(--govt-warning)'
                          : 'var(--govt-danger)',
                    }}
                  >
                    Score {sc.expectedScore} ({sc.expectedRisk})
                  </span>
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* Main Sandbox Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(12, 1fr)', gap: '1.5rem' }}>
        {/* Left 5 Cols: Input Payload Dossier */}
        <div style={{ gridColumn: 'span 5' }}>
          <div
            style={{
              backgroundColor: '#ffffff',
              border: '1px solid var(--govt-gray-medium)',
              borderRadius: 'var(--radius-lg, 12px)',
              overflow: 'hidden',
              boxShadow: 'var(--shadow-sm)',
            }}
          >
            <div
              style={{
                padding: '0.75rem 1rem',
                backgroundColor: 'var(--govt-gray-off-white)',
                borderBottom: '1px solid var(--govt-gray-medium)',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                fontSize: '0.8rem',
                fontWeight: 700,
              }}
            >
              <span style={{ color: 'var(--govt-blue-dark)' }}>Input Evidence Payload</span>
              <span style={{ fontFamily: 'monospace', color: 'var(--govt-gray-dark)' }}>{activeScenario.id}</span>
            </div>

            <div style={{ aspectRatio: '4/3', backgroundColor: '#0f172a', position: 'relative', overflow: 'hidden' }}>
              <img
                src={activeScenario.imageUrl}
                alt="Test Evidence"
                style={{ width: '100%', height: '100%', objectFit: 'cover' }}
              />
              <div
                style={{
                  position: 'absolute',
                  bottom: '0.5rem',
                  left: '0.5rem',
                  padding: '0.2rem 0.5rem',
                  borderRadius: '4px',
                  backgroundColor: 'rgba(15, 23, 42, 0.8)',
                  color: '#ffffff',
                  fontFamily: 'monospace',
                  fontSize: '0.75rem',
                }}
              >
                {activeScenario.lat.toFixed(4)}° N, {activeScenario.lng.toFixed(4)}° E
              </div>
            </div>

            <div style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '0.75rem', fontSize: '0.8rem' }}>
              <span style={{ fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase', color: 'var(--govt-gray-dark)' }}>
                Contractor Claimed Activity:
              </span>
              <p
                style={{
                  margin: 0,
                  fontStyle: 'italic',
                  color: 'var(--govt-gray-text)',
                  backgroundColor: 'var(--govt-gray-off-white)',
                  padding: '0.75rem',
                  borderRadius: '6px',
                  border: '1px solid var(--govt-gray-light)',
                  lineHeight: 1.4,
                }}
              >
                "{activeScenario.claim}"
              </p>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem', paddingTop: '0.5rem' }}>
                <div style={{ padding: '0.5rem', borderRadius: '4px', backgroundColor: 'var(--govt-gray-light)' }}>
                  <span style={{ fontSize: '0.7rem', color: 'var(--govt-gray-dark)', display: 'block' }}>Centroid Delta:</span>
                  <span style={{ fontWeight: 700 }}>{activeScenario.geofenceDevMeters}m</span>
                </div>
                <div style={{ padding: '0.5rem', borderRadius: '4px', backgroundColor: 'var(--govt-gray-light)' }}>
                  <span style={{ fontSize: '0.7rem', color: 'var(--govt-gray-dark)', display: 'block' }}>Duplicate Match:</span>
                  <span style={{ fontWeight: 700 }}>{activeScenario.duplicateRisk}%</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Right 7 Cols: Pipeline Stage Execution & Outcome */}
        <div style={{ gridColumn: 'span 7' }}>
          <div
            style={{
              backgroundColor: '#ffffff',
              border: '1px solid var(--govt-gray-medium)',
              borderRadius: 'var(--radius-lg, 12px)',
              padding: '1.5rem',
              boxShadow: 'var(--shadow-sm)',
            }}
          >
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                borderBottom: '1px solid var(--govt-gray-medium)',
                paddingBottom: '0.85rem',
                marginBottom: '1rem',
              }}
            >
              <h3 style={{ margin: 0, fontSize: '0.95rem', fontWeight: 700, color: 'var(--govt-blue-dark)' }}>
                7-Signal Fusion Pipeline Progress
              </h3>
              <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--govt-gray-dark)' }}>
                {pipelineStep === 0
                  ? 'Ready to Execute'
                  : pipelineStep === 7
                  ? 'Verification Complete'
                  : `Running Step ${pipelineStep} of 6...`}
              </span>
            </div>

            {/* Steps Progress List */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
              {steps.map((st, idx) => {
                const stepNum = idx + 1;
                const isCompleted = pipelineStep > stepNum || pipelineStep === 7;
                const isCurrent = pipelineStep === stepNum;

                return (
                  <div
                    key={st.title}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.75rem',
                      padding: '0.65rem 0.85rem',
                      borderRadius: '6px',
                      backgroundColor: isCurrent
                        ? 'var(--govt-blue-light, #eff6ff)'
                        : isCompleted
                        ? 'rgba(5, 150, 105, 0.05)'
                        : 'var(--govt-gray-off-white, #f8fafc)',
                      border: isCurrent
                        ? '1px solid var(--govt-blue-accent, #2563eb)'
                        : isCompleted
                        ? '1px solid var(--govt-success-border, #a7f3d0)'
                        : '1px solid var(--govt-gray-light, #f1f5f9)',
                      transition: 'all 0.2s ease',
                    }}
                  >
                    <div style={{ flexShrink: 0 }}>
                      {isCompleted ? (
                        <CheckCircle2 size={16} color="var(--govt-success, #059669)" />
                      ) : isCurrent ? (
                        <div
                          style={{
                            width: '14px',
                            height: '14px',
                            borderRadius: '50%',
                            border: '2px solid var(--govt-blue-primary)',
                            borderTopColor: 'transparent',
                            animation: 'spin 0.8s linear infinite',
                          }}
                        />
                      ) : (
                        <div
                          style={{
                            width: '14px',
                            height: '14px',
                            borderRadius: '50%',
                            border: '1.5px solid var(--govt-gray-medium)',
                          }}
                        />
                      )}
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <span
                        style={{
                          fontSize: '0.8rem',
                          fontWeight: isCurrent || isCompleted ? 700 : 500,
                          color: isCurrent
                            ? 'var(--govt-blue-primary)'
                            : isCompleted
                            ? 'var(--govt-gray-title)'
                            : 'var(--govt-gray-dark)',
                          display: 'block',
                        }}
                      >
                        {st.title}
                      </span>
                      <span style={{ fontSize: '0.725rem', color: 'var(--govt-gray-dark)' }}>{st.desc}</span>
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Final Fusion Outcome Card (Appears when pipelineStep === 7) */}
            {pipelineStep === 7 && (
              <div
                style={{
                  marginTop: '1.25rem',
                  padding: '1.25rem',
                  borderRadius: '8px',
                  backgroundColor: 'var(--govt-gray-off-white)',
                  border: '1px solid var(--govt-gray-medium)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: '1.5rem',
                }}
              >
                <div>
                  <span
                    style={{
                      fontSize: '0.75rem',
                      fontWeight: 700,
                      textTransform: 'uppercase',
                      color: 'var(--govt-gray-dark)',
                    }}
                  >
                    Synthesized Audit Conclusion
                  </span>
                  <h4
                    style={{
                      margin: '0.25rem 0',
                      fontSize: '1rem',
                      fontWeight: 700,
                      color:
                        activeScenario.expectedScore >= 80
                          ? 'var(--govt-success)'
                          : activeScenario.expectedScore >= 40
                          ? 'var(--govt-warning)'
                          : 'var(--govt-danger)',
                    }}
                  >
                    {activeScenario.expectedScore >= 80
                      ? 'Statutory Integrity Verified (Pass)'
                      : activeScenario.expectedScore >= 40
                      ? 'Flagged for Senior Reviewer Attention'
                      : 'Severe Cryptographic Anomaly Detected'}
                  </h4>
                  {activeScenario.anomalies.length > 0 ? (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem', marginTop: '0.4rem' }}>
                      {activeScenario.anomalies.map((anom, i) => (
                        <span key={i} style={{ fontSize: '0.775rem', color: 'var(--govt-danger)', fontWeight: 600 }}>
                          ⚠ {anom.title}
                        </span>
                      ))}
                    </div>
                  ) : (
                    <span style={{ fontSize: '0.775rem', color: 'var(--govt-success)', fontWeight: 600 }}>
                      ✓ All 7 multi-signals passed within statutory variance bounds.
                    </span>
                  )}
                </div>

                <IntegrityArc score={activeScenario.expectedScore} size="lg" showRiskBadge />
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
