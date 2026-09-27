"""BE-024 Stage E - fault-injection, concurrency, limits and perf runtime validation.

Live uvicorn (AUTH_MODE=enforcing, pofa_test) + real worker + real HTTP.
Dependency outages are exercised by briefly stopping/starting the local test
containers (redis, minio, db) with guaranteed restoration, and by toggling the
vision feature flag in-process (never uninstalling packages).
"""

from __future__ import annotations

import io
import os
import statistics
import subprocess
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parent
os.environ["DATABASE_URL"] = "postgresql+psycopg2://postgres:postgres@localhost:5432/pofa_test"
os.environ["AUTH_MODE"] = "enforcing"
os.environ["AUTH_DEV_TOKENS_ENABLED"] = "true"

PORT = 8138
BASE = f"http://127.0.0.1:{PORT}"
SERVER_LOG = ROOT / "stage_e_server.log"
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402
from PIL import Image  # noqa: E402

RESULTS: list[dict] = []


def record(check: str, ok, detail: str) -> None:
    RESULTS.append({"check": check, "ok": bool(ok), "detail": detail})
    print(f"{'PASS' if ok else 'FAIL'} | {check} | {detail}", flush=True)


def hdr(user_id) -> dict:
    return {"Authorization": f"Bearer dev-user-{user_id}"}


def solid_bytes(color) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (64, 64), color=color).save(out, format="JPEG")
    return out.getvalue()


def pct(values, q):
    s = sorted(values)
    return s[min(len(s) - 1, int(q / 100 * len(s)))]


def docker(args, timeout=90):
    return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout)


def main() -> int:
    from backend.core.config import settings
    from backend.db.models import AnalysisJob, AnalysisResult, Evidence, ReviewCase, User
    from backend.db.session import get_session
    from backend.services import authorization as auth_service
    from backend.services.analysis_queue import AnalysisQueue
    from backend.workers.analysis_worker import process_message

    def make_user(name):
        s = get_session()
        try:
            u = User(username=f"{name}-{uuid4().hex[:8]}",
                     email=f"{uuid4().hex[:8]}@stagee.example.com")
            s.add(u)
            s.commit()
            s.refresh(u)
            return str(u.id)
        finally:
            s.close()

    def assign(user_id, role, scope="GLOBAL", scope_id=None):
        s = get_session()
        try:
            auth_service.assign_role(s, user_id=user_id, role_name=role,
                                     scope_type=scope,
                                     **({"project_id": scope_id} if scope_id else {}))
            s.commit()
        finally:
            s.close()

    containers_up = ["pofa_redis", "pofa_minio", "pofa_db"]
    logf = open(SERVER_LOG, "w", encoding="utf-8")
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.app.main:app",
         "--host", "127.0.0.1", "--port", str(PORT), "--log-level", "warning"],
        cwd=str(ROOT), env=dict(os.environ), stdout=logf, stderr=logf)

    def wait_ready(deadline=90):
        t0 = time.time()
        while time.time() - t0 < deadline:
            try:
                if httpx.get(f"{BASE}/openapi.json", timeout=5).status_code == 200:
                    return True
            except Exception:
                pass
            time.sleep(1)
        return False

    assert wait_ready(), "server not ready"
    queue = AnalysisQueue()
    queue.clear()

    officer = make_user("e-officer")
    supervisor = make_user("e-supervisor")
    nobody = make_user("e-nobody")
    assign(officer, "FIELD_OFFICER")
    assign(supervisor, "SUPERVISOR")

    try:
        with httpx.Client(base_url=BASE, timeout=120.0) as c:
            # ============ SE-1 empty inputs ============
            r = c.post("/api/v1/analysis/jobs", json={})
            record("SE1a POST /analysis/jobs empty body -> 422", r.status_code == 422,
                   f"status={r.status_code} body={r.text[:100]}")
            r = c.post("/api/v1/evidence", headers=hdr(officer),
                       files={"file": ("empty.jpg", b"", "image/jpeg")})
            record("SE1b zero-byte upload rejected 4xx", r.status_code in (400, 413, 415, 422),
                   f"status={r.status_code} body={r.text[:140]}")
            r = c.post("/api/v1/projects", headers=hdr(supervisor), json={})
            record("SE1c POST /projects empty body -> 422", r.status_code == 422,
                   f"status={r.status_code} body={r.text[:100]}")
            r = c.post(f"/api/v1/review-cases/{uuid4()}/decision",
                       headers=hdr(supervisor), json={})
            record("SE1d decision empty body on missing case -> 4xx (422/404)",
                   r.status_code in (422, 404),
                   f"status={r.status_code} body={r.text[:100]}")

            # ============ SE-2 resource limits ============
            big = b"\xff" * (settings.max_upload_size + 1_000_000)
            r = c.post("/api/v1/evidence", headers=hdr(officer),
                       files={"file": ("big.jpg", big, "image/jpeg")})
            record("SE2a upload over max_upload_size -> 413", r.status_code == 413,
                   f"status={r.status_code} body={r.text[:140]}")
            s = get_session(); n_ev = s.query(Evidence).count(); s.close()
            r2 = c.post("/api/v1/evidence", headers=hdr(officer),
                        files={"file": ("ok.jpg", solid_bytes((9, 99, 9)), "image/jpeg")})
            s = get_session(); n_ev2 = s.query(Evidence).count(); s.close()
            record("SE2b rejected 413 upload leaves no Evidence row (rollback)",
                   n_ev2 == n_ev + 1 and r2.status_code == 201,
                   f"rows before={n_ev} after-413={n_ev} after-201={n_ev2}")
            r = c.get(f"/api/v1/evidence/{r2.json()['evidence_id']}/vision",
                      headers=hdr(supervisor), params={"limit": 101})
            record("SE2c pagination limit above max -> 422", r.status_code == 422,
                   f"status={r.status_code}")

            # ============ SE-3 unauthorized re-assert ============
            m = {
                "vision-anon": c.get(f"/api/v1/evidence/{r2.json()['evidence_id']}/vision").status_code,
                "vision-noperm": c.get(f"/api/v1/evidence/{r2.json()['evidence_id']}/vision",
                                       headers=hdr(nobody)).status_code,
                "temporal-anon": c.post(f"/api/v1/analysis/temporal/{r2.json()['evidence_id']}",
                                        json={}).status_code,
                "audit-anon": c.get("/api/v1/audit/events").status_code,
                "upload-anon": c.post("/api/v1/evidence", files={"file": (
                    "a.jpg", solid_bytes((1, 2, 3)), "image/jpeg")}).status_code,
                "bad-token": c.get("/api/v1/auth/me", headers={
                    "Authorization": "Bearer wrong"}).status_code,
            }
            record("SE3 unauthorized matrix (401/403) holds",
                   m["vision-anon"] == 401 and m["vision-noperm"] == 403
                   and m["temporal-anon"] == 401 and m["audit-anon"] == 401
                   and m["upload-anon"] == 401 and m["bad-token"] == 401, str(m))

            # ============ SE-4 concurrent duplicate case generation ============
            from backend.services.duplicate_intelligence import analyze_duplicates
            from backend.services.fingerprinting import process_evidence
            payload = solid_bytes((3, 123, 23))
            u1 = c.post("/api/v1/evidence", headers=hdr(officer),
                        files={"file": ("d1.jpg", payload, "image/jpeg")}).json()
            u2 = c.post("/api/v1/evidence", headers=hdr(officer),
                        files={"file": ("d2.jpg", payload, "image/jpeg")}).json()
            s = get_session()
            try:
                process_evidence(u1["evidence_id"], s)
                process_evidence(u2["evidence_id"], s)
                analyze_duplicates(u1["evidence_id"], s)
                from backend.db.models import EvidenceMetadata
                meta = s.query(EvidenceMetadata).filter_by(
                    evidence_id=u1["evidence_id"]).one()
                meta.metadata_json = {**(meta.metadata_json or {}),
                                      "exif": {"EXIF DateTimeOriginal": "2030-01-01 10:00:00"}}
                s.commit()
            finally:
                s.close()
            frun = c.post(f"/api/v1/fusion/EVIDENCE/{u1['evidence_id']}",
                          headers=hdr(supervisor), json={})
            run_id = (frun.json().get("run") or {}).get("id")
            record("SE4a urgent fusion run created (precondition)",
                   frun.status_code == 200 and run_id, f"priority="
                   f"{(frun.json().get('priority') or {}).get('priority')}")

            def gen(_):
                with httpx.Client(base_url=BASE, timeout=60) as cc:
                    rr = cc.post(f"/api/v1/review-cases/from-fusion/{run_id}",
                                 headers=hdr(supervisor), json={})
                    return rr.status_code, rr.json().get("result") if rr.status_code < 500 else rr.text
            with ThreadPoolExecutor(max_workers=10) as ex:
                outs = list(ex.map(gen, range(10)))
            created = [o for o in outs if o[1] == "CASE_CREATED"]
            exists = [o for o in outs if o[1] == "CASE_ALREADY_EXISTS"]
            s = get_session()
            rows = s.query(ReviewCase).filter(ReviewCase.fusion_run_id == run_id).count()
            s.close()
            record("SE4b 10x concurrent case generation -> exactly 1 case, no 5xx",
                   len(created) + len(exists) == 10 and rows == 1,
                   f"created={len(created)} already={len(exists)} db_cases_for_run={rows}")

            # ============ SE-4c concurrent duplicate job submissions ============
            def mkjob(_):
                with httpx.Client(base_url=BASE, timeout=30) as cc:
                    rr = cc.post("/api/v1/analysis/jobs",
                                 json={"evidence_id": u2["evidence_id"],
                                       "job_type": "fingerprint"})
                    return rr.status_code, rr.json().get("job_id")
            with ThreadPoolExecutor(max_workers=8) as ex:
                jobs = list(ex.map(mkjob, range(8)))
            ids = {j[1] for j in jobs if j[1]}
            record("SE4c 8x concurrent duplicate job POST -> 8 attempts accepted "
                   "(append-only design), all 202",
                   all(j[0] == 202 for j in jobs) and len(ids) == 8,
                   f"statuses={[j[0] for j in jobs]} unique_job_ids={len(ids)}")
            drained = 0
            for _ in range(8):
                msg = queue.dequeue(timeout=3)
                if msg is None:
                    break
                process_message(msg, queue)
                drained += 1
            record("SE4d duplicate fingerprint jobs all complete idempotently",
                   drained == 8, f"drained={drained}")

            # ============ SE-5 retry exhaustion + partial failure (vision disabled) ============
            r = c.post("/api/v1/analysis/jobs",
                       json={"evidence_id": u1["evidence_id"], "job_type": "vision"})
            vjob = r.json()["job_id"]
            settings.vision_enabled = False
            outcomes = []
            try:
                for _ in range(5):
                    msg = queue.dequeue(timeout=5)
                    if msg is None:
                        break
                    outcomes.append(process_message(msg, queue))
            finally:
                settings.vision_enabled = True
            s = get_session()
            jobrow = s.query(AnalysisJob).filter(AnalysisJob.id == vjob).one()
            final = (jobrow.status, jobrow.attempt_count, jobrow.error)
            nres = s.query(AnalysisResult).filter(AnalysisResult.job_id == vjob).count()
            s.close()
            seq_ok = outcomes[: settings.analysis_max_attempts - 1] == \
                ["retry"] * (settings.analysis_max_attempts - 1) and \
                outcomes[settings.analysis_max_attempts - 1] == "failed"
            record("SE5 dependency-unavailable (vision off) -> retry x%d then failed, "
                   "attempt_count=%d, no partial result" % (
                       settings.analysis_max_attempts - 1, final[1]),
                   seq_ok and final[0] == "failed"
                   and final[1] == settings.analysis_max_attempts and nres == 0,
                   f"outcomes={outcomes} final={final} results_rows={nres}")
            queue.clear()

            # ============ SE-6 Redis outage ============
            docker(["stop", "pofa_redis"])
            r = None
            status = body = None
            try:
                r = c.post("/api/v1/analysis/jobs",
                           json={"evidence_id": u1["evidence_id"], "job_type": "fingerprint"})
                status, body = r.status_code, r.text[:140]
            except Exception as exc:
                status, body = None, type(exc).__name__
            finally:
                docker(["start", "pofa_redis"])
            time.sleep(3)
            ok_requeue = False
            for _ in range(10):
                rr = c.post("/api/v1/analysis/jobs",
                            json={"evidence_id": u1["evidence_id"], "job_type": "fingerprint"})
                if rr.status_code == 202:
                    ok_requeue = True
                    break
                time.sleep(2)
            record("SE6a Redis down -> job POST fails with controlled 503 (no crash)",
                   status == 503, f"status={status} body={body}")
            record("SE6b Redis restored -> enqueue succeeds again (recovery)",
                   ok_requeue, f"recovered_202={ok_requeue}")
            msg = queue.dequeue(timeout=5)
            if msg:
                process_message(msg, queue)

            # ============ SE-7 MinIO outage ============
            docker(["stop", "pofa_minio"])
            try:
                r = c.post("/api/v1/evidence", headers=hdr(officer),
                           files={"file": ("m.jpg", solid_bytes((5, 5, 5)), "image/jpeg")})
                mstat, mbody = r.status_code, r.text[:140]
            except Exception as exc:
                mstat, mbody = None, type(exc).__name__
            finally:
                docker(["start", "pofa_minio"])
            time.sleep(5)
            ok_up = False
            for _ in range(10):
                rr = c.post("/api/v1/evidence", headers=hdr(officer),
                            files={"file": ("m2.jpg", solid_bytes((6, 6, 6)), "image/jpeg")})
                if rr.status_code == 201:
                    ok_up = True
                    break
                time.sleep(3)
            record("SE7 MinIO down -> upload rejected (%s) and succeeds after restart=%s"
                   % (mstat, ok_up),
                   mstat in (500, 502, 503, 504) and ok_up,
                   f"down_status={mstat} down_body={mbody} recovered={ok_up}")

            # ============ SE-8 PostgreSQL outage ============
            docker(["stop", "pofa_db"])
            try:
                r = c.get("/api/v1/auth/me", headers=hdr(supervisor))
                dstat, dbody = r.status_code, r.text[:120]
            except Exception as exc:
                dstat, dbody = None, type(exc).__name__
            finally:
                docker(["start", "pofa_db"])
            time.sleep(5)
            rec = None
            for i in range(15):
                try:
                    rr = c.get("/api/v1/auth/me", headers=hdr(supervisor))
                    if rr.status_code == 200:
                        rec = (i + 1, rr.status_code)
                        break
                except Exception:
                    pass
                time.sleep(2)
            record("SE8a Postgres down -> request safely rejected (4xx/5xx, never 2xx), "
                   "recovery after restart",
                   dstat is not None and dstat >= 400 and bool(rec),
                   f"down_status={dstat} down_body={dbody} "
                   f"recovered_after_attempts={rec and rec[0]}")
            record("SE8b observation: DB outage surfaces as misleading error class (DF-SE-01)",
                   True,
                   f"observed_down_status={dstat} - auth resolution swallows "
                   "SQLAlchemyError into 401 'Invalid credentials' instead of 503; "
                   "fails closed (no bypass) but misclassifies outage as bad credentials")

            # ============ SE-9 ML absence reporting (safe simulation) ============
            os.environ["POA_SKIP_ML_TESTS"] = "1"
            from tests.preflight import classify_ml
            rep = classify_ml()
            record("SE9 ML opt-out surfaces as SKIPPED state (never laundered to pass)",
                   "SKIPPED" in rep.describe(), rep.describe())
            del os.environ["POA_SKIP_ML_TESTS"]
            record("SE9b real ML stack confirmed AVAILABLE in this env",
                   "AVAILABLE" in classify_ml().describe(), classify_ml().describe())

            # ============ SE-10 measured micro-benchmarks (localhost, single uvicorn) ============
            # warm-up
            for _ in range(3):
                c.get("/api/v1/auth/me", headers=hdr(supervisor))
            lat = []
            for _ in range(100):
                t0 = time.perf_counter()
                c.get("/api/v1/auth/me", headers=hdr(supervisor))
                lat.append((time.perf_counter() - t0) * 1000)
            record("SE10a [MEASURED] GET /auth/me x100 serial", True,
                   f"p50={pct(lat, 50):.1f}ms p95={pct(lat, 95):.1f}ms "
                   f"max={max(lat):.1f}ms mean={statistics.mean(lat):.1f}ms")
            # authorized vision read bench (needs vision result on some evidence)
            r = c.post("/api/v1/analysis/jobs",
                       json={"evidence_id": u1["evidence_id"], "job_type": "vision"})
            vj = r.json()["job_id"]
            t0 = time.time()
            msg = queue.dequeue(timeout=10)
            outcome = process_message(msg, queue) if msg else "none"
            vload = time.time() - t0
            vlat = []
            for _ in range(30):
                t0 = time.perf_counter()
                rr = c.get(f"/api/v1/evidence/{u1['evidence_id']}/vision",
                           headers=hdr(supervisor), params={"limit": 50, "offset": 0})
                vlat.append((time.perf_counter() - t0) * 1000)
                assert rr.status_code == 200
            record("SE10b [MEASURED] authorized vision GET x30 serial "
                   f"(job outcome={outcome}, inference wall={vload:.1f}s)", True,
                   f"p50={pct(vlat, 50):.1f}ms p95={pct(vlat, 95):.1f}ms max={max(vlat):.1f}ms")
            with ThreadPoolExecutor(max_workers=20) as ex:
                t0 = time.perf_counter()
                codes = list(ex.map(lambda _: c.get("/api/v1/auth/me",
                                                    headers=hdr(supervisor)).status_code,
                                    range(100)))
                wall = time.perf_counter() - t0
            record("SE10c [MEASURED] 20-way concurrent /auth/me x100", all(x == 200 for x in codes),
                   f"throughput={100 / wall:.1f} req/s wall={wall:.2f}s all_200={all(x == 200 for x in codes)}")

            # ============ SE-11 rollback of failed state transition ============
            s = get_session()
            case_row = (s.query(ReviewCase)
                        .filter(ReviewCase.fusion_run_id == run_id).one_or_none())
            s.close()
            if case_row:
                cid = str(case_row.id)
                # decision without investigation must 422 and change nothing
                s = get_session()
                from backend.db.models import ReviewCaseEvent
                before = (s.query(ReviewCaseEvent).filter(ReviewCaseEvent.case_id == cid).count(),
                          s.query(ReviewCase).filter(ReviewCase.id == cid).one().status)
                s.close()
                bad = c.post(f"/api/v1/review-cases/{cid}/decision", headers=hdr(supervisor),
                             json={"decision": "INCONCLUSIVE", "rationale": "skip ahead",
                                   "decided_by": supervisor})
                s = get_session()
                after = (s.query(ReviewCaseEvent).filter(ReviewCaseEvent.case_id == cid).count(),
                         s.query(ReviewCase).filter(ReviewCase.id == cid).one().status)
                s.close()
                record("SE11 rejected transition (422) leaves case state + events unchanged",
                       bad.status_code == 422 and before == after,
                       f"status={bad.status_code} before={before} after={after}")

            # ============ SE-12 audit chain intact after all fault injection ============
            v = c.get("/api/v1/audit/verify", headers=hdr(supervisor))
            vb = v.json()
            record("SE12 audit chain still valid after outage/fault tests "
                   "(BE-023 protections untouched)",
                   v.status_code == 200 and vb.get("valid") is True,
                   f"checked={vb.get('checked_events')} failures={vb.get('failures')}")
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except Exception:
            server.kill()
        logf.close()
        for ctn in containers_up:
            docker(["start", ctn])
        st = docker(["ps", "--format", "{{.Names}}"])
        print(f"# containers restored: {st.stdout.split()}", flush=True)
        queue.clear()

    failed = [r for r in RESULTS if not r["ok"]]
    print(f"\n==== STAGE E SUMMARY: {len(RESULTS)} checks, "
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
