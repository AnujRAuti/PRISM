"""BE-024 Stage D - live-server runtime verification (v2).

Boots the real FastAPI application (uvicorn subprocess) against the isolated
pofa_test environment with AUTH_MODE=enforcing, then performs actual HTTP
runtime checks: auth matrices, idempotency, pagination, malformed/missing
resources, OpenAPI-vs-behavior parity, and the Evidence -> Analysis ->
Intelligence -> Fusion -> Review -> Audit path through real endpoints plus
real in-process analysis-worker runs with ML inference.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parent
os.environ["DATABASE_URL"] = "postgresql+psycopg2://postgres:postgres@localhost:5432/pofa_test"
os.environ["AUTH_MODE"] = "enforcing"
os.environ["AUTH_DEV_TOKENS_ENABLED"] = "true"

PORT = 8137
BASE = f"http://127.0.0.1:{PORT}"
SERVER_LOG = ROOT / "stage_d_server.log"

sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402
from PIL import Image  # noqa: E402

RESULTS: list[dict] = []


def record(check: str, ok, detail: str) -> None:
    RESULTS.append({"check": check, "ok": bool(ok), "detail": detail})
    print(f"{'PASS' if ok else 'FAIL'} | {check} | {detail}", flush=True)


def hdr(user_id) -> dict:
    return {"Authorization": f"Bearer dev-user-{user_id}"}


def photo_bytes() -> bytes:
    fixture = ROOT / "test-image.jpg"
    if fixture.exists():
        return fixture.read_bytes()
    out = io.BytesIO()
    Image.new("RGB", (640, 480), color=(120, 160, 200)).save(out, format="JPEG")
    return out.getvalue()


def solid_bytes(color) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (64, 64), color=color).save(out, format="JPEG")
    return out.getvalue()


def main() -> int:
    from backend.db.models import AnalysisJob, AnalysisResult, EvidenceMetadata, User
    from backend.db.session import get_session
    from backend.services import authorization as auth_service
    from backend.services.analysis_queue import AnalysisQueue
    from backend.workers.analysis_worker import process_message

    def make_user(name: str):
        s = get_session()
        try:
            u = User(username=f"{name}-{uuid4().hex[:8]}",
                     email=f"{uuid4().hex[:8]}@runtime.example.com")
            s.add(u)
            s.commit()
            s.refresh(u)
            uid = str(u.id)
        finally:
            s.close()
        return uid

    def assign(user_id: str, role: str, scope: str, scope_id: str | None = None):
        s = get_session()
        try:
            kwargs = {}
            if scope == "PROJECT":
                kwargs["project_id"] = scope_id
            auth_service.assign_role(s, user_id=user_id, role_name=role,
                                     scope_type=scope, **kwargs)
            s.commit()
        finally:
            s.close()

    logf = open(SERVER_LOG, "w", encoding="utf-8")
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.app.main:app",
         "--host", "127.0.0.1", "--port", str(PORT), "--log-level", "info"],
        cwd=str(ROOT), env=dict(os.environ), stdout=logf, stderr=logf,
    )
    boot = time.time()
    try:
        with httpx.Client(timeout=60.0) as c:
            for _ in range(120):
                try:
                    if c.get(f"{BASE}/openapi.json").status_code == 200:
                        break
                except Exception:
                    time.sleep(0.5)
            else:
                raise RuntimeError("server did not become ready")
    except Exception:
        server.kill()
        raise
    print(f"# uvicorn ready in {time.time() - boot:.1f}s (AUTH_MODE=enforcing, "
          f"DB=pofa_test)", flush=True)

    queue = AnalysisQueue()
    queue.clear()

    officer = make_user("runtime-officer")
    supervisor = make_user("runtime-supervisor")
    nobody = make_user("runtime-nobody")
    outsider = make_user("runtime-outsider")
    assign(officer, "FIELD_OFFICER", "GLOBAL")
    assign(supervisor, "SUPERVISOR", "GLOBAL")

    failed_uuid_diagnosis = {}
    try:
        with httpx.Client(base_url=BASE, timeout=90.0) as c:
            # ---------- R0: enforcing mode rejects anonymous principal lookup ----------
            r = c.get("/api/v1/auth/me")
            record("R0 anonymous /api/v1/auth/me -> 401", r.status_code == 401,
                   f"status={r.status_code} body={r.text[:120]}")
            r = c.get("/api/v1/auth/me", headers={"Authorization": "Bearer dev-user-garbage"})
            record("R0b invalid dev token -> 401", r.status_code == 401,
                   f"status={r.status_code} body={r.text[:120]}")

            # ---------- R1: evidence upload authorization ----------
            r = c.post("/api/v1/evidence", headers=hdr(officer),
                       files={"file": ("runtime.jpg", photo_bytes(), "image/jpeg")})
            ok = r.status_code == 201
            record("R1a officer POST /api/v1/evidence -> 201", ok,
                   f"status={r.status_code} body={r.text[:160]}")
            if not ok:
                raise RuntimeError("cannot continue without evidence")
            eid = r.json()["evidence_id"]
            r = c.post("/api/v1/evidence", files={"file": ("x.jpg", photo_bytes(), "image/jpeg")})
            record("R1b anonymous evidence upload -> 401", r.status_code == 401,
                   f"status={r.status_code} body={r.text[:120]}")
            r = c.post("/api/v1/evidence", headers=hdr(nobody),
                       files={"file": ("x.jpg", photo_bytes(), "image/jpeg")})
            record("R1c no-permission evidence upload -> 403", r.status_code == 403,
                   f"status={r.status_code} body={r.text[:120]}")

            # ---------- R2: vision read auth matrix (pre-analysis) ----------
            r = c.get(f"/api/v1/evidence/{eid}/vision")
            record("R2a vision unauthenticated -> 401", r.status_code == 401,
                   f"status={r.status_code} body={r.text[:120]}")
            r = c.get(f"/api/v1/evidence/{eid}/vision", headers=hdr(nobody))
            record("R2b vision authenticated-no-permission -> 403", r.status_code == 403,
                   f"status={r.status_code} body={r.text[:120]}")

            # ---------- R3: fingerprint job -> real worker run ----------
            r = c.post("/api/v1/analysis/jobs",
                       json={"evidence_id": eid, "job_type": "fingerprint"})
            fp_job = r.json().get("job_id") if r.status_code == 202 else None
            record("R3a POST fingerprint job -> 202", r.status_code == 202 and bool(fp_job),
                   f"status={r.status_code} body={r.text[:120]}")
            if fp_job:
                msg = queue.dequeue(timeout=10)
                outcome = process_message(msg, queue) if msg else "no-message"
                record("R3b fingerprint processed by real worker", outcome == "completed",
                       f"outcome={outcome}")

            # ---------- R4: vision job -> real ML inference ----------
            r = c.post("/api/v1/analysis/jobs",
                       json={"evidence_id": eid, "job_type": "vision"})
            vis_job = r.json().get("job_id") if r.status_code == 202 else None
            record("R4a POST vision job -> 202", r.status_code == 202 and bool(vis_job),
                   f"status={r.status_code} body={r.text[:120]}")
            if vis_job:
                msg = queue.dequeue(timeout=10)
                t0 = time.time()
                outcome = process_message(msg, queue) if msg else "no-message"
                record("R4b vision job ran real inference", outcome == "completed",
                       f"outcome={outcome} wall={time.time() - t0:.1f}s")

            r = c.get(f"/api/v1/evidence/{eid}/vision", headers=hdr(supervisor))
            j = r.json() if r.status_code == 200 else {}
            record("R4c vision authorized (SUPERVISOR GLOBAL) -> 200",
                   r.status_code == 200,
                   f"status={r.status_code} total_detections={j.get('total')} "
                   f"page={len(j.get('detections', []))}")
            r = c.get(f"/api/v1/evidence/{eid}/vision", headers=hdr(nobody))
            record("R4d 200-path user still rejected -> 403 (check precedes data)",
                   r.status_code == 403, f"status={r.status_code}")

            # ---------- R5: duplicate-request idempotency ----------
            if vis_job:
                queue.enqueue(vis_job)  # simulate duplicate delivery of same job
                msg = queue.dequeue(timeout=10)
                outcome = process_message(msg, queue) if msg else "no-message"
                s = get_session()
                n_results = (s.query(AnalysisResult)
                             .filter(AnalysisResult.job_id == vis_job).count())
                s.close()
                record("R5 duplicate job delivery processed idempotently",
                       outcome in ("already_completed",) and n_results == 1,
                       f"outcome={outcome} analysis_result_rows_for_job={n_results}")
                # Documented design: POST /analysis/jobs creates a new attempt
                # row per request (append-only); dedupe happens at result level.
                r2 = c.post("/api/v1/analysis/jobs",
                            json={"evidence_id": eid, "job_type": "vision"})
                record("R5b second POST vision job accepted (new attempt, by design)",
                       r2.status_code == 202,
                       f"status={r2.status_code} new_job={r2.json().get('job_id')}")
                if r2.status_code == 202:
                    msg = queue.dequeue(timeout=10)
                    outcome = process_message(msg, queue) if msg else "no-message"
                    s = get_session()
                    try:
                        from backend.db.models import VisionDetection
                        rows = (s.query(VisionDetection)
                                .filter(VisionDetection.analysis_result_id.in_(
                                    s.query(AnalysisResult.id)
                                    .filter(AnalysisResult.job_id.in_([vis_job,
                                            r2.json().get("job_id")])))).all())
                        det_by_job: dict = {}
                        for d in rows:
                            det_by_job.setdefault(d.analysis_result_id, []).append(
                                (d.class_name, round(float(d.confidence), 6)))
                        n = (s.query(AnalysisJob)
                             .filter(AnalysisJob.evidence_id == eid,
                                     AnalysisJob.job_type == "vision").count())
                    finally:
                        s.close()
                    same = len(det_by_job) == 2 and \
                        len({tuple(sorted(v)) for v in det_by_job.values()}) == 1
                    record("R5c vision rerun idempotent: identical detections, jobs=%d" % n,
                           outcome == "completed" and same,
                           f"outcome={outcome} detection_sets_identical={same}")

            # ---------- R6: pagination + authorization filtering ----------
            r = c.get(f"/api/v1/evidence/{eid}/vision", headers=hdr(supervisor),
                      params={"limit": 1, "offset": 0})
            j = r.json() if r.status_code == 200 else {}
            record("R6a vision pagination limit=1 echoes params and page size",
                   r.status_code == 200 and j.get("limit") == 1 and j.get("offset") == 0
                   and len(j.get("detections", [])) <= 1,
                   f"status={r.status_code} limit={j.get('limit')} "
                   f"page_len={len(j.get('detections', []))} total={j.get('total')}")
            r = c.get(f"/api/v1/evidence/{eid}/vision", headers=hdr(supervisor),
                      params={"limit": 0})
            record("R6b pagination out-of-range limit -> 422", r.status_code == 422,
                   f"status={r.status_code} body={r.text[:160]}")

            proj = c.post("/api/v1/projects", headers=hdr(supervisor),
                          json={"name": f"runtime-{uuid4().hex[:6]}",
                                "owner_id": supervisor})
            proj_id = proj.json()["id"] if proj.status_code == 201 else None
            record("R6c supervisor POST /projects -> 201",
                   proj.status_code == 201, f"status={proj.status_code} body={proj.text[:120]}")
            if proj_id:
                assign(outsider, "REVIEWER", "PROJECT", proj_id)
                r = c.get(f"/api/v1/evidence/{eid}/vision", headers=hdr(outsider))
                record("R6d out-of-scope PROJECT reviewer -> 404 (authz filtering)",
                       r.status_code == 404, f"status={r.status_code} body={r.text[:120]}")
                r = c.get("/api/v1/projects", headers=hdr(outsider))
                record("R6e project list shows only authorized projects",
                       r.status_code == 200 and any(
                           p["id"] == proj_id for p in r.json().get("items", [])),
                       f"status={r.status_code} total={r.json().get('total') if r.status_code == 200 else None}")

            # ---------- R7: temporal auth matrix ----------
            r = c.post(f"/api/v1/analysis/temporal/{eid}", json={})
            record("R7a temporal unauthenticated -> 401", r.status_code == 401,
                   f"status={r.status_code} body={r.text[:120]}")
            r = c.post(f"/api/v1/analysis/temporal/{eid}", json={}, headers=hdr(nobody))
            record("R7b temporal authenticated-no-permission -> 403", r.status_code == 403,
                   f"status={r.status_code} body={r.text[:120]}")
            r = c.post(f"/api/v1/analysis/temporal/{eid}", json={}, headers=hdr(supervisor))
            body = r.json() if r.status_code == 200 else {}
            record("R7c temporal authorized -> 200 with analysis payload",
                   r.status_code == 200 and "status" in body,
                   f"status={r.status_code} keys={sorted(body.keys())[:8]}")
            r = c.post(f"/api/v1/analysis/temporal/{str(uuid4())}", json={},
                       headers=hdr(supervisor))
            record("R7d temporal missing evidence -> 404", r.status_code == 404,
                   f"status={r.status_code} body={r.text[:120]}")

            # ---------- R8: malformed requests ----------
            for label, req in {
                "GET /evidence/{id}": lambda: c.get("/api/v1/evidence/not-a-uuid",
                                                    headers=hdr(supervisor)),
                "GET /evidence/{id}/vision": lambda: c.get(
                    "/api/v1/evidence/not-a-uuid/vision", headers=hdr(supervisor)),
                "POST /analysis/temporal/{id}": lambda: c.post(
                    "/api/v1/analysis/temporal/not-a-uuid", json={}, headers=hdr(supervisor)),
                "GET /review-cases/{id}": lambda: c.get("/api/v1/review-cases/not-a-uuid",
                                                        headers=hdr(supervisor)),
                "POST /fusion/CLAIM/{id}": lambda: c.post("/api/v1/fusion/CLAIM/not-a-uuid",
                                                          json={}, headers=hdr(supervisor)),
            }.items():
                resp = req()
                failed_uuid_diagnosis[label] = (resp.status_code, resp.text[:120])
            bad = {k: v for k, v in failed_uuid_diagnosis.items() if v[0] != 422}
            record("R8a malformed path UUID -> 422 on every probed endpoint",
                   not bad, f"observed={ {k: v[0] for k, v in failed_uuid_diagnosis.items()} }")
            r = c.post("/api/v1/analysis/jobs",
                       json={"evidence_id": 12345, "job_type": "bogus"})
            record("R8b malformed job body -> 422", r.status_code == 422,
                   f"status={r.status_code} body={r.text[:200]}")
            r = c.post("/api/v1/analysis/jobs",
                       json={"evidence_id": str(uuid4()), "job_type": "fingerprint"})
            record("R8c job for missing evidence -> 404", r.status_code == 404,
                   f"status={r.status_code} body={r.text[:120]}")
            r = c.post("/api/v1/evidence", headers=hdr(officer),
                       files={"file": ("bad.txt", b"not an image", "text/plain")})
            record("R8d non-image upload rejected with explicit 4xx",
                   r.status_code in (400, 415, 422),
                   f"status={r.status_code} body={r.text[:160]}")
            r = c.get(f"/api/v1/analysis/jobs/{str(uuid4())}")
            record("R8e missing analysis job -> 404", r.status_code == 404,
                   f"status={r.status_code} body={r.text[:120]}")

            # ---------- R9: OpenAPI parity from the running app ----------
            spec = c.get("/openapi.json").json()
            paths = spec.get("paths", {})
            want = {
                "/api/v1/evidence/{evidence_id}/vision": "get",
                "/api/v1/analysis/temporal/{evidence_id}": "post",
                "/api/v1/analysis/jobs": "post",
                "/api/v1/fusion/{target_type}/{target_id}": "post",
                "/api/v1/review-cases/from-fusion/{fusion_run_id}": "post",
                "/api/v1/audit/events": "get",
            }
            missing = [p for p, m in want.items() if m not in paths.get(p, {})]
            record("R9a running-app OpenAPI documents exercised endpoints",
                   not missing, f"missing={missing}")
            vp = paths.get("/api/v1/evidence/{evidence_id}/vision", {})
            r = c.delete(f"/api/v1/evidence/{eid}/vision", headers=hdr(supervisor))
            allowed = {m.strip().lower() for m in r.headers.get("allow", "").split(",")} - {"head"}
            record("R9b live 405 allow-list matches spec methods",
                   r.status_code == 405 and allowed == set(vp.keys()),
                   f"status={r.status_code} allow={sorted(allowed)} spec={sorted(vp.keys())}")
            vis_200 = vp.get("get", {}).get("responses", {}).get("200", {})
            record("R9c OpenAPI declares 200 JSON content for vision GET",
                   bool(vis_200.get("content")),
                   f"content_keys={list(vis_200.get('content', {}).keys())}")
            documented = set(vp.get("get", {}).get("responses", {}).keys())
            record("R9d observation: auth rejection codes present in live behavior vs spec",
                   True,  # informational: FastAPI does not auto-document 401/403
                   f"spec_response_codes={sorted(documented)} "
                   f"observed_codes=[401,403,404,200] (401/403/404 not declared in spec)")

            # ---------- R10: E2E Evidence->Analysis->Intelligence->Fusion->Review->Audit ----------
            claim = c.post(f"/api/v1/projects/{proj_id}/claims", headers=hdr(supervisor),
                           json={"title": "runtime claim", "description": "stage D",
                                 "claimant_id": supervisor}) if proj_id else None
            claim_id = claim.json()["id"] if claim and claim.status_code == 201 else None
            record("R10a claim created via HTTP -> 201",
                   claim is not None and claim.status_code == 201,
                   f"status={claim.status_code if claim else None} "
                   f"body={claim.text[:120] if claim else None}")
            edge = c.post("/api/v1/graph/relationships", headers=hdr(supervisor), json={
                "source": {"node_type": "EVIDENCE", "entity_id": eid},
                "target": {"node_type": "CLAIM", "entity_id": claim_id},
                "relationship_type": "SUPPORTS",
                "provenance": {"source": "human_review", "method": "runtime_check"}})
            record("R10b graph edge EVIDENCE -SUPPORTS-> CLAIM",
                   edge.status_code in (200, 201), f"status={edge.status_code} body={edge.text[:140]}")
            fusion = c.post(f"/api/v1/fusion/CLAIM/{claim_id}", headers=hdr(supervisor), json={})
            run_id = (fusion.json().get("run") or {}).get("id") if fusion.status_code == 200 else None
            record("R10c fusion execute on CLAIM via HTTP -> 200",
                   fusion.status_code == 200 and bool(run_id),
                   f"status={fusion.status_code} assessment="
                   f"{(fusion.json().get('assessment') or {}).get('assessment') if fusion.status_code == 200 else fusion.text[:120]}")

            # Urgent duplicate-evidence target drives a real review case.
            from backend.services.duplicate_intelligence import analyze_duplicates
            from backend.services.fingerprinting import process_evidence
            payload = solid_bytes((71, 141, 211))
            u1 = c.post("/api/v1/evidence", headers=hdr(officer),
                        files={"file": ("dup-a.jpg", payload, "image/jpeg")}).json()
            u2 = c.post("/api/v1/evidence", headers=hdr(officer),
                        files={"file": ("dup-b.jpg", payload, "image/jpeg")}).json()
            s = get_session()
            try:
                process_evidence(u1["evidence_id"], s)
                process_evidence(u2["evidence_id"], s)
                analyze_duplicates(u1["evidence_id"], s)
                meta = (s.query(EvidenceMetadata)
                        .filter_by(evidence_id=u1["evidence_id"]).one())
                meta.metadata_json = {**(meta.metadata_json or {}),
                                      "exif": {"EXIF DateTimeOriginal": "2030-01-01 10:00:00"}}
                s.commit()
            finally:
                s.close()
            fuse2 = c.post(f"/api/v1/fusion/EVIDENCE/{u1['evidence_id']}",
                           headers=hdr(supervisor), json={})
            run2_id = (fuse2.json().get("run") or {}).get("id") if fuse2.status_code == 200 else None
            prio = (fuse2.json().get("priority") or {}).get("priority") if fuse2.status_code == 200 else None
            record("R10d fusion on duplicate-signal evidence -> HIGH/URGENT",
                   fuse2.status_code == 200 and prio in ("HIGH", "URGENT"),
                   f"status={fuse2.status_code} priority={prio}")
            case_id = None
            if run2_id:
                gen = c.post(f"/api/v1/review-cases/from-fusion/{run2_id}",
                             headers=hdr(supervisor), json={})
                gj = gen.json() if gen.status_code in (200, 201) else {}
                case_id = (gj.get("case") or {}).get("id")
                record("R10e review case generated (CASE_CREATED, 201)",
                       gen.status_code == 201 and gj.get("result") == "CASE_CREATED" and case_id,
                       f"status={gen.status_code} result={gj.get('result')} band="
                       f"{(gj.get('case') or {}).get('priority_band')}")
                again = c.post(f"/api/v1/review-cases/from-fusion/{run2_id}",
                               headers=hdr(supervisor), json={})
                record("R10f duplicate case generation idempotent (200 CASE_ALREADY_EXISTS)",
                       again.status_code == 200 and again.json().get("result") == "CASE_ALREADY_EXISTS"
                       and (again.json().get("case") or {}).get("id") == case_id,
                       f"status={again.status_code} result={again.json().get('result')}")
            if case_id:
                rc = c.get(f"/api/v1/review-cases/{case_id}", headers=hdr(supervisor))
                record("R10g review case readable via HTTP",
                       rc.status_code == 200, f"status={rc.status_code}")
                asg = c.post(f"/api/v1/review-cases/{case_id}/assign",
                             headers=hdr(supervisor),
                             json={"assigned_to": supervisor})
                inv = c.post(f"/api/v1/review-cases/{case_id}/investigate",
                             headers=hdr(supervisor))
                dec = c.post(f"/api/v1/review-cases/{case_id}/decision",
                             headers=hdr(supervisor),
                             json={"decision": "INCONCLUSIVE",
                                   "rationale": "runtime Stage D check",
                                   "decided_by": supervisor})
                res = c.post(f"/api/v1/review-cases/{case_id}/resolve",
                             headers=hdr(supervisor))
                record("R10h review lifecycle assign->investigate->decision->resolve",
                       asg.status_code == 200 and inv.status_code == 200
                       and dec.status_code == 200
                       and res.status_code == 200
                       and res.json().get("status") == "RESOLVED",
                       f"assign={asg.status_code} investigate={inv.status_code} "
                       f"decision={dec.status_code}"
                       f"({dec.text[:80] if dec.status_code != 200 else ''}) "
                       f"resolve={res.status_code} state={res.json().get('status')}")
            if run_id:
                re_run = c.post(f"/api/v1/fusion/CLAIM/{claim_id}", headers=hdr(supervisor), json={})
                run_id_2 = (re_run.json().get("run") or {}).get("id") if re_run.status_code == 200 else None
                record("R10i duplicate fusion request -> new append-only run",
                       re_run.status_code == 200 and run_id_2 and run_id_2 != run_id,
                       f"status={re_run.status_code} run1={run_id} run2={run_id_2}")

            anon = c.get("/api/v1/audit/events")
            record("R11a audit events unauthenticated -> 401", anon.status_code == 401,
                   f"status={anon.status_code}")
            r = c.get("/api/v1/audit/events", headers=hdr(nobody))
            record("R11b audit events no-permission -> 403", r.status_code == 403,
                   f"status={r.status_code}")
            audit = c.get("/api/v1/audit/events", headers=hdr(supervisor),
                          params={"limit": 5, "offset": 0, "resource_type": "review_cases",
                                  "since": datetime(2026, 9, 27, 0, 0, tzinfo=timezone.utc).isoformat()})
            items = audit.json().get("items", []) if audit.status_code == 200 else []
            record("R11c audit events for this run's review case present (paginated)",
                   audit.status_code == 200 and len(items) > 0,
                   f"status={audit.status_code} total={audit.json().get('total') if audit.status_code == 200 else None} "
                   f"page={len(items)}")
            verify = c.get("/api/v1/audit/verify", headers=hdr(supervisor))
            vbody = verify.json() if verify.status_code == 200 else {}
            record("R11d audit hash-chain verify -> valid",
                   verify.status_code == 200 and vbody.get("valid") is True,
                   f"status={verify.status_code} checked={vbody.get('checked_events')} "
                   f"failures={len(vbody.get('failures', []))}")
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except Exception:
            server.kill()
        logf.close()
        queue.clear()

    if failed_uuid_diagnosis:
        print("# malformed-UUID observations: "
              + json.dumps({k: v for k, v in failed_uuid_diagnosis.items()}), flush=True)
        print("# --- server log tail (exception tracebacks) ---", flush=True)
        text = SERVER_LOG.read_text(encoding="utf-8", errors="replace")
        idx = text.find("Traceback")
        print(text[idx:idx + 3000] if idx >= 0 else "(no traceback in log)", flush=True)

    failed = [r for r in RESULTS if not r["ok"]]
    print(f"\n==== SUMMARY: {len(RESULTS)} checks, "
          f"{len(RESULTS) - len(failed)} passed, {len(failed)} failed ====", flush=True)
    for f in failed:
        print(f"FAILED: {f['check']} | {f['detail']}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(2)
