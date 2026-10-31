# PRISM: Proof-of-Action System

**Evidence Integrity and Intelligence Layer (EIIL)**

PRISM is an evidence verification and review platform designed to improve the reliability, traceability, and accountability of field evidence submitted for public infrastructure projects and government schemes.

The platform combines a React frontend with a FastAPI backend and supporting data services to validate evidence, identify potential anomalies, support human review, and maintain an auditable record of decisions.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Frontend: React 19](https://img.shields.io/badge/Frontend-React%2019%20%2B%20Vite-61dafb.svg)](frontend/)
[![Backend: FastAPI](https://img.shields.io/badge/Backend-FastAPI%20%2B%20Python-009688.svg)](openapi.json)

---

## Table of Contents

- [Overview](#overview)
- [Core Features](#core-features)
- [System Architecture](#system-architecture)
- [Backend Architecture](#backend-architecture)
- [Evidence Verification Pipeline](#evidence-verification-pipeline)
- [Authentication and Access Control](#authentication-and-access-control)
- [Database and Storage](#database-and-storage)
- [Background Processing](#background-processing)
- [Frontend Portals](#frontend-portals)
- [Technology Stack](#technology-stack)
- [Getting Started](#getting-started)
- [API Documentation](#api-documentation)
- [Testing](#testing)
- [Deployment](#deployment)
- [Repository Structure](#repository-structure)
- [Security Considerations](#security-considerations)
- [Contributing](#contributing)
- [License](#license)

---

## Overview

PRISM provides a structured workflow for collecting, verifying, reviewing, and auditing photographic and related field evidence.

Its verification process combines cryptographic hashing, image similarity checks, metadata validation, geospatial checks, and temporal consistency analysis. These signals help reviewers identify suspicious submissions and understand why evidence may require further investigation.

### Design Principles

- **Evidence integrity:** Detect changes to evidence using cryptographic hashes.
- **Explainable verification:** Keep evidence-quality issues distinct from potential fraud indicators.
- **Traceability:** Maintain records of important system actions and review decisions.
- **Controlled access:** Restrict protected operations according to user roles and permissions.
- **Scalable processing:** Separate API requests from background analysis and service tasks.
- **Review accountability:** Support human assessment of automated verification results.

---

## Core Features

### 1. Evidence Ingestion and Verification

- Accept evidence through the application workflow.
- Calculate SHA-256 hashes to establish file identity.
- Extract available image metadata, including EXIF information.
- Apply image fingerprinting techniques to identify potential duplicates.
- Associate submissions with relevant projects and evidence records.
- Preserve verification results for subsequent review.

### 2. Duplicate and Similarity Detection

- Use perceptual hashing techniques, including pHash and difference hashing where implemented.
- Identify potentially similar images across submissions.
- Support investigation of repeated evidence across projects or reporting periods.
- Provide similarity indicators to assist reviewers.

Similarity matches are indicators for investigation, not automatic proof of fraud.

### 3. Geospatial and Temporal Validation

- Validate available location data against configured project boundaries.
- Support point-in-polygon geofence checks where the required geospatial configuration is available.
- Evaluate timestamps and location consistency.
- Identify potentially implausible travel between evidence submissions.
- Flag missing, inconsistent, or suspicious metadata for further review.

### 4. Integrity and Fraud-Risk Assessment

PRISM distinguishes between evidence completeness and potential manipulation.

- **Integrity assessment:** Evaluates the availability and consistency of evidence attributes.
- **Fraud-risk assessment:** Combines configured verification signals to identify submissions that may require investigation.
- **Review support:** Makes verification findings available to authorized reviewers.
- **Decision traceability:** Supports recording review outcomes and related actions.

Risk indicators should support human review rather than serve as standalone proof of wrongdoing.

### 5. Tamper-Evident Audit Records

- Record important application and review activities.
- Support append-only audit records with hash-link verification where configured.
- Help identify changes to previously recorded audit entries.
- Preserve a traceable history of relevant actions and decisions.

### 6. Project and Evidence Management

- Maintain project and milestone information.
- Associate evidence with relevant project records.
- Filter evidence by available status, integrity, and risk attributes.
- Support detailed evidence inspection and review workflows.

### 7. Search and Evidence Relationships

- Search across supported evidence and project attributes.
- Explore relationships between projects, milestones, contractors, and submissions.
- Support CSV and JSON export through the relevant application functionality.

### 8. Reviewer and Auditor Workflows

- Provide a review queue for evidence requiring attention.
- Support side-by-side image inspection and metadata comparison.
- Allow authorized reviewers to record decisions.
- Provide audit-oriented views for compliance and investigation workflows.

---

## System Architecture

```text
┌───────────────────────────────────────────────────────────────┐
│                       Frontend Layer                           │
│                 React 19 + Vite + PWA                          │
│      Citizen Portal | Reviewer | Auditor | Administration      │
└──────────────────────────────┬────────────────────────────────┘
                               │
                         JSON / REST API
                               │
┌──────────────────────────────▼────────────────────────────────┐
│                     FastAPI Backend                            │
│                                                               │
│  API Routes | Authentication | Authorization | Validation     │
│  Evidence Services | Project Services | Audit Services         │
└───────────────┬─────────────────┬────────────────┬─────────────┘
                │                 │                │
                ▼                 ▼                ▼
       ┌────────────────┐ ┌──────────────┐ ┌──────────────────┐
       │ PostgreSQL     │ │ Redis        │ │ MinIO / S3       │
       │                │ │              │ │                  │
       │ Application    │ │ Caching and  │ │ Evidence files   │
       │ records        │ │ task support │ │ and objects      │
       └────────────────┘ └──────┬───────┘ └──────────────────┘
                                 │
                                 ▼
                     ┌────────────────────────┐
                     │ Background Workers     │
                     │                        │
                     │ Evidence analysis      │
                     │ Webhooks               │
                     │ Notifications          │
                     │ Retention tasks        │
                     └────────────────────────┘
```

The architecture separates request handling, persistent records, object storage, and asynchronous processing. The exact services enabled depend on the deployment configuration.

---

## Backend Architecture

The backend is built with FastAPI and Python. It exposes application functionality through HTTP APIs and coordinates evidence verification, data persistence, authorization, and supporting background services.

### API Layer

- REST API endpoints for application operations.
- Request validation and structured responses.
- OpenAPI schema generation.
- Interactive API documentation through Swagger UI and ReDoc when enabled.
- Health and readiness endpoints for service monitoring.

### Authentication and Authorization

- OpenID Connect (OIDC) integration where configured.
- Role-based access control (RBAC).
- Permission-based authorization for protected operations.
- Support for administrative, review, and audit workflows according to assigned permissions.
- Authentication configuration designed to be environment-specific.

### Evidence Processing Services

- SHA-256 file hashing.
- Image fingerprinting and duplicate analysis.
- Metadata validation.
- Geospatial and temporal consistency checks where configured.
- Integrity and fraud-risk signal processing.
- Persistence of verification results for review.

### Audit and Governance Services

- Audit records for relevant application actions.
- Tamper-evident hash verification where implemented.
- Review-decision traceability.
- Permission-controlled access to protected audit operations.

### Database Migration Management

Database schema changes are managed using Alembic migrations.

Typical migration command:

```bash
alembic upgrade head
```

Run migrations only after verifying the target environment, reviewing the migration changes, and creating an appropriate database backup.

### Service Health

The backend can expose health and readiness endpoints, depending on the deployed application configuration.

Typical checks:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

These commands assume the application exposes those routes in the current deployment.

---

## Evidence Verification Pipeline

A typical evidence-processing workflow follows these stages:

```text
Evidence Submission
        |
        ▼
Input Validation
        |
        ▼
File Identity and SHA-256 Hashing
        |
        ▼
Metadata and EXIF Inspection
        |
        ▼
Image Similarity and Duplicate Checks
        |
        ▼
Geospatial and Temporal Validation
        |
        ▼
Integrity and Risk Assessment
        |
        ▼
Evidence Record and Audit Updates
        |
        ▼
Reviewer Inspection and Decision
```

The checks performed depend on the evidence type, available metadata, project configuration, and enabled backend services.

A missing GPS coordinate or timestamp does not automatically establish fraud. Likewise, a duplicate match or risk score should be interpreted in context.

---

## Authentication and Access Control

PRISM supports role-based workflows for different classes of users.

| Role | Responsibilities |
|---|---|
| Administrator | User and permission administration, system configuration, and operational oversight |
| Reviewer | Evidence inspection, case review, and decision recording |
| Auditor | Compliance review, audit inspection, and cross-project oversight |
| Citizen or Submitter | Evidence submission and access to permitted project information |

The actions available to each role depend on the permissions assigned by the backend.

### Authentication Considerations

- Configure trusted identity providers through environment-specific settings.
- Validate identity tokens and issuer, audience, and signature requirements when using OIDC.
- Enforce authorization checks on protected backend endpoints.
- Apply appropriate session and token-handling practices.
- Use HTTPS for deployed environments.
- Never commit credentials, private keys, or production environment files to version control.

Two-factor authentication, citizen OTP login, and specific identity-provider flows should be enabled only where the corresponding implementation and configuration are available.

---

## Database and Storage

### PostgreSQL

PostgreSQL stores structured application data, such as project information, evidence records, review information, and other supported backend entities.

### PostGIS

PostGIS can support spatial queries and project-boundary validation when installed and configured in the target environment.

### Redis

Redis provides supporting infrastructure for caching and background task coordination where enabled.

### MinIO and S3-Compatible Storage

Object storage can be used to hold uploaded evidence and other file artifacts separately from structured database records.

### Data Management Principles

- Keep structured records separate from binary evidence objects.
- Validate evidence before processing.
- Restrict access to stored files and sensitive metadata.
- Define retention and deletion policies explicitly.
- Back up database records and object storage according to operational requirements.
- Test recovery procedures before relying on backups.

The exact storage configuration is deployment-dependent.

---

## Background Processing

Background workers allow longer-running tasks to execute independently of normal API requests.

The deployment may include separate workers for:

| Worker | Purpose |
|---|---|
| Evidence analysis | Runs configured verification and analysis tasks |
| Webhook processing | Handles configured outbound or event-driven integrations |
| Notifications | Processes supported notification tasks |
| Retention processing | Executes configured data-retention operations |

Worker availability depends on the active deployment configuration. Tasks that require external services may need additional credentials and connectivity.

---

## Frontend Portals

The React frontend provides role-oriented workflows for evidence submission, inspection, and administration.

| Route | Intended Role | Purpose |
|---|---|---|
| `/login` | Public | Authentication entry point |
| `/dashboard` | Authorized users | Overview of available project and evidence information |
| `/projects` | Authorized users | Project directory and milestone tracking |
| `/projects/create` | Authorized users with appropriate permissions | Project creation and configuration |
| `/evidence` | Authorized users | Evidence repository and filtering |
| `/evidence/upload` | Authorized submitters | Evidence submission |
| `/evidence/:id` | Authorized users | Evidence details and verification results |
| `/reviews` | Reviewers | Review queue |
| `/review/case` | Reviewers | Evidence inspection and decision workflow |
| `/auditor` | Auditors | Compliance and audit views |
| `/graph` | Authorized users | Evidence relationship visualization |
| `/search` | Authorized users | Search and supported export workflows |
| `/admin` | Administrators | Administrative controls |

Routes listed here describe the intended frontend navigation. Actual route availability and permissions depend on the current implementation and backend authorization rules.

---

## Technology Stack

| Component | Technology |
|---|---|
| Frontend | React 19 |
| Frontend tooling | Vite |
| Backend framework | FastAPI |
| Backend language | Python |
| API specification | OpenAPI |
| Relational database | PostgreSQL |
| Geospatial queries | PostGIS, where configured |
| Cache and task infrastructure | Redis |
| Object storage | MinIO / S3-compatible storage |
| Database migrations | Alembic |
| API server | Uvicorn |
| Containerization | Docker and Docker Compose, where configured |
| Identity | OIDC, where configured |

---

## Getting Started

### Prerequisites

- Node.js 18 or later; Node.js 20 or later is recommended.
- npm 9 or later.
- Python 3.11 or later for backend development.
- PostgreSQL and any additional required services.
- Docker and Docker Compose if using a containerized setup.

Verify the versions installed on your system before starting.

### Clone the Repository

```bash
git clone https://github.com/AnujRAuti/PRISM.git
cd PRISM
```

### Frontend Setup

```bash
cd frontend
npm install
```

Create the local environment file from the provided example, if available:

```bash
cp .env.example .env
```

Configure the frontend API endpoint and any required application settings in `.env`.

Example:

```env
VITE_API_BASE_URL=http://localhost:8000/api/v1
VITE_APP_NAME=PRISM
VITE_ENVIRONMENT=development
```

Use the API prefix configured by the backend. The example above must be adjusted if the current application uses a different route prefix.

Start the development server:

```bash
npm run dev
```

Run the available frontend tests and production build:

```bash
npm test
npm run build
```

### Backend Setup

Return to the repository root before running backend commands.

Create and activate a virtual environment:

```bash
python -m venv .venv
```

On Linux or macOS:

```bash
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Install the backend dependencies using the dependency file supplied by the repository. If `requirements.txt` is present:

```bash
pip install -r requirements.txt
```

Configure the required database, storage, authentication, and service environment variables before starting the backend.

Apply database migrations:

```bash
alembic upgrade head
```

Start the API server using the application's configured import path. For example, if the entry point is `backend.app.main:app`:

```bash
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

The import path and migration configuration should be confirmed against the current repository before running these commands.

---

## API Documentation

FastAPI can generate an OpenAPI schema and interactive documentation for registered routes.

When enabled, the usual local endpoints are:

| Resource | Path |
|---|---|
| Swagger UI | `/docs` |
| ReDoc | `/redoc` |
| OpenAPI schema | `/openapi.json` |

For a local server on port 8000, the Swagger UI is typically available at:

```text
http://localhost:8000/docs
```

The repository also includes an `openapi.json` file. Check whether it is regenerated from the current backend before treating it as the definitive API contract.

---

## Testing

PRISM should be tested at the unit, integration, and application levels.

Recommended coverage areas include:

- Authentication and authorization.
- Role and permission enforcement.
- Evidence ingestion and input validation.
- SHA-256 hashing and file identity.
- Image similarity and duplicate detection.
- Metadata and geospatial validation.
- Integrity and risk assessment.
- Audit record creation and verification.
- Database migrations and persistence.
- Background task execution.
- Health and readiness endpoints.
- Frontend build and route behavior.

Run the test commands configured in the repository. For a Python project using pytest, the command is typically:

```bash
pytest
```

For the frontend:

```bash
cd frontend
npm test
npm run build
```

Test results depend on the current source revision, environment, and external services. Run the suite against the version being released and report the actual results rather than relying on historical results.

---

## Deployment

PRISM can be deployed using containerized services or a separately managed application environment, depending on the deployment configuration.

### Deployment Components

A full deployment may include:

- FastAPI application.
- PostgreSQL database.
- Redis.
- MinIO or another S3-compatible object store.
- Background workers.
- React frontend.
- Reverse proxy and HTTPS termination.
- Monitoring, logging, and backup services.

### Production Checklist

Before releasing a version:

- [ ] Configure production environment variables.
- [ ] Use HTTPS for externally accessible services.
- [ ] Configure trusted identity-provider settings.
- [ ] Verify backend authorization rules.
- [ ] Configure the frontend's production API URL.
- [ ] Set the permitted CORS origins.
- [ ] Verify database connectivity and migration state.
- [ ] Verify object storage access and permissions.
- [ ] Verify background workers and task queues.
- [ ] Run automated tests against the release candidate.
- [ ] Back up the database and evidence objects.
- [ ] Test backup restoration.
- [ ] Confirm health and readiness checks.
- [ ] Review logs for errors and sensitive information.
- [ ] Confirm monitoring and incident-response procedures.

Do not run destructive database, volume, or storage commands against production without an approved backup and recovery plan.

---

## Repository Structure

The following structure reflects the main areas described by the project. Some backend paths may differ in the current checkout.

```text
PRISM/
├── docs/
│   ├── Production Task Files/
│   └── Proof-of-Action Backend — TODO.md
├── frontend/
│   ├── public/
│   │   ├── manifest.webmanifest
│   │   └── sw.js
│   ├── src/
│   │   ├── components/
│   │   ├── context/
│   │   ├── lib/
│   │   ├── pages/
│   │   └── services/
│   ├── tests/
│   ├── package.json
│   └── vite.config.js
├── backend/
│   └── app/
│       └── main.py
├── openapi.json
└── README.md
```

Verify this tree against the current repository before adding paths that do not exist.

---

## Security Considerations

PRISM handles evidence that may contain sensitive location, device, project, or personal information. Security must be enforced in both the frontend and backend.

- Enforce authorization on the server, not only through hidden frontend routes.
- Validate incoming data and uploaded files.
- Protect credentials and tokens from logs and source control.
- Restrict database and object-storage access.
- Apply appropriate metadata minimization and privacy controls.
- Use HTTPS in production.
- Keep dependencies and base images updated.
- Monitor application and worker failures.
- Review audit integrity and access logs.
- Establish explicit retention and backup policies.

A badge or documented control should not be treated as proof of compliance without verification against the implemented system and its deployment.

---

## License

This project is distributed under the MIT License if the repository's `LICENSE` file specifies those terms. See [LICENSE](LICENSE) for the applicable license text.
