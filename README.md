# 🌐 PRISM — Proof-of-Action System

> **Evidence Integrity & Intelligence Layer (EIIL)**  
> Next-generation forensic verification, duplicate detection, and review platform for field evidence in public infrastructure projects and government schemes.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Frontend: React 19](https://img.shields.io/badge/Frontend-React%2019%20%2B%20Vite-61dafb.svg)](frontend/)
[![Backend: FastAPI](https://img.shields.io/badge/Backend-FastAPI%20%2B%20Python-009688.svg)](openapi.json)
[![Compliance: WCAG 2.1 AA](https://img.shields.io/badge/Accessibility-WCAG%202.1%20AA-success.svg)](frontend/)
[![PWA: Offline Ready](https://img.shields.io/badge/PWA-Offline%20Ready-orange.svg)](frontend/public/manifest.webmanifest)

---

## 📌 Overview

**PRISM** is an open-standard, cryptographically verified Evidence Integrity & Intelligence Layer engineered to monitor photographic and sensor evidence across major civil infrastructure programs (*Pradhan Mantri Gram Sadak Yojana*, *Jal Jeevan Mission*, *National Solar Mission*, and urban renewal initiatives).

Rather than relying on opaque AI predictions, PRISM implements a **multi-signal forensic verification pipeline**:

1. **Cryptographic Identity:** SHA-256 hashing computed at ingestion to guarantee tamper-evident authenticity.
2. **Perceptual Fingerprinting:** Difference & perceptual hashing (pHash) to detect duplicate images across distinct projects and dates.
3. **Geospatial & Spatiotemporal Fusion:** Point-in-polygon geofencing against approved project boundaries, combined with impossible travel velocity checks (speed-of-light & transit velocity limits).
4. **EXIF & Sensor Telemetry Validation:** Device fingerprinting, camera make/model correlation, GPS dilution of precision (DOP), and software modification detection.
5. **Separation of Integrity & Fraud Risk:** Clear explainability distinguishing missing data (Integrity Score) from malicious manipulation (Fraud Risk Score).
6. **Immutable Audit Ledger:** Append-only chain-hashed audit records with verifiable integrity for anti-corruption compliance.

---

## 🏛️ System Architecture

```text
┌────────────────────────────────────────────────────────────────────────┐
│                        PRISM Presentation Layer                        │
│  React 19 • Vite • GovTech Design System • WCAG 2.1 AA • PWA (Offline) │
└────────────────────────────────────┬───────────────────────────────────┘
                                     │ JSON / REST API (OpenAPI 3.1)
                                     ▼
┌────────────────────────────────────────────────────────────────────────┐
│                      FastAPI Ingestion & API Gateway                   │
│         OIDC Identity Provider • Role-Based Access Control (RBAC)      │
└──────────┬─────────────────────────┬─────────────────────────┬─────────┘
           │                         │                         │
           ▼                         ▼                         ▼
┌──────────────────────┐  ┌──────────────────────┐  ┌────────────────────┐
│   Forensic Pipeline  │  │   PostgreSQL + GIS   │  │   MinIO / S3 Store │
│ • SHA-256 Hashing    │  │ • Evidence Registry  │  │ • Encrypted Photos │
│ • pHash Duplication  │  │ • PostGIS Geofencing │  │ • Raw Sensor Logs  │
│ • Impossible Travel  │  │ • Immutable Audit Log│  │ • Evidence Dossiers│
│ • EXIF Sanitization  │  │ • Vector Similarity  │  │ • Derived Crops    │
└──────────────────────┘  └──────────────────────┘  └────────────────────┘
```

---

## ✨ Key Features

### 1. Multi-Role RBAC & Specialized Portals
- **Auditor Portal (`/auditor`):** High-level compliance oversight, cross-project anomaly analytics, and ledger verification.
- **Reviewer PWA Workspace (`/reviews`, `/review/case`):** Mobile-first offline inspection canvas, side-by-side photo comparison, split-screen EXIF analysis, and decision logging.
- **Citizen Portal (`/citizen`):** Public transparency tracking, project progress visualization, and community evidence submission.
- **Admin Control Plane (`/admin`):** User provisioning, forensic rule weighting, system health metrics, and tamper detection audits.

### 2. Dual-Channel Secure Authentication
- **Officials & Reviewers:** Departmental login with mandatory Two-Factor Authentication (2FA), Time-Based One-Time Password (TOTP) enforcement, and TLS verification.
- **Citizens:** Lightweight OTP / Email authentication with instant verification and anonymous submission options.

### 3. Progressive Web App (PWA) & Offline Capability
- Offline evidence review queue and caching via Service Workers (`sw.js`).
- Mobile responsive off-canvas navigation drawer and quick-action toolbars.
- Device synchronization with automatic conflict resolution upon reconnection.

### 4. Interactive Evidence Graph & Search Workbench
- Interactive SVG network graph (`/graph`) mapping relationships between contractors, projects, milestones, and evidence.
- Full-text and geospatial multi-parameter search workbench (`/search`) with one-click export to CSV and JSON formats.

---

## 🚀 Quick Start Guide

### Prerequisites
- **Node.js:** v18.0.0 or higher (v20+ recommended)
- **npm:** v9.0.0 or higher
- **Python:** v3.11+ (if running backend services)
- **Docker & Docker Compose:** Optional, for full-stack containerized deployment

---

### Frontend Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/AnujRAuti/PRISM.git
   cd PRISM
   ```

2. **Navigate to the frontend directory:**
   ```bash
   cd frontend
   ```

3. **Install dependencies:**
   ```bash
   npm install
   ```

4. **Configure environment variables:**
   ```bash
   cp .env.example .env
   ```
   *Edit `.env` to configure your API endpoint and Supabase/OIDC keys:*
   ```env
   VITE_API_BASE_URL=http://localhost:8000/api/v1
   VITE_APP_NAME=PRISM
   VITE_ENVIRONMENT=development
   ```

5. **Start the local development server:**
   ```bash
   npm run dev
   ```
   Open your browser at **[http://localhost:5173](http://localhost:5173)**.

6. **Run tests & quality checks:**
   ```bash
   npm test
   npm run build
   ```

---

### Backend Setup (FastAPI & Services)

1. **Create and activate a virtual environment:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. **Install requirements:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run database migrations:**
   ```bash
   alembic upgrade head
   ```

4. **Start the API service:**
   ```bash
   uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
   ```
   API Swagger documentation will be accessible at **[http://localhost:8000/docs](http://localhost:8000/docs)**.

---

## 🗺️ Route Directory

| Route | Role | Description |
| :--- | :--- | :--- |
| `/login` | Public | Dual-option authentication (Official 2FA / Citizen login) |
| `/dashboard` | All Users | Executive metrics, scheme telemetry, and recent alerts |
| `/projects` | All Users | Geo-tagged infrastructure projects directory & milestone tracking |
| `/projects/create`| Admin/Auditor | Project wizard with geofence polygon boundary definition |
| `/evidence` | All Users | Evidence repository filtered by status, integrity, and risk |
| `/evidence/upload`| Citizen/Official | Multi-step evidence ingestion wizard with live EXIF extraction |
| `/evidence/:id` | All Users | Detailed forensic dossier, pHash matches, and travel velocity checks |
| `/reviews` | Reviewer | Priority case triage queue sorted by calculated fraud risk |
| `/review/case` | Reviewer (PWA)| Offline-capable review workspace with side-by-side inspection |
| `/auditor` | Auditor | High-level compliance audits and forensic reports |
| `/graph` | All Users | Dynamic node-link graph visualizing evidence relationships |
| `/search` | All Users | Multi-parameter search workbench with CSV/JSON export |
| `/admin` | Admin | Role management, tamper-evident audit ledger, and rule config |

---

## 🛡️ Security, Governance & Compliance

- **GovTech Design Standards:** Adheres to the Indian National Informatics Centre (NIC) guidelines, featuring a high-trust national palette (Deep Navy, Pure White, Gold highlights) and readable typography.
- **WCAG 2.1 AA Accessibility:** Full keyboard navigation, `aria-*` accessibility landmarks, screen reader accommodations, and `:focus-visible` styling.
- **Anti-Tampering:** Append-only cryptographic audit logging with parent-hash verification prevents retroactive record manipulation.
- **Data Privacy:** Automated stripping of sensitive PII from metadata; geofence redaction for sensitive installations.

---

## 📂 Repository Structure

```text
PRISM/
├── docs/                   # Architectural Decision Records (ADRs) & specs
│   ├── Production Task Files/
│   └── Proof-of-Action Backend — TODO.md
├── frontend/               # React 19 Frontend application
│   ├── public/             # PWA manifest, icons, and service worker
│   ├── src/
│   │   ├── components/     # Reusable UI & GovTech components
│   │   ├── context/        # Auth and global application state
│   │   ├── lib/            # Supabase, API client, and Zod schemas
│   │   ├── pages/          # Application routes (Reviewer, Auditor, Admin, etc.)
│   │   └── services/       # API integration services
│   ├── tests/              # Automated test suites
│   ├── package.json
│   └── vite.config.js
├── openapi.json            # Complete OpenAPI 3.1 REST API specification
└── README.md               # Project documentation
```

---

## 🤝 Contributing

Contributions to PRISM are welcome! Please follow these steps:

1. Fork the repository.
2. Create your feature branch (`git checkout -b feature/NewFeature`).
3. Commit your changes (`git commit -m "feat: implement NewFeature"`).
4. Push to the branch (`git push origin feature/NewFeature`).
5. Open a Pull Request detailing the changes made.

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
