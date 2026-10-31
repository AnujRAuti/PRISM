export interface Anomaly {
  id: string;
  type:
    | 'DUPLICATE_EVIDENCE'
    | 'CROSS_PROJECT_DUPLICATE'
    | 'LOCATION_MISMATCH'
    | 'TEMPORAL_MISMATCH'
    | 'METADATA_ANOMALY'
    | 'IMAGE_MANIPULATION_RISK'
    | 'CLAIM_MISMATCH'
    | 'INCOMPLETE_EVIDENCE'
    | 'VISUAL_INCONSISTENCY'
    | 'QUANTITY_UNSUPPORTED'
    | 'IMPOSSIBLE_TRAVEL';
  severity: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  confidence: number; // 0-100
  title: string;
  description: string;
  supportingData?: string;
  translatedDescription?: Record<string, string>;
}

export interface SimilarMatch {
  evidenceId: string;
  projectId: string;
  projectName: string;
  scheme: string;
  district: string;
  distanceKm: number;
  similarityPercentage: number;
  matchedFeature: 'pHash' | 'vector_embedding' | 'sha256_exact' | 'keypoint_sift';
  thumbnailUri: string;
}

export interface DetectedObject {
  label: string;
  confidence: number;
  box: [number, number, number, number]; // [ymin, xmin, ymax, xmax] percentage
}

export interface EvidenceItem {
  id: string;
  projectId: string;
  projectName: string;
  scheme: string;
  ministry: string;
  activityName: string;
  stage: 'before' | 'during' | 'after' | 'completion_doc';
  title: string;
  imageUrl: string;
  beforeImageUrl?: string;
  mimeType: string;
  sizeBytes: number;
  sha256: string;
  capturedAt: string;
  uploadedAt: string;
  location: {
    lat: number;
    lng: number;
    accuracyMeters: number;
    geofenceDistanceMeters: number;
    siteCentroid: { lat: number; lng: number };
    status: 'CONSISTENT' | 'DEVIATION' | 'ANOMALOUS';
    state: string;
    district: string;
    block: string;
  };
  camera: {
    make: string;
    model: string;
    software: string;
    focalLength: string;
    iso: string;
    exposure: string;
  };
  integrityScore: number; // 0-100
  riskLevel: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  auditStatus: 'PENDING' | 'APPROVED' | 'REJECTED' | 'FLAGGED' | 'OVERRIDDEN';
  reviewer?: {
    assignedTo: string;
    reviewedBy?: string;
    decisionDate?: string;
    note?: string;
    overrideReason?: string;
  };
  fusionScores: {
    gps: number;
    temporal: number;
    duplicateRisk: number; // lower is better
    manipulationRisk: number; // lower is better
    claimMatch: number;
    metadataIntegrity: number;
    completeness: number;
  };
  detectedAnomalies: Anomaly[];
  similarEvidenceMatches: SimilarMatch[];
  detectedObjects: DetectedObject[];
  structuralChangeConfidence?: number;
  claimText: string;
  modelVersion: string;
}

export interface Project {
  id: string;
  name: string;
  scheme: string;
  ministry: string;
  state: string;
  district: string;
  block: string;
  budgetInr: number;
  contractor: string;
  centroid: { lat: number; lng: number };
  geofenceRadiusMeters: number;
  startDate: string;
  endDate: string;
  status: 'IN_PROGRESS' | 'COMPLETED' | 'UNDER_AUDIT' | 'FLAGGED_HOLD';
  evidenceHealthScore: number;
  totalSubmissions: number;
  flaggedCount: number;
  imageUrl: string;
  requiredEvidenceList: {
    key: string;
    label: string;
    isMandatory: boolean;
    status: 'FULFILLED' | 'MISSING' | 'PARTIAL';
  }[];
  activities: {
    id: string;
    name: string;
    status: 'COMPLETED' | 'IN_PROGRESS' | 'PENDING';
    evidenceIds: string[];
  }[];
}

export interface AuditEvent {
  id: string;
  evidenceId: string;
  projectId: string;
  actorName: string;
  actorRole: string;
  action: 'UPLOAD' | 'AI_FUSION_ANALYSIS' | 'FLAG_CRITICAL' | 'APPROVE' | 'REJECT' | 'OVERRIDE' | 'INSPECTION_REQUESTED';
  previousState: string;
  newState: string;
  reason: string;
  sha256Hash: string;
  timestamp: string;
}

// 1. Projects Dataset (Strict 6 Projects Mapped to Local Images)
export const MOCK_PROJECTS: Project[] = [
  {
    id: 'PRJ-PMGSY-MH-401',
    name: 'Purandar Taluka Rural Bitumen Road Reconstruction (Km 0.00 to 4.20)',
    scheme: 'PMGSY (Rural Roads)',
    ministry: 'Ministry of Rural Development',
    state: 'Maharashtra',
    district: 'Pune',
    block: 'Purandar',
    budgetInr: 34500000,
    contractor: 'Sahyadri Infrastructure Ltd.',
    centroid: { lat: 18.2812, lng: 74.0154 },
    geofenceRadiusMeters: 150,
    startDate: '2026-03-01',
    endDate: '2026-08-30',
    status: 'COMPLETED',
    evidenceHealthScore: 94,
    totalSubmissions: 12,
    flaggedCount: 0,
    imageUrl: '/images/projects/road-pothole.jpg',
    requiredEvidenceList: [
      { key: 'before_photo', label: 'Before Road Condition Survey', isMandatory: true, status: 'FULFILLED' },
      { key: 'during_photo', label: 'During WBM Subgrade Laying', isMandatory: true, status: 'FULFILLED' },
      { key: 'after_photo', label: 'Final Bituminous Carpet Surface', isMandatory: true, status: 'FULFILLED' },
      { key: 'gps_centroid', label: 'Geo-centroid Waypoint Track', isMandatory: true, status: 'FULFILLED' },
      { key: 'qa_cert', label: 'Stage-3 Quality Inspection Certificate', isMandatory: true, status: 'FULFILLED' },
    ],
    activities: [
      { id: 'ACT-01', name: 'Existing Pavement Scarification', status: 'COMPLETED', evidenceIds: ['EVD-2026-8812'] },
      { id: 'ACT-02', name: 'Dense Bituminous Macadam (DBM) Layer', status: 'COMPLETED', evidenceIds: ['EVD-2026-8812'] },
      { id: 'ACT-03', name: 'Asphalt Wearing Course & Pavement Markings', status: 'COMPLETED', evidenceIds: ['EVD-2026-8812'] },
    ],
  },
  {
    id: 'PRJ-JJM-RJ-108',
    name: 'Har Ghar Jal Rural Piped Water Scheme with Solar Dual-Pump Well',
    scheme: 'Jal Jeevan Mission',
    ministry: 'Ministry of Jal Shakti',
    state: 'Rajasthan',
    district: 'Jaipur',
    block: 'Chaksu',
    budgetInr: 18200000,
    contractor: 'Marwar Water Engineering Works',
    centroid: { lat: 26.6021, lng: 75.9511 },
    geofenceRadiusMeters: 100,
    startDate: '2026-04-10',
    endDate: '2026-09-15',
    status: 'FLAGGED_HOLD',
    evidenceHealthScore: 28,
    totalSubmissions: 8,
    flaggedCount: 3,
    imageUrl: '/images/projects/water-pump.jpg',
    requiredEvidenceList: [
      { key: 'borewell_photo', label: 'Deep Borewell Drilling Site', isMandatory: true, status: 'FULFILLED' },
      { key: 'pump_install', label: 'Solar Submersible Pump & Panel Array', isMandatory: true, status: 'FULFILLED' },
      { key: 'staging_tank', label: 'Overhead RCC Staging Tank (50kL)', isMandatory: true, status: 'MISSING' },
      { key: 'tap_fhtc', label: 'Household Tap Connection Flow Verification', isMandatory: true, status: 'MISSING' },
    ],
    activities: [
      { id: 'ACT-J1', name: 'Borewell Drilling & Casing', status: 'COMPLETED', evidenceIds: ['EVD-2026-9041'] },
      { id: 'ACT-J2', name: 'Solar Dual-Pump & Control Panel Installation', status: 'IN_PROGRESS', evidenceIds: ['EVD-2026-9041'] },
    ],
  },
  {
    id: 'PRJ-SSA-UP-512',
    name: 'Government Primary & Upper Primary School Structural Roof & Masonry Repair',
    scheme: 'Samagra Shiksha Abhiyan',
    ministry: 'Ministry of Education',
    state: 'Uttar Pradesh',
    district: 'Varanasi',
    block: 'Pindra',
    budgetInr: 4600000,
    contractor: 'Kashi Constructions & Allied Services',
    centroid: { lat: 25.3176, lng: 82.9739 },
    geofenceRadiusMeters: 80,
    startDate: '2026-05-01',
    endDate: '2026-08-15',
    status: 'UNDER_AUDIT',
    evidenceHealthScore: 41,
    totalSubmissions: 6,
    flaggedCount: 2,
    imageUrl: '/images/projects/school-after.jpg',
    requiredEvidenceList: [
      { key: 'roof_damage', label: 'Pre-Repair Roof Spalling & Seepage Photos', isMandatory: true, status: 'FULFILLED' },
      { key: 'waterproofing', label: 'Waterproofing Membrane & Screed Coat', isMandatory: true, status: 'FULFILLED' },
      { key: 'final_classroom', label: 'Refurbished Classroom & Exterior Plaster', isMandatory: true, status: 'FULFILLED' },
    ],
    activities: [
      { id: 'ACT-S1', name: 'Structural Slab Retrofitting', status: 'IN_PROGRESS', evidenceIds: ['EVD-2026-7734'] },
    ],
  },
  {
    id: 'PRJ-KUSUM-KA-204',
    name: 'PM-KUSUM Component-C Feeder Level Solarization (500 kW Plant)',
    scheme: 'PM-KUSUM (Solar)',
    ministry: 'Ministry of New and Renewable Energy',
    state: 'Karnataka',
    district: 'Tumakuru',
    block: 'Tiptur',
    budgetInr: 22000000,
    contractor: 'Cauvery Solar Renewable Infra',
    centroid: { lat: 13.2577, lng: 76.4789 },
    geofenceRadiusMeters: 120,
    startDate: '2026-02-15',
    endDate: '2026-07-31',
    status: 'UNDER_AUDIT',
    evidenceHealthScore: 62,
    totalSubmissions: 14,
    flaggedCount: 1,
    imageUrl: '/images/projects/solar-plant.jpg',
    requiredEvidenceList: [
      { key: 'land_level', label: 'Land Grading & Foundation Pier Casts', isMandatory: true, status: 'FULFILLED' },
      { key: 'pv_array', label: 'Ground-Mounted Mono-PERC Solar Arrays', isMandatory: true, status: 'FULFILLED' },
      { key: 'grid_substation', label: 'Inverter Transformer & Discom Interconnection', isMandatory: true, status: 'FULFILLED' },
    ],
    activities: [
      { id: 'ACT-K1', name: 'Module Mounting Structure Installation', status: 'COMPLETED', evidenceIds: ['EVD-2026-6190'] },
    ],
  },
  {
    id: 'PRJ-SSA-OD-309',
    name: 'Model Tribal Residential Ashram School Solar Street Lighting & Campus Security',
    scheme: 'Samagra Shiksha Abhiyan',
    ministry: 'Ministry of Education & Tribal Affairs',
    state: 'Odisha',
    district: 'Mayurbhanj',
    block: 'Baripada',
    budgetInr: 1850000,
    contractor: 'Mayurbhanj Electricals & Infra',
    centroid: { lat: 21.9345, lng: 86.7412 },
    geofenceRadiusMeters: 100,
    startDate: '2026-06-01',
    endDate: '2026-08-20',
    status: 'FLAGGED_HOLD',
    evidenceHealthScore: 34,
    totalSubmissions: 4,
    flaggedCount: 2,
    imageUrl: '/images/projects/school-solar-lights.jpg',
    requiredEvidenceList: [
      { key: 'solar_pole_batch', label: '10x Standalone 40W LED Solar Street Lights Installed', isMandatory: true, status: 'PARTIAL' },
      { key: 'lithium_battery', label: 'Battery Box & MPPT Charge Controller Verification', isMandatory: true, status: 'MISSING' },
    ],
    activities: [
      { id: 'ACT-O1', name: 'Solar Pole Erection & Luminaires Fixture', status: 'IN_PROGRESS', evidenceIds: ['EVD-2026-5509'] },
    ],
  },
  {
    id: 'PRJ-PMGSY-AS-198',
    name: 'Brahmaputra Flood-Resilient Embankment Approach Road (Ch. 12+200)',
    scheme: 'PMGSY (Rural Roads)',
    ministry: 'Ministry of Rural Development',
    state: 'Assam',
    district: 'Kamrup',
    block: 'Hajo',
    budgetInr: 41200000,
    contractor: 'Pragjyotish Civil Works Pvt Ltd',
    centroid: { lat: 26.2483, lng: 91.5218 },
    geofenceRadiusMeters: 200,
    startDate: '2026-01-10',
    endDate: '2026-10-31',
    status: 'IN_PROGRESS',
    evidenceHealthScore: 58,
    totalSubmissions: 7,
    flaggedCount: 1,
    imageUrl: '/images/projects/embankment-road.jpg',
    requiredEvidenceList: [
      { key: 'geo_textile', label: 'Geo-textile Reinforcement Slope Protection', isMandatory: true, status: 'FULFILLED' },
      { key: 'stone_pitching', label: 'Boulder Stone Pitching on Toe Wall', isMandatory: true, status: 'MISSING' },
      { key: 'wearing_layer', label: 'Paver Asphalt Top Finish', isMandatory: true, status: 'PARTIAL' },
    ],
    activities: [
      { id: 'ACT-A1', name: 'Slope Embankment Stabilization', status: 'IN_PROGRESS', evidenceIds: ['EVD-2026-4402'] },
    ],
  },
];

// Helper to get local project image
export function getProjectImage(projectIdOrScheme?: string): string {
  if (!projectIdOrScheme) return '/images/projects/road-pothole.jpg';
  if (projectIdOrScheme === 'PRJ-PMGSY-MH-401' || projectIdOrScheme.includes('PMGSY') || projectIdOrScheme.includes('Bitumen') || projectIdOrScheme.includes('Purandar')) {
    return '/images/projects/road-pothole.jpg';
  }
  if (projectIdOrScheme === 'PRJ-JJM-RJ-108' || projectIdOrScheme.includes('JJM') || projectIdOrScheme.includes('Jal') || projectIdOrScheme.includes('Water')) {
    return '/images/projects/water-pump.jpg';
  }
  if (projectIdOrScheme === 'PRJ-SSA-UP-512' || (projectIdOrScheme.includes('Samagra') && projectIdOrScheme.includes('UP')) || projectIdOrScheme.includes('Primary') || projectIdOrScheme.includes('Roof')) {
    return '/images/projects/school-after.jpg';
  }
  if (projectIdOrScheme === 'PRJ-KUSUM-KA-204' || projectIdOrScheme.includes('KUSUM') || projectIdOrScheme.includes('Feeder')) {
    return '/images/projects/solar-plant.jpg';
  }
  if (projectIdOrScheme === 'PRJ-SSA-OD-309' || projectIdOrScheme.includes('Ashram') || projectIdOrScheme.includes('Lighting')) {
    return '/images/projects/school-solar-lights.jpg';
  }
  if (projectIdOrScheme === 'PRJ-PMGSY-AS-198' || projectIdOrScheme.includes('Brahmaputra') || projectIdOrScheme.includes('Embankment')) {
    return '/images/projects/embankment-road.jpg';
  }
  return '/images/projects/road-pothole.jpg';
}

// 2. Evidence Items Dataset (Strictly using local project assets)
export const MOCK_EVIDENCE_ITEMS: EvidenceItem[] = [
  // Item 1: Road Repair Evidence (PRJ-PMGSY-MH-401)
  {
    id: 'EVD-2026-8812',
    projectId: 'PRJ-PMGSY-MH-401',
    projectName: 'Purandar Taluka Rural Bitumen Road Reconstruction (Km 0.00 to 4.20)',
    scheme: 'PMGSY (Rural Roads)',
    ministry: 'Ministry of Rural Development',
    activityName: 'Asphalt Wearing Course & Pavement Markings',
    stage: 'after',
    title: 'Site Survey Photograph of Road Pavement Section with Pothole Defect',
    imageUrl: '/images/projects/road-pothole.jpg',
    mimeType: 'image/jpeg',
    sizeBytes: 3842100,
    sha256: '9f83a48e71b29d8164bc77f202e88a014902cd51772183e89f8a31362e08c491',
    capturedAt: '2026-08-20T14:32:10+05:30',
    uploadedAt: '2026-08-20T14:41:22+05:30',
    location: {
      lat: 18.2814,
      lng: 74.0156,
      accuracyMeters: 4.2,
      geofenceDistanceMeters: 28,
      siteCentroid: { lat: 18.2812, lng: 74.0154 },
      status: 'CONSISTENT',
      state: 'Maharashtra',
      district: 'Pune',
      block: 'Purandar',
    },
    camera: {
      make: 'Samsung',
      model: 'Galaxy A54 5G Enterprise',
      software: 'Govt e-Pramaan Mobile Client v3.1.2',
      focalLength: '5.4mm (f/1.8)',
      iso: '50',
      exposure: '1/850s',
    },
    integrityScore: 94,
    riskLevel: 'LOW',
    auditStatus: 'APPROVED',
    reviewer: {
      assignedTo: 'Rajesh Kulkarni (SE PWD)',
      reviewedBy: 'Rajesh Kulkarni (SE PWD)',
      decisionDate: '2026-08-21T10:15:00+05:30',
      note: 'Verified against field survey records. Geofence boundaries and GPS coordinates fully aligned.',
    },
    fusionScores: {
      gps: 98,
      temporal: 96,
      duplicateRisk: 3,
      manipulationRisk: 4,
      claimMatch: 95,
      metadataIntegrity: 96,
      completeness: 100,
    },
    detectedAnomalies: [],
    similarEvidenceMatches: [],
    detectedObjects: [
      { label: 'asphalt_road_surface', confidence: 0.98, box: [0.35, 0.05, 0.95, 0.95] },
      { label: 'road_pothole_defect', confidence: 0.93, box: [0.45, 0.30, 0.85, 0.70] },
    ],
    structuralChangeConfidence: 91,
    claimText: 'Field survey record of damaged road segment showing deep pothole along 4.20 km stretch.',
    modelVersion: 'eiil-vision-v2.4-pmgsy',
  },

  // Item 2: Recycled Cross-District Water Pump (PRJ-JJM-RJ-108)
  {
    id: 'EVD-2026-9041',
    projectId: 'PRJ-JJM-RJ-108',
    projectName: 'Har Ghar Jal Rural Piped Water Scheme with Solar Dual-Pump Well',
    scheme: 'Jal Jeevan Mission',
    ministry: 'Ministry of Jal Shakti',
    activityName: 'Solar Dual-Pump & Control Panel Installation',
    stage: 'after',
    title: 'Installed 5HP DC Submersible Solar Pump with 12-Panel Solar Array',
    imageUrl: '/images/projects/water-pump.jpg',
    mimeType: 'image/jpeg',
    sizeBytes: 4210900,
    sha256: '3c19e59d997a02c841bb28ff8390ab914028ce821102948caef198302bf029aa',
    capturedAt: '2026-08-25T11:20:45+05:30',
    uploadedAt: '2026-08-25T11:45:10+05:30',
    location: {
      lat: 26.6025,
      lng: 75.9515,
      accuracyMeters: 8.5,
      geofenceDistanceMeters: 62,
      siteCentroid: { lat: 26.6021, lng: 75.9511 },
      status: 'CONSISTENT',
      state: 'Rajasthan',
      district: 'Jaipur',
      block: 'Chaksu',
    },
    camera: {
      make: 'Xiaomi',
      model: 'Redmi Note 12 Pro',
      software: 'MIUI Camera v4.5',
      focalLength: '4.8mm (f/1.9)',
      iso: '100',
      exposure: '1/1200s',
    },
    integrityScore: 28,
    riskLevel: 'CRITICAL',
    auditStatus: 'FLAGGED',
    reviewer: {
      assignedTo: 'Vikram Singh Shekhawat (EE JJM)',
    },
    fusionScores: {
      gps: 88,
      temporal: 45,
      duplicateRisk: 96,
      manipulationRisk: 62,
      claimMatch: 80,
      metadataIntegrity: 40,
      completeness: 50,
    },
    detectedAnomalies: [
      {
        id: 'ANOM-01',
        type: 'CROSS_PROJECT_DUPLICATE',
        severity: 'CRITICAL',
        confidence: 94.7,
        title: 'Cross-Project Recycled Evidence Detected (94.7% Visual Match)',
        description: 'This photograph exhibits 94.7% perceptual & embedding similarity with evidence EVD-2025-1832 uploaded 8 months ago for a distinct scheme in Jodhpur district, located 318.4 km away.',
        supportingData: 'Matched Target: EVD-2025-1832 (PRJ-JJM-RJ-044, Jodhpur). pHash Hamming Distance: 2. Cosine Embedding Similarity: 0.947.',
      },
      {
        id: 'ANOM-02',
        type: 'METADATA_ANOMALY',
        severity: 'HIGH',
        confidence: 88.0,
        title: 'EXIF Timestamp Stripped & Modified by Third-Party Editor',
        description: 'Original EXIF DateTimeOriginal tag was deleted; software tag indicates secondary export via mobile image sharing app prior to upload.',
        supportingData: 'Original DateTime header missing. File header signature: WhatsApp/Lightroom re-encode.',
      },
    ],
    similarEvidenceMatches: [
      {
        evidenceId: 'EVD-2025-1832',
        projectId: 'PRJ-JJM-RJ-044',
        projectName: 'Phalodi Village Solar Piped Water Installation Stage 2',
        scheme: 'Jal Jeevan Mission',
        district: 'Jodhpur (318 km away)',
        distanceKm: 318.4,
        similarityPercentage: 94.7,
        matchedFeature: 'vector_embedding',
        thumbnailUri: '/images/projects/water-pump.jpg',
      },
      {
        evidenceId: 'EVD-2025-0914',
        projectId: 'PRJ-KUSUM-RJ-019',
        projectName: 'Bikaner Solar Ag Pump Grid Substation',
        scheme: 'PM-KUSUM',
        district: 'Bikaner (295 km away)',
        distanceKm: 295.1,
        similarityPercentage: 86.2,
        matchedFeature: 'pHash',
        thumbnailUri: '/images/projects/solar-plant.jpg',
      },
    ],
    detectedObjects: [
      { label: 'solar_panel_array', confidence: 0.96, box: [0.10, 0.15, 0.70, 0.85] },
      { label: 'pump_control_kiosk', confidence: 0.91, box: [0.55, 0.60, 0.90, 0.85] },
    ],
    claimText: 'Newly installed 5HP dual solar pumping assembly providing 40,000 litres per day discharge into Chaksu overhead reservoir.',
    modelVersion: 'eiil-vision-v2.4-water',
  },

  // Item 3: School Before & After Pair (PRJ-SSA-UP-512)
  {
    id: 'EVD-2026-7734',
    projectId: 'PRJ-SSA-UP-512',
    projectName: 'Government Primary & Upper Primary School Structural Roof & Masonry Repair',
    scheme: 'Samagra Shiksha Abhiyan',
    ministry: 'Ministry of Education',
    activityName: 'Structural Slab Retrofitting & Masonry Painting',
    stage: 'after',
    title: 'Completed Structural Roof Waterproofing & Masonry Plaster on Classroom Block',
    imageUrl: '/images/projects/school-after.jpg',
    beforeImageUrl: '/images/projects/school-before.jpg',
    mimeType: 'image/jpeg',
    sizeBytes: 3120400,
    sha256: '7b80a112cd4e0029b389182390fca8201994821a8bc4710182739481902ebaf1',
    capturedAt: '2026-08-26T10:04:12+05:30',
    uploadedAt: '2026-08-26T10:06:05+05:30',
    location: {
      lat: 25.3176,
      lng: 82.9739,
      accuracyMeters: 4.5,
      geofenceDistanceMeters: 18,
      siteCentroid: { lat: 25.3176, lng: 82.9739 },
      status: 'CONSISTENT',
      state: 'Uttar Pradesh',
      district: 'Varanasi',
      block: 'Pindra',
    },
    camera: {
      make: 'Vivo',
      model: 'V29 5G',
      software: 'Govt e-Pramaan Mobile Client v3.1.2',
      focalLength: '5.5mm (f/1.8)',
      iso: '150',
      exposure: '1/600s',
    },
    integrityScore: 89,
    riskLevel: 'LOW',
    auditStatus: 'APPROVED',
    reviewer: {
      assignedTo: 'Anand Swaroop (BSA Education Varanasi)',
      reviewedBy: 'Anand Swaroop (BSA Education Varanasi)',
      decisionDate: '2026-08-27T11:00:00+05:30',
      note: 'Before/After comparison verified. Structural roof screed, masonry plaster, and school exterior repainting completed to specification.',
    },
    fusionScores: {
      gps: 95,
      temporal: 94,
      duplicateRisk: 4,
      manipulationRisk: 6,
      claimMatch: 92,
      metadataIntegrity: 95,
      completeness: 100,
    },
    detectedAnomalies: [],
    similarEvidenceMatches: [],
    detectedObjects: [
      { label: 'school_building_exterior', confidence: 0.98, box: [0.15, 0.05, 0.95, 0.95] },
      { label: 'repaired_concrete_roof', confidence: 0.94, box: [0.10, 0.10, 0.40, 0.90] },
      { label: 'masonry_pillars', confidence: 0.91, box: [0.45, 0.30, 0.85, 0.85] },
    ],
    structuralChangeConfidence: 94,
    claimText: 'Completed concrete polymer structural screeding, crack injection, and elastomeric waterproof coating across school building roof.',
    modelVersion: 'eiil-vision-v2.4-school',
  },

  // Item 4: Solar Plant Installation (PRJ-KUSUM-KA-204)
  {
    id: 'EVD-2026-6190',
    projectId: 'PRJ-KUSUM-KA-204',
    projectName: 'PM-KUSUM Component-C Feeder Level Solarization (500 kW Plant)',
    scheme: 'PM-KUSUM (Solar)',
    ministry: 'Ministry of New and Renewable Energy',
    activityName: 'Module Mounting Structure Installation',
    stage: 'after',
    title: 'Galvanized Steel Mounting Racks & Solar Inverter Connection Grounding',
    imageUrl: '/images/projects/solar-plant.jpg',
    mimeType: 'image/jpeg',
    sizeBytes: 2980100,
    sha256: '44a80291e019280cdb9012a9e8802914109823ae8910012e882910baef091a22',
    capturedAt: '2026-08-24T16:10:30+05:30',
    uploadedAt: '2026-08-24T16:18:40+05:30',
    location: {
      lat: 13.2612,
      lng: 76.4820,
      accuracyMeters: 6.0,
      geofenceDistanceMeters: 485,
      siteCentroid: { lat: 13.2577, lng: 76.4789 },
      status: 'DEVIATION',
      state: 'Karnataka',
      district: 'Tumakuru',
      block: 'Tiptur',
    },
    camera: {
      make: 'OnePlus',
      model: 'Nord CE 3 Lite',
      software: 'OxygenOS v14.0',
      focalLength: '5.2mm (f/1.7)',
      iso: '80',
      exposure: '1/1000s',
    },
    integrityScore: 62,
    riskLevel: 'MEDIUM',
    auditStatus: 'PENDING',
    reviewer: {
      assignedTo: 'Nagaraj Swamy (AEE KREDL)',
    },
    fusionScores: {
      gps: 55,
      temporal: 92,
      duplicateRisk: 5,
      manipulationRisk: 8,
      claimMatch: 88,
      metadataIntegrity: 90,
      completeness: 85,
    },
    detectedAnomalies: [
      {
        id: 'ANOM-05',
        type: 'LOCATION_MISMATCH',
        severity: 'MEDIUM',
        confidence: 82.0,
        title: 'Geofence Boundary Deviation (485m Outside Registered Center)',
        description: 'The capture location is 485 metres from the registered survey plot center (sanctioned radius: 120m). May indicate an adjacent agricultural parcel or updated feeder substation alignment.',
        supportingData: 'Target Boundary: 120m radius. Deviation: +365m. Direction: North-East 42°',
      },
    ],
    similarEvidenceMatches: [],
    detectedObjects: [
      { label: 'solar_mounting_structure', confidence: 0.97, box: [0.20, 0.10, 0.85, 0.90] },
      { label: 'solar_pv_panels', confidence: 0.92, box: [0.15, 0.15, 0.80, 0.85] },
    ],
    claimText: 'Completed mounting of 24 galvanized heavy-gauge mounting tables with hot-dip zinc coating and surge arrestor earthing pit.',
    modelVersion: 'eiil-vision-v2.4-solar',
  },

  // Item 5: Ashram School Solar Street Lights (PRJ-SSA-OD-309)
  {
    id: 'EVD-2026-5509',
    projectId: 'PRJ-SSA-OD-309',
    projectName: 'Model Tribal Residential Ashram School Solar Street Lighting & Campus Security',
    scheme: 'Samagra Shiksha Abhiyan',
    ministry: 'Ministry of Education & Tribal Affairs',
    activityName: 'Solar Pole Erection & Luminaires Fixture',
    stage: 'after',
    title: 'Completed Installation of Solar Campus LED Street Luminaires',
    imageUrl: '/images/projects/school-solar-lights.jpg',
    mimeType: 'image/jpeg',
    sizeBytes: 2540000,
    sha256: '55bc9018283901abcf8192019283019283019283019283019283019283019283',
    capturedAt: '2026-08-26T15:40:00+05:30',
    uploadedAt: '2026-08-26T15:52:19+05:30',
    location: {
      lat: 21.9348,
      lng: 86.7416,
      accuracyMeters: 5.0,
      geofenceDistanceMeters: 45,
      siteCentroid: { lat: 21.9345, lng: 86.7412 },
      status: 'CONSISTENT',
      state: 'Odisha',
      district: 'Mayurbhanj',
      block: 'Baripada',
    },
    camera: {
      make: 'Realme',
      model: '11 Pro 5G',
      software: 'Realme UI v4.0',
      focalLength: '4.7mm (f/1.8)',
      iso: '120',
      exposure: '1/750s',
    },
    integrityScore: 84,
    riskLevel: 'LOW',
    auditStatus: 'APPROVED',
    reviewer: {
      assignedTo: 'Debasish Mohapatra (DEO Mayurbhanj)',
    },
    fusionScores: {
      gps: 94,
      temporal: 90,
      duplicateRisk: 4,
      manipulationRisk: 10,
      claimMatch: 88,
      metadataIntegrity: 88,
      completeness: 85,
    },
    detectedAnomalies: [],
    similarEvidenceMatches: [],
    detectedObjects: [
      { label: 'solar_street_light', confidence: 0.98, box: [0.10, 0.20, 0.90, 0.80] },
      { label: 'pv_panel_pole', confidence: 0.91, box: [0.10, 0.30, 0.45, 0.70] },
    ],
    claimText: 'Erected standalone 6-meter galvanized octagonal poles with integrated 40W Lumileds LED and 60Ah LiFePO4 battery pack.',
    modelVersion: 'eiil-vision-v2.4-solar',
  },

  // Item 6: Brahmaputra Embankment Approach Road (PRJ-PMGSY-AS-198)
  {
    id: 'EVD-2026-4402',
    projectId: 'PRJ-PMGSY-AS-198',
    projectName: 'Brahmaputra Flood-Resilient Embankment Approach Road (Ch. 12+200)',
    scheme: 'PMGSY (Rural Roads)',
    ministry: 'Ministry of Rural Development',
    activityName: 'Slope Embankment Stabilization',
    stage: 'during',
    title: 'Geo-synthetic Woven Mattress Laying on River Embankment Slope',
    imageUrl: '/images/projects/embankment-road.jpg',
    mimeType: 'image/jpeg',
    sizeBytes: 3410200,
    sha256: '2288001199a00cdb019280cdb9012a9e8802914109823ae8910012e882910bb3',
    capturedAt: '2026-08-23T11:15:20+05:30',
    uploadedAt: '2026-08-23T11:30:10+05:30',
    location: {
      lat: 26.2486,
      lng: 91.5222,
      accuracyMeters: 7.2,
      geofenceDistanceMeters: 55,
      siteCentroid: { lat: 26.2483, lng: 91.5218 },
      status: 'CONSISTENT',
      state: 'Assam',
      district: 'Kamrup',
      block: 'Hajo',
    },
    camera: {
      make: 'Motorola',
      model: 'Edge 40 Neo',
      software: 'Android 14 Cam',
      focalLength: '5.0mm (f/1.8)',
      iso: '100',
      exposure: '1/900s',
    },
    integrityScore: 78,
    riskLevel: 'LOW',
    auditStatus: 'APPROVED',
    reviewer: {
      assignedTo: 'Bhaskar Jyoti Barua (EE PWD Assam)',
    },
    fusionScores: {
      gps: 92,
      temporal: 85,
      duplicateRisk: 6,
      manipulationRisk: 8,
      claimMatch: 84,
      metadataIntegrity: 92,
      completeness: 80,
    },
    detectedAnomalies: [],
    similarEvidenceMatches: [],
    detectedObjects: [
      { label: 'river_embankment', confidence: 0.95, box: [0.15, 0.05, 0.95, 0.95] },
      { label: 'flood_approach_road', confidence: 0.91, box: [0.40, 0.20, 0.85, 0.80] },
    ],
    claimText: 'Laid 3200 sq.m of 400 GSM high-tenacity polypropylene woven geotextile fabric anchored on river embankment slope.',
    modelVersion: 'eiil-vision-v2.4-pmgsy',
  },
];

// 3. Audit Trail Event Ledger
export const MOCK_AUDIT_EVENTS: AuditEvent[] = [
  {
    id: 'AUD-9901',
    evidenceId: 'EVD-2026-9041',
    projectId: 'PRJ-JJM-RJ-108',
    actorName: 'EIIL-Fusion-Engine-v2.4',
    actorRole: 'AI Automated Auditor',
    action: 'FLAG_CRITICAL',
    previousState: 'RAW_INGESTED',
    newState: 'FLAGGED_CRITICAL',
    reason: 'Detected 94.7% perceptual & vector embedding similarity with historical record EVD-2025-1832 (Jodhpur district). High fraud risk.',
    sha256Hash: 'a8910bc47289012a9e8802914109823ae8910012e882910baef091a2244a8029',
    timestamp: '2026-08-25T11:45:12+05:30',
  },
  {
    id: 'AUD-9902',
    evidenceId: 'EVD-2026-7734',
    projectId: 'PRJ-SSA-UP-512',
    actorName: 'Anand Swaroop (BSA Education)',
    actorRole: 'Evidence Reviewer',
    action: 'APPROVE',
    previousState: 'UNDER_AUDIT',
    newState: 'APPROVED',
    reason: 'Before / After image structural verification confirmed complete roof screeding and masonry restoration.',
    sha256Hash: 'bc47289012a9e8802914109823ae8910012e882910baef091a2244a8029a8910',
    timestamp: '2026-08-27T11:00:00+05:30',
  },
  {
    id: 'AUD-9903',
    evidenceId: 'EVD-2026-8812',
    projectId: 'PRJ-PMGSY-MH-401',
    actorName: 'Rajesh Kulkarni (SE PWD)',
    actorRole: 'Evidence Reviewer',
    action: 'APPROVE',
    previousState: 'PENDING_REVIEW',
    newState: 'APPROVED',
    reason: 'Survey photograph corroborated against geofence boundary.',
    sha256Hash: '1102948caef198302bf029aa3c19e59d997a02c841bb28ff8390ab914028ce82',
    timestamp: '2026-08-21T10:15:00+05:30',
  },
];
