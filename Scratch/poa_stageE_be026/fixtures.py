"""Stage E world builder: two organizations, full role coverage, live rows.

Every object is created through the shipped services/endpoints (no shortcuts),
tagged with the run LABEL and removed by h.teardown().
"""

from h import (BASE, LABEL, create_assignment, grant, new_activity, new_api_client,
               new_claim, new_org, new_project, new_unit, new_user, tracked)


def build_world(suffix):
    w = {"suffix": suffix}
    w["org_a"] = new_org(f"{suffix}-orgA")
    w["unit_a"] = new_unit(w["org_a"], f"{suffix}-unitA")
    w["org_b"] = new_org(f"{suffix}-orgB")
    w["unit_b"] = new_unit(w["org_b"], f"{suffix}-unitB")

    w["admin"] = new_user(f"{suffix}-admin")            # ADMINISTRATOR GLOBAL
    w["orgadmin_a"] = new_user(f"{suffix}-orgadminA")   # ADMINISTRATOR @ org A
    w["orgadmin_b"] = new_user(f"{suffix}-orgadminB")   # ADMINISTRATOR @ org B
    w["officer"] = new_user(f"{suffix}-officer")
    w["colleague"] = new_user(f"{suffix}-colleague")
    w["officer_b"] = new_user(f"{suffix}-officerB")
    w["reviewer"] = new_user(f"{suffix}-reviewer")
    w["supervisor"] = new_user(f"{suffix}-supervisor")
    w["supervisor_b"] = new_user(f"{suffix}-supervisorB")
    w["citizen"] = new_user(f"{suffix}-citizen")
    w["outsider"] = new_user(f"{suffix}-outsider")

    grant(w["admin"], "ADMINISTRATOR")
    grant(w["orgadmin_a"], "ADMINISTRATOR", "ORGANIZATION", w["org_a"])
    grant(w["orgadmin_b"], "ADMINISTRATOR", "ORGANIZATION", w["org_b"])
    grant(w["officer"], "FIELD_OFFICER", "ORGANIZATION", w["org_a"])
    grant(w["colleague"], "FIELD_OFFICER", "ORGANIZATION", w["org_a"])
    grant(w["officer_b"], "FIELD_OFFICER", "ORGANIZATION", w["org_b"])
    grant(w["reviewer"], "REVIEWER", "ORGANIZATION", w["org_a"])
    grant(w["supervisor"], "SUPERVISOR", "ORGANIZATION", w["org_a"])
    grant(w["supervisor_b"], "SUPERVISOR", "ORGANIZATION", w["org_b"])
    grant(w["citizen"], "CITIZEN")

    # project.create is a SUPERVISOR action; ADMINISTRATOR is not a superuser.
    w["project_a"] = new_project(w["supervisor"], w["admin"],
                                 f"SE {LABEL} {suffix} projectA", w["org_a"], w["unit_a"])
    w["project_b"] = new_project(w["supervisor_b"], w["admin"],
                                 f"SE {LABEL} {suffix} projectB", w["org_b"], w["unit_b"])
    w["claim_a"] = new_claim(w["project_a"], w["citizen"], f"se {LABEL} {suffix} claimA")
    w["activity_a"] = new_activity(w["project_a"], w["officer"])
    w["claim_a2"] = new_claim(w["project_a"], w["citizen"], f"se {LABEL} {suffix} claimA2")
    w["activity_a2"] = new_activity(w["project_a"], w["colleague"])
    w["claim_b"] = new_claim(w["project_b"], w["citizen"], f"se {LABEL} {suffix} claimB")
    w["activity_b"] = new_activity(w["project_b"], w["officer_b"])

    w["client_sync"] = new_api_client(w["admin"], f"se {LABEL} {suffix} sync",
                                      ["field.sync", "evidence.create"])
    w["client_narrow"] = new_api_client(w["admin"], f"se {LABEL} {suffix} narrow",
                                        ["field.sync"])

    r = create_assignment(w["admin"], w["officer"], w["project_a"],
                          claim_id=w["claim_a"], activity_id=w["activity_a"],
                          instructions="stage e baseline")
    assert r.status_code == 201, r.text
    w["assignment"] = r.json()["id"]
    tracked["assignments"].append(w["assignment"])

    r = create_assignment(w["admin"], w["colleague"], w["project_a"],
                          claim_id=w["claim_a2"], activity_id=w["activity_a2"])
    assert r.status_code == 201, r.text
    w["assignment_colleague"] = r.json()["id"]
    tracked["assignments"].append(w["assignment_colleague"])

    r = create_assignment(w["admin"], w["officer_b"], w["project_b"],
                          claim_id=w["claim_b"], activity_id=w["activity_b"])
    assert r.status_code == 201, r.text
    w["assignment_b"] = r.json()["id"]
    tracked["assignments"].append(w["assignment_b"])

    r = open(w, w["assignment"], device=f"pad-{suffix}")
    assert r.status_code == 201, r.text
    w["session"] = r.json()["id"]
    tracked["sessions"].append(w["session"])

    r = open(w, w["assignment_colleague"], actor=w["colleague"], device=f"pad2-{suffix}")
    assert r.status_code == 201, r.text
    w["session_colleague"] = r.json()["id"]
    tracked["sessions"].append(w["session_colleague"])
    return w


def open(w, assignment_id, device=None, actor=None, label=None):
    return open_session_http(actor or w["officer"], assignment_id, device, label)


def open_session_http(actor, assignment_id, device=None, label=None):
    import requests as rq
    from h import hdr
    body = {"assignment_id": assignment_id}
    if device:
        body["client_device_id"] = device
    if label:
        body["session_label"] = label
    return rq.post(f"{BASE}/api/v1/field/sessions", json=body, headers=hdr(actor), timeout=60)


def close(sid, actor, reason="done"):
    import requests as rq
    from h import BASE, hdr
    return rq.post(f"{BASE}/api/v1/field/sessions/{sid}/close", json={"reason": reason},
                   headers=hdr(actor), timeout=60)


def patch_assignment(aid, actor, status_value, reason):
    import requests as rq
    from h import BASE, hdr
    return rq.patch(f"{BASE}/api/v1/field/assignments/{aid}/status",
                    json={"status": status_value, "reason": reason},
                    headers=hdr(actor), timeout=60)


def resolve(op_id, actor, outcome="DISMISSED", note="stage e resolution"):
    import requests as rq
    from h import BASE, hdr
    return rq.post(f"{BASE}/api/v1/field/operations/{op_id}/resolve",
                   json={"outcome": outcome, "note": note},
                   headers=hdr(actor), timeout=60)


def get_capture(client_op, actor=None, client=None):
    import requests as rq
    from h import BASE, client_hdr, hdr
    headers = client_hdr(client) if client else hdr(actor)
    return rq.get(f"{BASE}/api/v1/field/captures/{client_op}", headers=headers, timeout=60)


def list_ops(actor=None, client=None, **params):
    import requests as rq
    from h import BASE, client_hdr, hdr
    headers = client_hdr(client) if client else hdr(actor)
    return rq.get(f"{BASE}/api/v1/field/operations", params=params, headers=headers, timeout=60)


def list_assignments(actor, **params):
    import requests as rq
    from h import BASE, hdr
    return rq.get(f"{BASE}/api/v1/field/assignments", params=params,
                  headers=hdr(actor), timeout=60)


def work(actor=None, client=None, **params):
    import requests as rq
    from h import BASE, client_hdr, hdr
    headers = client_hdr(client) if client else hdr(actor)
    return rq.get(f"{BASE}/api/v1/field/work", params=params, headers=headers, timeout=60)
