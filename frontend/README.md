# Proof-of-Action (PoA) — Frontend

> **Evidence Integrity & Intelligence Layer (EIIL)**  
> Dedicated user interface for analyzing, verifying, and reviewing photographic field evidence submitted in public infrastructure and government scheme activities.

---

## 🏛️ System Overview & Design Philosophy

The Proof-of-Action frontend is designed to monitor evidence across major government schemes (*Pradhan Mantri Gram Sadak Yojana*, *Jal Jeevan Mission*, *Solar Energy Programme*, etc.).

Rather than relying on a single opaque AI model, the platform provides **multi-signal verification intelligence**:
- **Cryptographic Fingerprint:** SHA-256 byte-level identity.
- **Perceptual Fingerprint:** pHash visual similarity and cross-project duplicate detection.
- **Contextual Verification:** Geofence polygon boundary checks and timeline consistency.
- **Explainability:** Separate **Integrity** (completeness) and **Fraud Risk** ratings with plain-English anomaly explanations.
- **Aesthetics:** Adheres strictly to **Indian Government Web Standards** (WCAG 2.1 AA compliant, navy blue & cream palette, clear data tables, accessibility landmarks).

---

## 🚀 Getting Started

### Prerequisites
- Node.js `v18+` or `v20+` (tested on Node v26)
- npm `v9+`

### Installation
```bash
cd frontend
npm install
```

### Environment Configuration
The application reads configuration from `.env`:
```env
# API Configuration
VITE_API_BASE_URL=http://localhost:8000/api/v1

# Application Settings
VITE_APP_NAME=Proof-of-Action
VITE_APP_VERSION=1.0.0
VITE_ENVIRONMENT=development
```

### Development Server
```bash
npm run dev
```
Open your browser to: [http://localhost:5173](http://localhost:5173)

### Running Automated Tests
```bash
npm test
```
Executes the native test suite verifying formatters, validators, scoring formulas, and impossible travel algorithms.

### Production Build & Code Optimization
```bash
npm run build
```
Generates an optimized, code-split production bundle in `dist/`.

---

## 📱 Page & Route Directory

| Path | Component | Stage | Description |
| :--- | :--- | :--- | :--- |
| `/login` | `LoginForm` | **Stage 1** | Portal login with credential validation & session persistence |
| `/dashboard` | `Dashboard` | **Stage 1** | Key statistics, recent activities, notifications, and quick actions |
| `/projects` | `ProjectsList` | **Stage 1** | Paginated table of infrastructure projects with status badges |
| `/projects/create` | `CreateProject` | **Stage 1** | Project creation wizard with geofencing and state dropdown |
| `/projects/:id` | `ProjectDetail` | **Stage 1** | Milestone progress, activity timeline, and evidence ledger |
| `/evidence` | `EvidenceList` | **Stage 2** | Multi-filter evidence registry with integrity and risk tags |
| `/evidence/upload` | `UploadEvidence` | **Stage 2** | 4-step wizard linking evidence to project milestones |
| `/evidence/:id` | `EvidenceDetail` | **Stage 2/3** | Forensic dossier with multi-signal breakdown & anomaly alerts |
| `/reviews` | `ReviewQueue` | **Stage 2** | Priority review queue sorted by fraud risk severity |
| `/review/:id` | `ReviewInterface` | **Stage 2** | Side-by-side inspection canvas with reviewer decision actions |
| `/graph` | `EvidenceGraph` | **Stage 3** | Interactive SVG network graph & chronological timeline view |
| `/search` | `Search` | **Stage 3** | Multi-parameter search workbench with direct CSV/JSON export |
| `/admin` | `AdminDashboard` | **Stage 3** | User RBAC, Immutable audit log viewer, & Rule configuration |
| `/profile` | `Profile` | **Stage 2** | Operator identity, permissions, and departmental credentials |

---

## ⚡ Performance & Bundle Optimization (Stage 4)

- **Route-Based Code Splitting:** Every page is dynamically loaded via `React.lazy()` and wrapped in `<Suspense fallback={<LoadingFallback />}>`.
- **Manual Rollup Chunking:** Configured via `vite.config.js`:
  - `react-core` (`react`, `react-dom`): Cached core bundle.
  - `react-router` (`react-router-dom`): Router bundle.
  - `network` (`axios`): Networking layer.
  - On-demand page chunks: Each route bundle is between **2 kB and 30 kB**.
  - Initial entry chunk reduced to **< 20 kB** (< 5 kB gzipped).

---

## ♿ Accessibility (WCAG 2.1 AA Compliance)

- **Keyboard Navigation:** Full support for Tab/Shift-Tab with high-contrast `:focus-visible` outlines.
- **Skip to Content:** Keyboard users can press Tab to reveal the *"Skip to main content"* link bypassing top navigation.
- **Screen Reader Support:** Semantic HTML5 landmarks (`<header role="banner">`, `<aside aria-label="Portal Navigation">`, `<main id="main-content">`, `<footer role="contentinfo">`).
- **Contrast Ratios:** Text and UI elements maintain contrast ratios exceeding 4.5:1 on light and dark backgrounds.
- **Reduced Motion:** Supports `@media (prefers-reduced-motion: reduce)` to disable non-essential animations.

---

## 🧪 Testing Suite

Tests are situated in `tests/`:
- `tests/helpers.test.js`: Validates dates, file sizes, role labels, states list, and RFC email syntax.
- `tests/fusion-rules.test.js`: Validates multi-signal fusion weighting and impossible travel velocity detection.

Run via:
```bash
npm test
```
