import React, { useState, useRef } from 'react';
import { useApp } from '../../context/AppContext';
import {
  Camera,
  MapPin,
  CheckCircle2,
  Upload,
  Mic,
  MicOff,
  RotateCcw,
  Wifi,
  WifiOff,
  ArrowRight,
  ArrowLeft,
  Check,
  Sparkles,
  Layers,
  FileCheck,
} from 'lucide-react';

export default function FieldOperations() {
  const { evidenceList, projects, addToast } = useApp();

  const [currentStep, setCurrentStep] = useState(1);
  const [selectedCaseId, setSelectedCaseId] = useState(evidenceList?.[0]?.id || 'EVD-2026-8812');
  const [capturedImage, setCapturedImage] = useState(null);
  const [isCapturing, setIsCapturing] = useState(false);
  const [isRecordingVoice, setIsRecordingVoice] = useState(false);
  const [voiceNoteText, setVoiceNoteText] = useState('');
  const [isOffline, setIsOffline] = useState(false);
  const [isSuccess, setIsSuccess] = useState(false);

  const fileInputRef = useRef(null);

  const activeEvidence = (evidenceList || []).find((e) => e.id === selectedCaseId) || evidenceList?.[0] || {
    id: 'EVD-2026-8812',
    projectId: 'PRJ-PMGSY-MH-401',
    imageUrl: '/images/projects/road-pothole.jpg',
    projectName: 'Purandar Taluka Rural Bitumen Road Reconstruction',
    scheme: 'PMGSY (Rural Roads)',
  };

  const activeProject = (projects || []).find((p) => p.id === activeEvidence.projectId) || projects?.[0] || {
    id: 'PRJ-PMGSY-MH-401',
    name: 'Purandar Taluka Rural Bitumen Road Reconstruction',
    district: 'Pune',
    state: 'Maharashtra',
  };

  const handleSnapPhoto = () => {
    setIsCapturing(true);
    setTimeout(() => {
      setCapturedImage(activeEvidence.imageUrl);
      setIsCapturing(false);
      setCurrentStep(3);
      addToast({
        title: 'फोटो खींची गई (Photo Captured)',
        description: 'GPS लोकेशन और समय फोटो के साथ सुरक्षित जोड़ दिया गया है।',
        type: 'success',
      });
    }, 400);
  };

  const handleFileChange = (e) => {
    const file = e.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = (event) => {
        setCapturedImage(event.target?.result);
        setCurrentStep(3);
        addToast({
          title: 'फोटो अपलोड हो गई (Photo Uploaded)',
          description: 'स्थान और समय स्वतः सत्यापित किया गया।',
          type: 'success',
        });
      };
      reader.readAsDataURL(file);
    }
  };

  const handleToggleVoice = () => {
    if (isRecordingVoice) {
      setIsRecordingVoice(false);
    } else {
      setIsRecordingVoice(true);
      setTimeout(() => {
        setVoiceNoteText(
          'स्थल पर 4.2 किमी सड़क का डामरीकरण कार्य पूर्ण हो चुका है। किनारे की सफेद पट्टियां खींच दी गई हैं।'
        );
        setIsRecordingVoice(false);
        addToast({
          title: 'आवाज से टिप्पणी दर्ज (Voice Note Recorded)',
          description: 'आवाज को टेक्स्ट में बदल दिया गया है।',
          type: 'info',
        });
      }, 1500);
    }
  };

  const handleFinalSubmit = () => {
    setIsSuccess(true);
    addToast({
      title: isOffline ? 'ऑफलाइन सुरक्षित (Saved Offline)' : 'साक्ष्य सफलता से भेजा गया (Uploaded)',
      description: isOffline
        ? 'फोटो फोन में सुरक्षित है। नेटवर्क मिलने पर खुद पोर्टल पर अपलोड हो जाएगी।'
        : `परियोजना #${activeProject.id} के लिए साक्ष्य रिकॉर्ड हो गया है।`,
      type: 'success',
    });
  };

  const handleReset = () => {
    setCapturedImage(null);
    setVoiceNoteText('');
    setIsSuccess(false);
    setCurrentStep(1);
  };

  return (
    <div style={{ padding: '1.5rem', maxWidth: '640px', margin: '0 auto' }}>
      {/* Top Header Bar */}
      <div
        style={{
          backgroundColor: '#ffffff',
          border: '1px solid var(--govt-gray-medium)',
          borderRadius: 'var(--radius-md, 8px)',
          padding: '0.85rem 1.25rem',
          boxShadow: 'var(--shadow-sm)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: '1rem',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <div
            style={{
              width: '36px',
              height: '36px',
              borderRadius: '50%',
              backgroundColor: 'var(--govt-blue-light)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '1.25rem',
            }}
          >
            📱
          </div>
          <div>
            <h1 style={{ margin: 0, fontSize: '0.95rem', fontWeight: 700, color: 'var(--govt-blue-dark)' }}>
              फील्ड साथी (Field Companion)
            </h1>
            <span style={{ fontSize: '0.75rem', color: 'var(--govt-gray-dark)' }}>
              सरल फोटो अपलोड प्रणाली • Government of India
            </span>
          </div>
        </div>

        {/* Offline / Online Network Indicator */}
        <button
          type="button"
          onClick={() => {
            setIsOffline(!isOffline);
            addToast({
              title: !isOffline ? 'ऑफलाइन मोड चालू (Offline Mode)' : 'इंटरनेट कनेक्टेड (Online)',
              description: !isOffline
                ? 'बिना इंटरनेट के भी फोटो खींची जा सकती है।'
                : 'पोर्टल से लाइव कनेक्ट हो गया है।',
              type: 'info',
            });
          }}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.35rem',
            padding: '0.35rem 0.75rem',
            borderRadius: '6px',
            fontSize: '0.75rem',
            fontWeight: 700,
            cursor: 'pointer',
            border: isOffline ? '1px solid var(--govt-warning)' : '1px solid var(--govt-success-border)',
            backgroundColor: isOffline ? 'var(--govt-warning-light)' : 'rgba(5, 150, 105, 0.1)',
            color: isOffline ? 'var(--govt-warning-text)' : 'var(--govt-success)',
          }}
        >
          {isOffline ? <WifiOff size={14} /> : <Wifi size={14} />}
          <span>{isOffline ? 'ऑफलाइन (Offline)' : 'इंटरनेट चालू (Online)'}</span>
        </button>
      </div>

      {/* 3-Step Wizard Tracker */}
      {!isSuccess && (
        <div
          style={{
            backgroundColor: '#ffffff',
            border: '1px solid var(--govt-gray-medium)',
            borderRadius: 'var(--radius-md, 8px)',
            padding: '0.75rem 1rem',
            boxShadow: 'var(--shadow-sm)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            marginBottom: '1.25rem',
            fontSize: '0.8rem',
          }}
        >
          <button
            type="button"
            onClick={() => setCurrentStep(1)}
            style={{
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '0.4rem',
              fontWeight: 700,
              color: currentStep === 1 ? 'var(--govt-blue-primary)' : currentStep > 1 ? 'var(--govt-success)' : 'var(--govt-gray-dark)',
            }}
          >
            <span
              style={{
                width: '24px',
                height: '24px',
                borderRadius: '50%',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                backgroundColor: currentStep === 1 ? 'var(--govt-blue-primary)' : currentStep > 1 ? 'var(--govt-success)' : 'var(--govt-gray-light)',
                color: currentStep >= 1 ? '#ffffff' : 'var(--govt-gray-dark)',
                fontSize: '0.75rem',
              }}
            >
              {currentStep > 1 ? '✓' : '1'}
            </span>
            <span>1. कार्य चुनें (Select Site)</span>
          </button>

          <span style={{ color: 'var(--govt-gray-dark)' }}>→</span>

          <button
            type="button"
            onClick={() => {
              if (selectedCaseId) setCurrentStep(2);
            }}
            style={{
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '0.4rem',
              fontWeight: 700,
              color: currentStep === 2 ? 'var(--govt-blue-primary)' : currentStep > 2 ? 'var(--govt-success)' : 'var(--govt-gray-dark)',
            }}
          >
            <span
              style={{
                width: '24px',
                height: '24px',
                borderRadius: '50%',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                backgroundColor: currentStep === 2 ? 'var(--govt-blue-primary)' : currentStep > 2 ? 'var(--govt-success)' : 'var(--govt-gray-light)',
                color: currentStep >= 2 ? '#ffffff' : 'var(--govt-gray-dark)',
                fontSize: '0.75rem',
              }}
            >
              {currentStep > 2 ? '✓' : '2'}
            </span>
            <span>2. फोटो खींचें (Photo)</span>
          </button>

          <span style={{ color: 'var(--govt-gray-dark)' }}>→</span>

          <button
            type="button"
            onClick={() => {
              if (capturedImage) setCurrentStep(3);
            }}
            style={{
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '0.4rem',
              fontWeight: 700,
              color: currentStep === 3 ? 'var(--govt-blue-primary)' : 'var(--govt-gray-dark)',
            }}
          >
            <span
              style={{
                width: '24px',
                height: '24px',
                borderRadius: '50%',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                backgroundColor: currentStep === 3 ? 'var(--govt-blue-primary)' : 'var(--govt-gray-light)',
                color: currentStep === 3 ? '#ffffff' : 'var(--govt-gray-dark)',
                fontSize: '0.75rem',
              }}
            >
              3
            </span>
            <span>3. पुष्टि करें (Submit)</span>
          </button>
        </div>
      )}

      {/* Step Content */}
      {isSuccess ? (
        <div
          style={{
            backgroundColor: '#ffffff',
            border: '1px solid var(--govt-success-border)',
            borderRadius: 'var(--radius-lg, 12px)',
            padding: '2.5rem 1.5rem',
            textAlign: 'center',
            boxShadow: 'var(--shadow-sm)',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: '1rem',
          }}
        >
          <div
            style={{
              width: '56px',
              height: '56px',
              borderRadius: '50%',
              backgroundColor: 'rgba(5, 150, 105, 0.12)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'var(--govt-success)',
            }}
          >
            <CheckCircle2 size={36} />
          </div>

          <div>
            <h2 style={{ margin: '0 0 0.35rem', fontSize: '1.25rem', fontWeight: 700, color: 'var(--govt-blue-dark)' }}>
              {isOffline ? 'फोटो ऑफलाइन सुरक्षित हो गई!' : 'साक्ष्य सफलतापूर्वक अपलोड हुआ!'}
            </h2>
            <p style={{ margin: 0, fontSize: '0.85rem', color: 'var(--govt-gray-dark)' }}>
              {isOffline
                ? 'नेटवर्क आने पर साक्ष्य स्वतः PRISM पोर्टल पर सिंक्रोनाइज़ हो जाएगा।'
                : 'क्रिप्टोग्राफिक SHA-256 हैश और GPS जियोफेंस सत्यापित कर लिया गया है।'}
            </p>
          </div>

          <button
            type="button"
            onClick={handleReset}
            style={{
              marginTop: '0.5rem',
              padding: '0.65rem 1.5rem',
              borderRadius: '6px',
              backgroundColor: 'var(--govt-blue-primary)',
              color: '#ffffff',
              fontSize: '0.85rem',
              fontWeight: 700,
              border: 'none',
              cursor: 'pointer',
            }}
          >
            नया फोटो खींचें (Capture Next)
          </button>
        </div>
      ) : currentStep === 1 ? (
        <div
          style={{
            backgroundColor: '#ffffff',
            border: '1px solid var(--govt-gray-medium)',
            borderRadius: 'var(--radius-lg, 12px)',
            padding: '1.25rem',
            boxShadow: 'var(--shadow-sm)',
          }}
        >
          <h2 style={{ margin: '0 0 0.75rem', fontSize: '1rem', fontWeight: 700, color: 'var(--govt-blue-dark)' }}>
            स्थल और कार्य चुनें (Select Inspection Assignment)
          </h2>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {(evidenceList || []).slice(0, 4).map((ev) => {
              const isSelected = selectedCaseId === ev.id;
              return (
                <div
                  key={ev.id}
                  onClick={() => setSelectedCaseId(ev.id)}
                  style={{
                    padding: '1rem',
                    borderRadius: '8px',
                    border: isSelected ? '1.5px solid var(--govt-blue-accent)' : '1px solid var(--govt-gray-medium)',
                    backgroundColor: isSelected ? 'var(--govt-blue-light)' : '#ffffff',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                  }}
                >
                  <div>
                    <span style={{ fontFamily: 'monospace', fontSize: '0.75rem', fontWeight: 700, color: 'var(--govt-blue-dark)' }}>
                      {ev.id} • {ev.scheme}
                    </span>
                    <h4 style={{ margin: '0.2rem 0', fontSize: '0.875rem', fontWeight: 600, color: 'var(--govt-gray-title)' }}>
                      {ev.activityName || ev.projectName}
                    </h4>
                    <span style={{ fontSize: '0.75rem', color: 'var(--govt-gray-dark)' }}>
                      📍 {ev.location?.district}, {ev.location?.state}
                    </span>
                  </div>
                  <span
                    style={{
                      width: '20px',
                      height: '20px',
                      borderRadius: '50%',
                      border: isSelected ? '5px solid var(--govt-blue-primary)' : '2px solid var(--govt-gray-medium)',
                      backgroundColor: '#ffffff',
                    }}
                  />
                </div>
              );
            })}
          </div>

          <button
            type="button"
            onClick={() => setCurrentStep(2)}
            style={{
              marginTop: '1.25rem',
              width: '100%',
              padding: '0.75rem',
              borderRadius: '6px',
              backgroundColor: 'var(--govt-blue-primary)',
              color: '#ffffff',
              fontSize: '0.85rem',
              fontWeight: 700,
              border: 'none',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '0.5rem',
            }}
          >
            <span>आगे बढ़ें (Proceed to Camera)</span>
            <ArrowRight size={16} />
          </button>
        </div>
      ) : currentStep === 2 ? (
        <div
          style={{
            backgroundColor: '#ffffff',
            border: '1px solid var(--govt-gray-medium)',
            borderRadius: 'var(--radius-lg, 12px)',
            padding: '1.5rem',
            boxShadow: 'var(--shadow-sm)',
            textAlign: 'center',
          }}
        >
          <h2 style={{ margin: '0 0 0.5rem', fontSize: '1rem', fontWeight: 700, color: 'var(--govt-blue-dark)' }}>
            लाइव फोटो खींचें (Capture Live Inspection Photo)
          </h2>
          <p style={{ margin: '0 0 1.25rem', fontSize: '0.8rem', color: 'var(--govt-gray-dark)' }}>
            कार्य स्थल के 150 मीटर के दायरे में रहकर सीधी फोटो खींचें।
          </p>

          <div
            style={{
              aspectRatio: '4/3',
              borderRadius: '8px',
              backgroundColor: '#0f172a',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '1rem',
              color: '#ffffff',
              marginBottom: '1.25rem',
              position: 'relative',
              overflow: 'hidden',
            }}
          >
            <Camera size={48} color="#94a3b8" />
            <div style={{ fontSize: '0.8rem', color: '#cbd5e1' }}>
              GPS Locked: 18.2814° N, 74.0156° E (±4.2m)
            </div>

            <div
              style={{
                position: 'absolute',
                bottom: '1rem',
                display: 'flex',
                gap: '0.75rem',
              }}
            >
              <button
                type="button"
                onClick={handleSnapPhoto}
                disabled={isCapturing}
                style={{
                  padding: '0.65rem 1.25rem',
                  borderRadius: '999px',
                  backgroundColor: 'var(--govt-blue-primary)',
                  color: '#ffffff',
                  fontWeight: 700,
                  fontSize: '0.85rem',
                  border: '2px solid #ffffff',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.4rem',
                }}
              >
                <Camera size={16} />
                <span>{isCapturing ? 'खींच रहे हैं...' : 'फोटो खींचें (Snap Photo)'}</span>
              </button>

              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                style={{
                  padding: '0.65rem 1rem',
                  borderRadius: '999px',
                  backgroundColor: 'rgba(255, 255, 255, 0.2)',
                  color: '#ffffff',
                  fontWeight: 600,
                  fontSize: '0.8rem',
                  border: '1px solid rgba(255, 255, 255, 0.4)',
                  cursor: 'pointer',
                  backdropFilter: 'blur(4px)',
                }}
              >
                फ़ाइल चुनें (File)
              </button>
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                onChange={handleFileChange}
                style={{ display: 'none' }}
              />
            </div>
          </div>

          <button
            type="button"
            onClick={() => setCurrentStep(1)}
            style={{
              background: 'none',
              border: 'none',
              color: 'var(--govt-gray-dark)',
              fontSize: '0.8rem',
              fontWeight: 600,
              cursor: 'pointer',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.35rem',
            }}
          >
            <ArrowLeft size={14} />
            <span>पीछे जाएं (Back to Tasks)</span>
          </button>
        </div>
      ) : (
        <div
          style={{
            backgroundColor: '#ffffff',
            border: '1px solid var(--govt-gray-medium)',
            borderRadius: 'var(--radius-lg, 12px)',
            padding: '1.5rem',
            boxShadow: 'var(--shadow-sm)',
            display: 'flex',
            flexDirection: 'column',
            gap: '1.25rem',
          }}
        >
          <h2 style={{ margin: 0, fontSize: '1rem', fontWeight: 700, color: 'var(--govt-blue-dark)' }}>
            3. पुष्टि करें और भेजें (Confirm & Upload)
          </h2>

          <div
            style={{
              aspectRatio: '16/9',
              borderRadius: '8px',
              overflow: 'hidden',
              backgroundColor: '#0f172a',
              border: '1px solid var(--govt-gray-medium)',
            }}
          >
            <img
              src={capturedImage || activeEvidence.imageUrl}
              alt="Captured Site"
              style={{ width: '100%', height: '100%', objectFit: 'cover' }}
            />
          </div>

          <div
            style={{
              backgroundColor: 'var(--govt-gray-off-white)',
              borderRadius: '8px',
              padding: '0.85rem 1rem',
              border: '1px solid var(--govt-gray-medium)',
              fontSize: '0.8rem',
              display: 'flex',
              flexDirection: 'column',
              gap: '0.4rem',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--govt-gray-dark)' }}>जियोफेंस सत्यापन (Geofence):</span>
              <span style={{ fontWeight: 700, color: 'var(--govt-success)' }}>✓ कार्य स्थल से 28m भीतर</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--govt-gray-dark)' }}>समय (Capture Time):</span>
              <span style={{ fontWeight: 600 }}>{new Date().toLocaleTimeString()}</span>
            </div>
          </div>

          {/* Voice Note Simulation */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--govt-gray-title)' }}>
                आवाज में टिप्पणी जोड़ें (Voice Note):
              </span>
              <button
                type="button"
                onClick={handleToggleVoice}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.35rem',
                  padding: '0.35rem 0.75rem',
                  borderRadius: '6px',
                  backgroundColor: isRecordingVoice ? 'var(--govt-danger-light)' : 'var(--govt-gray-light)',
                  border: isRecordingVoice ? '1px solid var(--govt-danger)' : '1px solid var(--govt-gray-medium)',
                  color: isRecordingVoice ? 'var(--govt-danger)' : 'var(--govt-gray-title)',
                  fontSize: '0.75rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                {isRecordingVoice ? <MicOff size={14} /> : <Mic size={14} />}
                <span>{isRecordingVoice ? 'रिकॉर्डिंग जारी...' : 'बोलें (Record)'}</span>
              </button>
            </div>

            {voiceNoteText && (
              <p
                style={{
                  margin: 0,
                  padding: '0.65rem 0.85rem',
                  borderRadius: '6px',
                  backgroundColor: 'var(--govt-blue-light)',
                  border: '1px solid var(--govt-blue-accent)',
                  fontSize: '0.8rem',
                  color: 'var(--govt-blue-dark)',
                  fontStyle: 'italic',
                }}
              >
                "{voiceNoteText}"
              </p>
            )}
          </div>

          <div style={{ display: 'flex', gap: '0.75rem', marginTop: '0.5rem' }}>
            <button
              type="button"
              onClick={() => setCurrentStep(2)}
              style={{
                padding: '0.75rem 1rem',
                borderRadius: '6px',
                border: '1px solid var(--govt-gray-medium)',
                backgroundColor: 'var(--govt-gray-light)',
                color: 'var(--govt-gray-title)',
                fontSize: '0.85rem',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              दोबारा खींचें
            </button>
            <button
              type="button"
              onClick={handleFinalSubmit}
              style={{
                flex: 1,
                padding: '0.75rem',
                borderRadius: '6px',
                backgroundColor: 'var(--govt-success)',
                color: '#ffffff',
                fontSize: '0.85rem',
                fontWeight: 700,
                border: 'none',
                cursor: 'pointer',
                boxShadow: 'var(--shadow-sm)',
              }}
            >
              पोर्टल पर जमा करें (Submit to PRISM)
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
