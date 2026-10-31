# PRISM (Proof-of-Action): Development & PWA Plan

> [!NOTE]
> Active 48-Hour Release Roadmap: See [pwa-plan.md](file:///home/adarsh/Documents/College%20Things/Prism/docs/pwa-plan.md) for the official PoA Progressive Web App (PWA) Implementation & Reviewer Journey Plan.

## 🎯 **PROGRESS UPDATE - Stages 1, 2, 3, 4 & 5 Complete** (Production Ready)

### ✅ **What's Been Completed in Stage 5 (PRISM Rebranding, Authentic Logo & Loading Splash):**
- ✅ **Authentic Brand Emblem Integration**: Replaced synthetic placeholder with the user's authentic PRISM crystal emblem (`prism-symbol-transparent.png`), featuring the faceted triangular prism letterform with cyan-to-purple-to-magenta spectral gradient.
- ✅ **Minimalist Modern Loading Animation (`<LoadingSplash />`)**:
  - Distraction-free, automatic loading experience matching the website's clean GovTech canvas (`#f8fafc`).
  - Contains strictly the authentic PRISM crystal emblem and the animated "PRISM" wordmark.
  - Removed all manual buttons, skip prompts, progress bars, and ticker text for a clean cinematic sequence.
  - **Letter-by-Letter Multilingual Assembly**:
    - Each of the 5 character positions scrambles rapidly through official Indian scripts (Devanagari, Bengali, Telugu, Tamil, Gurmukhi, Odia, Gujarati, Kannada, Malayalam).
    - In a staggered sequence (`t=550ms` to `1750ms`), each position locks with a punchy micro-pop into English: `P` ➔ `R` ➔ `I` ➔ `S` ➔ `M`.
    - Once the full word **PRISM** completes in English, a chromatic spectral refraction sweep illuminates the letters in sync with an emblem halo pulse.
    - Automatically dissolves smoothly into the platform (`opacity: 0`, 500ms fade).
- ✅ **Layout Measurements & Grid Alignment**:
  - Fixed misaligned shell layout: converted Header to full-width (`width: 100%, height: 64px, padding: 0 1.5rem`), aligning the PRISM brand emblem with the left docked Sidebar.
  - Eliminated conflicting `maxWidth: 1400px / 1440px` and `margin: 0 auto` across pages (`Dashboard`, `Search`, `Projects`, `Evidence`, `Reviews`, `Graph`, `Admin`), giving the entire content area consistent, responsive padding (`padding: 1.75rem 2rem`) with exact grid alignment.
  - Repositioned `Footer` inside scrollable `main` with `minWidth: 0`, preventing table blowouts and ensuring the sidebar stays cleanly pinned from top to bottom.
- ✅ **Clean Human Design (Removed "AI Slop" Green Boxes & Tacky Badges)**:
  - **Root Cause Layout Fix**: Discovered Vite's starter template in `index.css` had `#root { width: 1126px; margin: 0 auto; text-align: center; border-inline: 1px solid var(--border); }`. Rewrote `index.css` from scratch to full responsive width `100%`, border-box sizing, and clean typography, fixing the misaligned layout measurements across the entire application.
  - Removed tacky neon green `● EIIL Engine Active` pill box from the header.
  - Removed loud `Susasan` tag boxes and arbitrary numeric badges from sidebar navigation items; converted review counters to understated neutral pills (`#f1f5f9 / #64748b`).
  - Removed tacky bottom "Good Governance" emoji banner from the sidebar and replaced it with a discreet, professional system version indicator.
  - Modernized `Dashboard.jsx` cards: abolished harsh yellow/cream containers, solid dark blue bars, and white-on-white text; replaced with crisp white cards (`#ffffff`, border `#e2e8f0`, subtle drop shadows) and high-contrast typography.
  - Removed green badge box `🏛️ Susasan E-Citizen Charter` from the Search page; replaced with clean, authoritative GovTech typography and converted green state chips into neutral pills.
  - Standardized all application pages with consistent `padding: 1.75rem 2rem` and zero artificial container capping.

### ✅ **What's Been Completed in Stage 1:**
- ✅ Project Setup, Layout & Indian Govt. Aesthetic Design System
- ✅ Authentication System & Protected Routes
- ✅ Dashboard with Summary Statistics, Recent Activity, and Quick Actions
- ✅ Projects Management (List, Detail, and Create Project Form)

### ✅ **What's Been Completed in Stage 2:**
- ✅ Evidence Registry (List, Multi-step Upload Wizard)
- ✅ Evidence Dossier Detail View (`/evidence/:id`) with multi-signal scorecards
- ✅ Review Queue (`/reviews`) and Side-by-Side Review Interface (`/review/:id`)

### ✅ **What's Been Completed in Stage 3:**
- ✅ Evidence Graph Visualization (`/graph`) with SVG network canvas & timeline view
- ✅ Advanced Multi-Parameter Search (`/search`) with direct CSV/JSON export
- ✅ Admin Dashboard & Governance (`/admin`) with User RBAC, Audit Log Viewer, & Rule Configuration

### ✅ **What's Been Completed in Stage 4 (Polish & Optimization):**

#### **1. Performance Optimization:**
- ✅ Route-level lazy loading (`React.lazy()` & `<Suspense>`) for all page modules
- ✅ Optimized Vite/Rolldown manual chunk splitting (`react-core`, `react-router`, `network`)
- ✅ Initial entry bundle reduced from >520 kB down to **18.7 kB (5.0 kB gzipped)**
- ✅ All page bundles code-split into lightweight **2 kB – 30 kB** on-demand chunks

#### **2. Accessibility Audit (WCAG 2.1 AA Compliant):**
- ✅ Keyboard focus navigation with high-contrast `:focus-visible` outlines
- ✅ *"Skip to main content"* accessible keyboard bypass link
- ✅ Full semantic landmarks (`role="banner"`, `role="navigation"`, `role="main"`, `role="contentinfo"`)
- ✅ Contrast ratios verified across badges, text, and buttons (> 4.5:1 standard)
- ✅ Accessible LoadingFallback component with `role="status"` and `.sr-only` screen-reader text

#### **3. Automated Testing Suite:**
- ✅ Native test suite implemented in `tests/` (`npm test`)
- ✅ 14 automated unit tests covering helpers, formatters, scoring scales, validators, and impossible travel algorithms
- ✅ Linting verified via `oxlint` with 0 errors

#### **4. Production Documentation:**
- ✅ Comprehensive engineering documentation created in `frontend/README.md`
- ✅ Architectural blueprints, route maps, design system tokens, and operational guidelines

### **📱 Pages Available:**
| Route | Page | Status |
|-------|------|--------|
| `/login` | Login | ✅ Stage 1 |
| `/dashboard` | Dashboard | ✅ Stage 1 |
| `/projects` | Projects List | ✅ Stage 1 |
| `/projects/create` | Create Project | ✅ Stage 1 |
| `/projects/:id` | Project Detail | ✅ Stage 1 |
| `/evidence` | Evidence List | ✅ Stage 2 |
| `/evidence/upload` | Upload Evidence | ✅ Stage 2 |
| `/evidence/:id` | Evidence Detail Dossier | ✅ Stage 2/3 |
| `/reviews` | Review Queue | ✅ Stage 2 |
| `/review/:id` | Review Interface | ✅ Stage 2 |
| `/graph` | Evidence Graph Visualization | ✅ Stage 3 |
| `/search` | Advanced Search & Export | ✅ Stage 3 |
| `/admin` | Admin Portal & Governance | ✅ Stage 3 |
| `/profile` | User Profile | ✅ |

### **Stage 3: Advanced Features - COMPLETE** ✅

### **🚀 How to Run the Application:**
- ✅ **Mock Data Integration** - All pages working with mock data
- ✅ **Responsive Design** - Basic mobile responsiveness
- ✅ **Error Handling** - Graceful error states
- ✅ **Loading States** - Spinners and loading indicators
- ✅ **Form Validation** - Client-side validation

### **🔗 Ready for Backend Integration:**
The API service layer is prepared with the following endpoints:
- Authentication API
- Projects API (GET, POST, PATCH, DELETE)
- Evidence API (stubs ready)
- Review API (stubs ready)
- Audit API (stubs ready)

---

## Project Overview
Proof-of-Action (PoA) is an Evidence Integrity & Intelligence Layer for analyzing field evidence submitted in public infrastructure projects. The frontend should follow Indian government website style - basic, clean, minimal, not flashy or AI-looking.

## Design Principles (Indian Govt. Website Style)

### Visual Style
- Clean, minimal interface
- Standard government blue color palette (#0f52ba, #0066cc, #003366)
- Simple typography (standard system fonts like Arial, Segoe UI)
- Conservative spacing, no flashy animations
- Traditional table-based layouts where appropriate
- Simple cards/panels for content separation

### UI Components
- Basic tables with striped rows
- Simple forms with clear labels
- Traditional buttons (no rounded corners, simple hover states)
- Tab-based navigation where needed
- Modal dialogs for actions

### User Experience
- Simple, predictable navigation
- Clear hierarchy of information
- No "AI slop" - focus on clear data presentation
- Accessibility-focused design
- Works well on low-bandwidth connections

## Technical Stack

### Frontend Framework
- **React** (most common, good for govt projects)
- **React Router** for navigation

### UI & Styling
- Basic components with minimal custom styling
- CSS modules or simple SCSS
- Simple charting library if needed (recharts or victory)

### State Management
- React Context or Redux (basic)
- Axios for API calls

## Stage 1: Foundation & Core Pages (MVP) - COMPLETED ✅

### ✅ COMPLETED - Page 1: Login Page
- ✅ Simple govt-branded header
- ✅ Username/password form with validation
- ✅ Submit button with loading state
- ✅ Help text/contact info
- ✅ Authentication context with token management

### ✅ COMPLETED - Page 2: Dashboard/Home
- ✅ Welcome message with user role
- ✅ Quick stats (projects count, pending reviews, etc.)
- ✅ Recent activity feed
- ✅ Quick actions (create project, upload evidence, view reviews)
- ✅ Notifications panel
- ✅ Help card with support contact

### ✅ COMPLETED - Page 3: Projects List
- ✅ Table with columns: Project ID, Project Name, Scheme, Location, Status, Evidence Count, Created Date
- ✅ Filter by status and search functionality
- ✅ Create New Project button
- ✅ Status badges with color coding
- ✅ Pagination support
- ✅ Responsive table design

### ✅ COMPLETED - Page 4: Project Detail
- ✅ Project info panel (name, description, location, timeline)
- ✅ Activities sub-section with progress bars
- ✅ Evidence list related to this project
- ✅ Project metadata table
- ✅ Breadcrumb navigation
- ✅ Edit and upload evidence actions

### ✅ COMPLETED - Page 5: Create Project Form
- ✅ Project name and scheme selection
- ✅ Location information (State, District, Village)
- ✅ Date range selection
- ✅ Description field
- ✅ Geofence coordinates input
- ✅ Form validation
- ✅ Success/error handling

## Stage 2: Analysis & Review Interface - Weeks 3-4

### Page 5: Evidence Upload
- Step 1: Select project & activity
- Step 2: Upload file(s)
- Step 3: Enter basic metadata
- Step 4: Review & submit
- Progress indicator

### Page 6: Evidence Detail
- Evidence file preview
- Basic metadata (file info, uploader, timestamp)
- Analysis results panel
- Signals breakdown table
- Integrity & risk scores with explanations
- Anomalies list
- Similar evidence section
- Review decision area (if applicable)

### Page 7: Review Queue
- Table of evidence needing review
- Columns: Evidence ID, Project, Integrity Score, Risk Score, Upload Date
- Filter by risk level, project
- Quick actions (view, skip, assign)

### Page 8: Review Interface
- Side-by-side layout:
  - Left: Evidence preview & basic info
  - Right: Analysis results & decision form
- Decision options (Approve, Reject, Flag, Request Resubmission, Request Inspection)
- Comments field
- Previous reviews history

## Stage 3: Advanced Features - COMPLETED ✅

### ✅ COMPLETED - Page 9: Evidence Graph Visualization
- ✅ Interactive SVG network graph canvas connecting Projects, Activities, Claims, Evidence, and Geofences
- ✅ Relational link definitions (`BELONGS_TO`, `SUPPORTS`, `CAPTURED_AT`, `CORROBORATES`, `DUPLICATE_OF`)
- ✅ Cross-project duplicate and contradiction discovery
- ✅ Node Inspector Drawer with full metadata and direct dossier navigation
- ✅ Chronological Timeline View with impossible travel & timeline inversion diagnostics
- ✅ Filtering by Project, Node ID search, and Cross-Project conflicts highlight

### ✅ COMPLETED - Page 10: Search & Filtering
- ✅ Advanced multi-criteria search (keyword, scheme, status, state, min integrity, max risk, date range, anomaly only)
- ✅ One-click quick presets (Flagged Anomalies, Cross-Project Duplicates, Pending Review, High Integrity)
- ✅ Direct client-side data export to CSV and formatted JSON
- ✅ Printable dossier summary report
- ✅ Tabbed counts and unified results view

### ✅ COMPLETED - Page 11: Admin Dashboard
- ✅ User Management & RBAC Table (Admin, Supervisor, Reviewer, Field Inspector, Citizen Auditor)
- ✅ Interactive user role editing and status suspension/activation toggles
- ✅ Provision New System Operator modal with client validation
- ✅ Immutable Compliance Audit Trail with severity categorization and CSV export
- ✅ System Configuration & Rule Tuning panel (High/Medium risk thresholds, geofence radius margin, velocity cutoff, quarantine retention window)
- ✅ Pipeline health & telemetry latency metrics across all micro-analyzers

## Stage 4: Polish & Optimization - COMPLETED ✅

### ✅ Completed Tasks:
1. ✅ **Performance Optimization:** Implemented route code splitting (`React.lazy()` / `<Suspense>`) and Rolldown/Vite manual chunking (`react-core`, `react-router`, `network`), decreasing initial load bundle to 18.7 kB (< 5 kB gzipped).
2. ✅ **Accessibility Audit (WCAG 2.1 AA):** Added skip-to-main-content landmark, `:focus-visible` keyboard focus indicators, prefers-reduced-motion support, contrast compliance (>4.5:1), and semantic HTML5 aria landmarks.
3. ✅ **Automated Testing Suite:** Implemented native automated tests in `tests/` (`npm test`) covering formatters, utilities, scoring algorithms, and impossible travel velocity checks (14 tests passing).
4. ✅ **Engineering Documentation:** Overhauled `frontend/README.md` with complete architecture, routing, design tokens, and developer operations manuals.

## File Structure

```
frontend/
├── public/
├── src/
│   ├── components/
│   │   ├── common/
│   │   │   ├── Header.jsx
│   │   │   ├── Footer.jsx
│   │   │   ├── Sidebar.jsx
│   │   │   ├── DataTable.jsx
│   │   │   ├── FormInput.jsx
│   │   │   └── Button.jsx
│   │   ├── evidence/
│   │   │   ├── EvidenceCard.jsx
│   │   │   ├── EvidenceUpload.jsx
│   │   │   ├── EvidenceDetail.jsx
│   │   │   └── EvidenceList.jsx
│   │   ├── projects/
│   │   │   ├── ProjectCard.jsx
│   │   │   ├── ProjectForm.jsx
│   │   │   ├── ProjectDetail.jsx
│   │   │   └── ProjectList.jsx
│   │   ├── reviews/
│   │   │   ├── ReviewQueue.jsx
│   │   │   ├── ReviewInterface.jsx
│   │   │   └── ReviewHistory.jsx
│   │   └── auth/
│   │       ├── LoginForm.jsx
│   │       └── ProtectedRoute.jsx
│   ├── pages/
│   │   ├── Login.jsx
│   │   ├── Dashboard.jsx
│   │   ├── Projects/
│   │   │   ├── ProjectsList.jsx
│   │   │   ├── ProjectDetail.jsx
│   │   │   └── CreateProject.jsx
│   │   ├── Evidence/
│   │   │   ├── EvidenceList.jsx
│   │   │   ├── EvidenceDetail.jsx
│   │   │   └── UploadEvidence.jsx
│   │   ├── Reviews/
│   │   │   ├── ReviewQueue.jsx
│   │   │   └── ReviewDetail.jsx
│   │   └── Admin/
│   │       ├── AdminDashboard.jsx
│   │       ├── UserManagement.jsx
│   │       └── AuditLog.jsx
│   ├── services/
│   │   ├── api.js
│   │   ├── auth.js
│   │   └── evidence.js
│   ├── styles/
│   │   ├── variables.scss
│   │   ├── common.scss
│   │   ├── components.scss
│   │   └── pages.scss
│   ├── utils/
│   │   ├── formatters.js
│   │   ├── validators.js
│   │   └── helpers.js
│   ├── context/
│   │   ├── AuthContext.jsx
│   │   └── ThemeContext.jsx
│   └── App.js
├── package.json
└── README.md
```

## Component Specifications

### Header Component
- Govt logo/emblem on left
- Application name
- Navigation menu
- User profile dropdown
- Simple, clean layout

### DataTable Component
- Striped rows for readability
- Sortable columns
- Pagination
- Export options
- Basic filtering

### Form Components
- Clear labels above inputs
- Required field indicators
- Simple validation messages
- Traditional form layout
- Consistent spacing

### Color Palette

```css
:root {
  --govt-blue-dark: #003366;
  --govt-blue-medium: #0066cc;
  --govt-blue-light: #0f52ba;
  --govt-white: #ffffff;
  --govt-gray-light: #f5f5f5;
  --govt-gray-medium: #cccccc;
  --govt-gray-dark: #666666;
  --govt-success: #28a745;
  --govt-warning: #ffc107;
  --govt-danger: #dc3545;
  --govt-info: #17a2b8;
}
```

## API Integration Points

### Backend API Endpoints
Based on the backend documentation, the frontend will integrate with:

1. **Authentication**
   - POST `/api/v1/auth/login`
   - POST `/api/v1/auth/logout`
   - GET `/api/v1/auth/me`

2. **Projects**
   - GET `/api/v1/projects`
   - POST `/api/v1/projects`
   - GET `/api/v1/projects/{id}`
   - PATCH `/api/v1/projects/{id}`

3. **Evidence**
   - POST `/api/v1/evidence/uploads`
   - POST `/api/v1/evidence/{id}/complete`
   - GET `/api/v1/evidence/{id}`
   - GET `/api/v1/evidence/{id}/analysis`
   - GET `/api/v1/evidence/{id}/similar`
   - GET `/api/v1/evidence/{id}/anomalies`

4. **Reviews**
   - GET `/api/v1/reviews/queue`
   - POST `/api/v1/reviews/{id}/decision`

5. **Audit**
   - GET `/api/v1/audit/events`

## Responsive Design

### Breakpoints
- Desktop: > 1024px (full features)
- Tablet: 768px - 1024px (simplified layouts)
- Mobile: < 768px (stacked layouts, essential features only)

### Mobile Considerations
- Simplify tables to card layouts
- Stack form elements vertically
- Use mobile-friendly navigation (hamburger menu)
- Ensure touch targets are adequate (min 44x44px)

## Accessibility Requirements

### WCAG 2.1 AA Compliance
- Color contrast ratio: at least 4.5:1 for normal text
- Keyboard navigation support
- Screen reader compatibility
- ARIA labels for interactive elements
- Focus indicators for keyboard users

### Semantic HTML
- Proper heading hierarchy
- Descriptive link text
- Alt text for images
- Form labels associated with inputs

## Testing Strategy

### Unit Tests
- Component rendering
- Form validation
- Utility functions

### Integration Tests
- API calls
- User flows (login, upload, review)
- State management

### E2E Tests
- Complete user journeys
- Cross-browser compatibility
- Performance benchmarks

## Performance Targets

### Loading Times
- First Contentful Paint: < 1.5s
- Largest Contentful Paint: < 2.5s
- Time to Interactive: < 3.5s

### Bundle Size
- Initial bundle: < 200kb gzipped
- Lazy loading for routes
- Code splitting for larger components

## Development Timeline

### Phase 1: Foundation (2 weeks)
- Project setup and boilerplate
- Authentication flow
- Basic layout components
- Home dashboard

### Phase 2: Core Features (2 weeks)
- Project management
- Evidence upload
- Basic evidence viewing
- Review queue interface

### Phase 3: Advanced Features (2 weeks)
- Analysis visualization
- Search and filtering
- Admin interface
- Export functionality

### Phase 4: Polish (2 weeks)
- Performance optimization
- Accessibility improvements
- Testing and bug fixes
- Documentation

## Success Metrics

### User Experience
- User satisfaction score
- Task completion rate
- Error rate during evidence upload
- Review decision time

### Technical Performance
- Page load times
- API response times
- Error rates
- Uptime percentage

### Business Impact
- Evidence processing throughput
- Review queue turnaround time
- System adoption rate

## Risk Mitigation

### Technical Risks
- API integration delays
- Performance bottlenecks
- Browser compatibility issues

### Mitigation Strategies
- Early API contract validation
- Performance monitoring from day 1
- Cross-browser testing throughout development

### Project Risks
- Scope creep
- Timeline overruns
- Changing requirements

### Mitigation Strategies
- Clear requirement sign-off
- Regular progress reviews
- Agile development approach with sprints

## Next Steps

1. **Immediate (Week 1)**
   - Set up React project
   - Create basic layout components
   - Implement authentication
   - Connect to backend API

2. **Short-term (Weeks 2-3)**
   - Build project management pages
   - Implement evidence upload flow
   - Create basic evidence viewing

3. **Medium-term (Weeks 4-6)**
   - Develop review interface
   - Add analysis visualization
   - Build admin features

4. **Long-term (Weeks 7-8)**
   - Performance optimization
   - Accessibility improvements
   - Testing and deployment

This plan provides a clear roadmap for building a clean, functional frontend that matches government website aesthetics while meeting the requirements of the Proof-of-Action evidence intelligence system.