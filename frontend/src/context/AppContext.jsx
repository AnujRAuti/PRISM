import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  MOCK_EVIDENCE_ITEMS,
  MOCK_PROJECTS,
  MOCK_AUDIT_EVENTS,
  getProjectImage
} from '../data/mockDataset';
import { casesApi, evidenceApi, projectsApi, auditApi } from '../services/api';

const AppContext = createContext();

const STORAGE_KEYS = {
  user: 'eiil_current_user',
  evidence: 'eiil_evidence_list',
  auditEvents: 'eiil_audit_events',
  complaints: 'eiil_complaints',
  supervisorTasks: 'eiil_supervisor_tasks',
  density: 'eiil_table_density',
};

const INITIAL_CITIZEN_COMPLAINTS = [
  {
    id: 'CMP-1029',
    trackingId: 'GRV-2026-881',
    projectId: 'PRJ-PMGSY-MH-401',
    projectName: 'Purandar Taluka Rural Bitumen Road Reconstruction',
    category: 'Pavement Quality & Drainage',
    description: 'Road wearing coat was completed nicely, but rain drain on the left side near village school is blocked by construction gravel.',
    status: 'IN_REVIEW',
    statusLabel: 'Being Looked Into (जांच जारी)',
    filedAt: '2026-08-25T11:20:00+05:30',
    updatedAt: '2026-08-26T14:10:00+05:30',
    departmentResponse: 'Junior Engineer visited site on 26 Aug. Contractor instructed to clear drainage by 29 Aug.',
    filedBy: 'Ramesh Sharma (Verified Resident)',
    isVerifiedCitizen: true,
  },
  {
    id: 'CMP-1030',
    trackingId: 'GRV-2026-742',
    projectId: 'PRJ-JJM-RJ-108',
    projectName: 'Har Ghar Jal Rural Piped Water Scheme',
    category: 'Water Pressure',
    description: 'Solar pump installed 4 days ago, but household tap flow in Ward 2 is very low in the morning hours.',
    status: 'RECEIVED',
    statusLabel: 'Received by Department (शिकायत प्राप्त हुई)',
    filedAt: '2026-08-27T09:15:00+05:30',
    updatedAt: '2026-08-27T09:15:00+05:30',
    filedBy: 'Sunita Devi',
    isVerifiedCitizen: false,
  },
];

const INITIAL_SUPERVISOR_TASKS = [
  {
    id: 'TSK-01',
    projectId: 'PRJ-PMGSY-MH-401',
    projectName: 'Purandar Taluka Rural Bitumen Road (Km 0 to 4.2)',
    scheme: 'PMGSY (Rural Roads)',
    activityName: 'Final Bituminous Wearing Coat & Edge Lines',
    requiredStage: 'after',
    dueDate: '2026-08-30',
    distanceMeters: 28,
    status: 'PENDING',
    sampleLocation: { lat: 18.2814, lng: 74.0156 },
  },
  {
    id: 'TSK-02',
    projectId: 'PRJ-JJM-RJ-108',
    projectName: 'Chaksu Solar Dual-Pump & Tap Scheme',
    scheme: 'Jal Jeevan Mission',
    activityName: 'Retake Live Photo: Pump Assembly & Panel Array',
    requiredStage: 'after',
    dueDate: '2026-08-29',
    distanceMeters: 62,
    status: 'NEEDS_RETAKE',
    reviewerNote: 'The location in this photo did not match the site — please retake a clear live photo on site today.',
    sampleLocation: { lat: 26.6025, lng: 75.9515 },
  },
  {
    id: 'TSK-03',
    projectId: 'PRJ-KUSUM-KA-204',
    projectName: 'Tiptur Feeder Level Solarization (500 kW)',
    scheme: 'PM-KUSUM (Solar)',
    activityName: 'Ground-Mounted Array & Earthing Pit',
    requiredStage: 'after',
    dueDate: '2026-09-02',
    distanceMeters: 485,
    status: 'PENDING',
    sampleLocation: { lat: 13.2612, lng: 76.4820 },
  },
];

export function AppProvider({ children }) {
  const navigate = useNavigate();

  // Role & User Account State
  const [currentUser, setCurrentUser] = useState(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEYS.user);
      return saved ? JSON.parse(saved) : {
        id: 'USR-REV-01',
        name: 'Rajesh Kulkarni (SE & Lead Auditor)',
        role: 'REVIEWER',
        email: 'r.kulkarni@pwd.maharashtra.gov.in',
        district: 'Pune',
        state: 'Maharashtra',
        department: 'State Quality Audit Division',
      };
    } catch {
      return null;
    }
  });

  const [role, setRoleState] = useState(() => currentUser?.role || 'REVIEWER');

  const [evidenceList, setEvidenceList] = useState(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEYS.evidence);
      return saved ? JSON.parse(saved) : MOCK_EVIDENCE_ITEMS;
    } catch {
      return MOCK_EVIDENCE_ITEMS;
    }
  });

  const [projects, setProjects] = useState(MOCK_PROJECTS);

  const [auditEvents, setAuditEvents] = useState(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEYS.auditEvents);
      return saved ? JSON.parse(saved) : MOCK_AUDIT_EVENTS;
    } catch {
      return MOCK_AUDIT_EVENTS;
    }
  });

  const [complaints, setComplaints] = useState(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEYS.complaints);
      return saved ? JSON.parse(saved) : INITIAL_CITIZEN_COMPLAINTS;
    } catch {
      return INITIAL_CITIZEN_COMPLAINTS;
    }
  });

  const [supervisorTasks, setSupervisorTasks] = useState(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEYS.supervisorTasks);
      return saved ? JSON.parse(saved) : INITIAL_SUPERVISOR_TASKS;
    } catch {
      return INITIAL_SUPERVISOR_TASKS;
    }
  });

  const [density, setDensityState] = useState(() => {
    return localStorage.getItem(STORAGE_KEYS.density) || 'comfortable';
  });

  const [selectedEvidenceIds, setSelectedEvidenceIds] = useState([]);
  const [toasts, setToasts] = useState([]);
  const [isCommandPaletteOpen, setIsCommandPaletteOpen] = useState(false);
  const [isShortcutsModalOpen, setIsShortcutsModalOpen] = useState(false);

  // Sync to localStorage
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEYS.evidence, JSON.stringify(evidenceList));
      localStorage.setItem(STORAGE_KEYS.auditEvents, JSON.stringify(auditEvents));
      localStorage.setItem(STORAGE_KEYS.complaints, JSON.stringify(complaints));
      localStorage.setItem(STORAGE_KEYS.supervisorTasks, JSON.stringify(supervisorTasks));
    } catch (e) {
      console.warn('Storage sync error', e);
    }
  }, [evidenceList, auditEvents, complaints, supervisorTasks]);

  // Global Keyboard Shortcuts (Cmd+K, ?, ESC)
  useEffect(() => {
    const handleKeyDown = (e) => {
      // Toggle Command Palette (Cmd+K or Ctrl+K)
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setIsCommandPaletteOpen((prev) => !prev);
        return;
      }

      // Quick Search shortcut '/'
      if (e.key === '/' && !['INPUT', 'TEXTAREA'].includes(document.activeElement?.tagName)) {
        e.preventDefault();
        setIsCommandPaletteOpen(true);
        return;
      }

      // Toggle Shortcuts Modal '?'
      if (e.key === '?' && !['INPUT', 'TEXTAREA'].includes(document.activeElement?.tagName)) {
        e.preventDefault();
        setIsShortcutsModalOpen((prev) => !prev);
        return;
      }

      // Close open modals on ESC
      if (e.key === 'Escape') {
        setIsCommandPaletteOpen(false);
        setIsShortcutsModalOpen(false);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const addToast = useCallback((toast) => {
    const id = 'toast_' + Math.random().toString(36).substring(2, 9);
    const newToast = {
      ...toast,
      id,
      timestamp: Date.now(),
    };
    setToasts((prev) => [...prev, newToast]);

    setTimeout(() => {
      removeToast(id);
    }, 6000);
  }, []);

  const removeToast = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const loginUser = (newRole, customUser = {}) => {
    let mockProfile;
    if (newRole === 'CITIZEN') {
      mockProfile = {
        id: 'USR-CITIZEN-01',
        name: 'Ramesh Sharma',
        role: 'CITIZEN',
        phone: '+91 98230 11223',
        district: 'Pune',
        state: 'Maharashtra',
        pincode: '412301',
        isAadhaarVerified: true,
        ...customUser,
      };
    } else if (newRole === 'SUPERVISOR') {
      mockProfile = {
        id: 'USR-SUP-01',
        name: 'Suresh Patil (Junior Engineer)',
        role: 'SUPERVISOR',
        phone: '+91 98450 33441',
        email: 'suresh.patil@field.gov.in',
        district: 'Pune',
        state: 'Maharashtra',
        department: 'PMGSY Rural Roads Division',
        ...customUser,
      };
    } else {
      mockProfile = {
        id: 'USR-REV-01',
        name: 'Rajesh Kulkarni (SE & Lead Auditor)',
        role: 'REVIEWER',
        email: 'r.kulkarni@pwd.maharashtra.gov.in',
        district: 'Pune',
        state: 'Maharashtra',
        department: 'State Quality Audit Division',
        ...customUser,
      };
    }

    setCurrentUser(mockProfile);
    setRoleState(newRole);
    localStorage.setItem(STORAGE_KEYS.user, JSON.stringify(mockProfile));

    addToast({
      title: `Welcome, ${mockProfile.name}`,
      description: `Authenticated as ${newRole}. Operations hub updated.`,
      type: 'success',
    });
  };

  const logoutUser = () => {
    setCurrentUser(null);
    localStorage.removeItem(STORAGE_KEYS.user);
    navigate('/login');
    addToast({
      title: 'Logged Out',
      description: 'Session ended safely.',
      type: 'info',
    });
  };

  const setDensity = (newDensity) => {
    setDensityState(newDensity);
    localStorage.setItem(STORAGE_KEYS.density, newDensity);
  };

  const addAuditEvent = (item, action, newState, reason) => {
    const newAuditEvent = {
      id: `AUD-${Date.now().toString().slice(-6)}-${Math.random().toString(36).slice(2, 5)}`,
      evidenceId: item.id,
      projectId: item.projectId,
      actorName: currentUser?.name || 'Audit Officer',
      actorRole: role,
      action,
      previousState: item.auditStatus,
      newState,
      reason,
      sha256Hash: item.sha256,
      timestamp: new Date().toISOString(),
    };
    setAuditEvents((prev) => [newAuditEvent, ...prev]);

    // Asynchronously submit to backend audit ledger if reachable
    auditApi.recordDecision({
      evidence_id: item.id,
      action,
      state: newState,
      rationale: reason,
      hash: item.sha256
    }).catch(() => {
      // Graceful offline fallback
    });
  };

  const toggleSelectEvidence = (id) => {
    setSelectedEvidenceIds((prev) =>
      prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]
    );
  };

  const selectAllEvidence = (ids) => {
    setSelectedEvidenceIds(ids);
  };

  const clearSelection = () => {
    setSelectedEvidenceIds([]);
  };

  const approveEvidence = (id, note = 'Approved upon visual & geofence multi-signal verification') => {
    const prevItem = evidenceList.find((e) => e.id === id);
    if (!prevItem) return;

    setEvidenceList((prev) =>
      prev.map((e) =>
        e.id === id
          ? {
              ...e,
              auditStatus: 'APPROVED',
              reviewer: {
                ...e.reviewer,
                assignedTo: currentUser?.name || 'Lead Reviewer',
                note,
                decisionDate: new Date().toISOString(),
              },
            }
          : e
      )
    );

    addAuditEvent(prevItem, 'APPROVE', 'APPROVED', note);

    addToast({
      title: `Evidence ${id} Approved`,
      description: `Cryptographic clearance issued. Status: APPROVED.`,
      type: 'success',
    });
  };

  const rejectEvidence = (id, reason) => {
    const prevItem = evidenceList.find((e) => e.id === id);
    if (!prevItem) return;

    setEvidenceList((prev) =>
      prev.map((e) =>
        e.id === id
          ? {
              ...e,
              auditStatus: 'REJECTED',
              reviewer: {
                ...e.reviewer,
                assignedTo: currentUser?.name || 'Lead Reviewer',
                note: reason,
                decisionDate: new Date().toISOString(),
              },
            }
          : e
      )
    );

    addAuditEvent(prevItem, 'REJECT', 'REJECTED', reason);

    addToast({
      title: `Evidence ${id} Rejected`,
      description: `Formal defect report recorded. Rejection logged in ledger.`,
      type: 'error',
    });
  };

  const flagEvidence = (id, reason) => {
    const prevItem = evidenceList.find((e) => e.id === id);
    if (!prevItem) return;

    setEvidenceList((prev) =>
      prev.map((e) =>
        e.id === id
          ? {
              ...e,
              auditStatus: 'FLAGGED',
              reviewer: {
                ...e.reviewer,
                assignedTo: currentUser?.name || 'Lead Reviewer',
                note: reason,
                decisionDate: new Date().toISOString(),
              },
            }
          : e
      )
    );

    addAuditEvent(prevItem, 'INSPECTION_REQUESTED', 'FLAGGED', reason);

    addToast({
      title: `Evidence ${id} Flagged`,
      description: `Field inspection requisition dispatched.`,
      type: 'warning',
    });
  };

  const overrideEvidence = (id, newScore, newRisk, mandatoryReason) => {
    const prevItem = evidenceList.find((e) => e.id === id);
    if (!prevItem) return;

    setEvidenceList((prev) =>
      prev.map((e) =>
        e.id === id
          ? {
              ...e,
              integrityScore: newScore,
              riskLevel: newRisk,
              auditStatus: 'OVERRIDDEN',
              reviewer: {
                ...e.reviewer,
                assignedTo: currentUser?.name || 'Senior Reviewer',
                overrideReason: mandatoryReason,
                decisionDate: new Date().toISOString(),
              },
            }
          : e
      )
    );

    addAuditEvent(prevItem, 'OVERRIDE', 'OVERRIDDEN', mandatoryReason);

    addToast({
      title: `AI Finding Overridden for ${id}`,
      description: `Adjusted integrity index to ${newScore}%. Reason logged in immutable ledger.`,
      type: 'info',
    });
  };

  const batchApprove = (ids) => {
    const affectedItems = evidenceList.filter((item) => ids.includes(item.id));
    setEvidenceList((prev) =>
      prev.map((e) => (ids.includes(e.id) ? { ...e, auditStatus: 'APPROVED' } : e))
    );
    affectedItems.forEach((item) =>
      addAuditEvent(item, 'APPROVE', 'APPROVED', 'Approved through institutional batch review action')
    );
    clearSelection();
    addToast({
      title: `Batch Verification Completed`,
      description: `${ids.length} evidence submissions approved.`,
      type: 'success',
    });
  };

  const batchFlag = (ids) => {
    const affectedItems = evidenceList.filter((item) => ids.includes(item.id));
    setEvidenceList((prev) =>
      prev.map((e) => (ids.includes(e.id) ? { ...e, auditStatus: 'FLAGGED' } : e))
    );
    affectedItems.forEach((item) =>
      addAuditEvent(item, 'INSPECTION_REQUESTED', 'FLAGGED', 'Flagged for physical field inspection via batch review')
    );
    clearSelection();
    addToast({
      title: `Batch Flagging Completed`,
      description: `${ids.length} submissions flagged for on-site physical inspection.`,
      type: 'warning',
    });
  };

  return (
    <AppContext.Provider
      value={{
        currentUser,
        role,
        setRole: loginUser,
        loginUser,
        logoutUser,
        evidenceList,
        projects,
        auditEvents,
        complaints,
        supervisorTasks,
        density,
        setDensity,
        selectedEvidenceIds,
        setSelectedEvidenceIds,
        toggleSelectEvidence,
        selectAllEvidence,
        clearSelection,
        approveEvidence,
        rejectEvidence,
        flagEvidence,
        overrideEvidence,
        batchApprove,
        batchFlag,
        toasts,
        addToast,
        removeToast,
        isCommandPaletteOpen,
        setIsCommandPaletteOpen,
        isShortcutsModalOpen,
        setIsShortcutsModalOpen,
      }}
    >
      {children}
    </AppContext.Provider>
  );
}

export function useApp() {
  const context = useContext(AppContext);
  if (!context) {
    throw new Error('useApp must be used within an AppProvider');
  }
  return context;
}
