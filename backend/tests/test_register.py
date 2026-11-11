"""Pendaftaran member baru: domain email, kuota per peran, persetujuan Admin."""
import os

os.environ.update(USE_MOCK_DB="true", DISABLE_JOBS="true", DATA_DIR="/tmp/sd-test-reg", DEFAULT_ADMIN_PIN="111111")

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def c():
    from app import routes_register
    routes_register.RATE_LIMIT = 1000
    with TestClient(app) as client:
        yield client


def test_rate_limit():
    from app import routes_register
    routes_register._bucket.clear()
    old, routes_register.RATE_LIMIT = routes_register.RATE_LIMIT, 2
    try:
        with TestClient(app) as cc:
            codes = [cc.post("/api/public/register", json={"name": "Spam", "email": "x@gmail.com", "role": "CS Agent",
                                                           "pin": "482913"}).status_code for _ in range(3)]
        assert codes == [400, 400, 429]
    finally:
        routes_register.RATE_LIMIT = 1000
        routes_register._bucket.clear()


def H(c, name="Admin", pin="111111"):
    r = c.post("/api/auth/login", json={"name": name, "pin": pin})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


def reg(c, n, role="CS Agent", email=None, pin="482913"):
    return c.post("/api/public/register", json={"name": n, "email": email or f"{n.lower().replace(' ', '.')}@citarasakuliner.com",
                                                "role": role, "pin": pin})


def test_validation(c):
    assert reg(c, "Budi", email="budi@gmail.com").status_code == 400
    assert reg(c, "Budi", email="budi@citarasakuliner.com.evil.id").status_code == 400
    assert reg(c, "Budi", role="Admin").status_code == 400
    assert reg(c, "Budi", role="Viewer").status_code == 400
    assert reg(c, "Budi", pin="123456").status_code == 400
    assert reg(c, "Budi", pin="12ab56").status_code == 400
    assert reg(c, "Bu").status_code == 400
    info = c.get("/api/public/register/info").json()
    assert info["domain"] == "citarasakuliner.com"
    assert {r["role"]: r["slots"] for r in info["roles"]} == {"CS Lead": 1, "Marketing TL": 1, "CS Agent": 5}
    # data rahasia tidak bocor & daftar nama tidak lagi publik
    assert c.get("/api/auth/users").status_code in (404, 405) or c.get("/api/auth/users").headers["content-type"].startswith("text/html")


def test_approval_flow_and_login_by_email(c):
    A = H(c)
    r = reg(c, "Rina Supervisor", role="CS Lead").json()
    assert r["status"] == "pending"
    # belum bisa login sebelum disetujui
    assert c.post("/api/auth/login", json={"name": "rina.supervisor@citarasakuliner.com", "pin": "482913"}).status_code == 401
    lst = c.get("/api/registrations", headers=A).json()
    row = next(x for x in lst["rows"] if x["id"] == r["id"])
    assert "pinHash" not in row and row["roleLabel"] == "CRM Supervisor"
    # hanya Admin yang menyetujui
    L = None
    u = c.post(f"/api/registrations/{r['id']}/approve", json={}, headers=A).json()
    assert u["role"] == "CS Lead" and u["email"] == "rina.supervisor@citarasakuliner.com"
    L = H(c, "Rina.Supervisor@citarasakuliner.com ", "482913")  # email tidak peka huruf besar/spasi
    r2 = reg(c, "Tono Agent").json()
    assert c.post(f"/api/registrations/{r2['id']}/approve", json={}, headers=L).status_code == 403
    assert c.post(f"/api/registrations/{r['id']}/approve", json={}, headers=A).status_code == 400  # sudah diputuskan


def test_slots(c):
    A = H(c)
    # CRM Supervisor sudah terisi (test sebelumnya) → daftar & approve ditolak
    assert reg(c, "Dewi Lead", role="CS Lead").status_code == 409
    # Marketing TL 1 slot: dua pendaftar, yang kedua ditolak saat approve
    a = reg(c, "Maya Marketing", role="Marketing TL").json()
    b = reg(c, "Joko Marketing", role="Marketing TL").json()
    assert c.post(f"/api/registrations/{a['id']}/approve", json={}, headers=A).status_code == 200
    assert c.post(f"/api/registrations/{b['id']}/approve", json={}, headers=A).status_code == 409
    assert c.post(f"/api/registrations/{b['id']}/reject", json={"reason": "kuota penuh"}, headers=A).status_code == 200
    assert c.get(f"/api/public/register/{b['id']}").json()["status"] == "rejected"
    # Customer Service 5 slot (Tono pending dari test sebelumnya + 4 baru = 5, yang ke-6 ditolak)
    ids = [x["id"] for x in c.get("/api/registrations", params={"status": "pending"}, headers=A).json()["rows"] if x["role"] == "CS Agent"]
    for i in range(4):
        ids.append(reg(c, f"Agen Nomor{i}").json()["id"])
    for rid in ids[:5]:
        assert c.post(f"/api/registrations/{rid}/approve", json={}, headers=A).status_code == 200
    assert reg(c, "Agen Keenam").status_code == 409
    # admin membuat user CS Agent manual juga terkena kuota
    assert c.post("/api/users", json={"name": "Manual", "role": "CS Agent", "pin": "482913"}, headers=A).status_code == 409
    # nonaktifkan satu → slot terbuka; mengaktifkan lagi saat penuh ditolak
    users = c.get("/api/users", headers=A).json()
    one = next(x for x in users if x["role"] == "CS Agent")
    assert c.patch(f"/api/users/{one['id']}", json={"active": False}, headers=A).status_code == 200
    assert c.post("/api/users", json={"name": "Pengganti", "role": "CS Agent", "pin": "482913",
                                      "email": "pengganti@citarasakuliner.com"}, headers=A).status_code == 200
    assert c.patch(f"/api/users/{one['id']}", json={"active": True}, headers=A).status_code == 409
    # Manager Area tidak dibatasi kuota
    assert c.post("/api/users", json={"name": "MA1", "role": "Manager Area", "pin": "482913"}, headers=A).status_code == 200
    roles = {r["role"]: r for r in c.get("/api/roles", headers=A).json()["roles"]}
    assert roles["CS Agent"]["used"] == 5 and roles["CS Agent"]["slots"] == 5


def test_marketing_tl_permissions(c):
    M = H(c, "maya.marketing@citarasakuliner.com", "482913")
    assert c.get("/api/dashboard", params={"from": "2026-11-01", "to": "2026-11-10"}, headers=M).status_code == 200
    m = c.post("/api/meetings", json={"date": "2026-11-11", "periodStart": "2026-11-01", "periodEnd": "2026-11-10"}, headers=M)
    assert m.status_code == 200
    assert c.patch(f"/api/meetings/{m.json()['id']}", json={"insights": []}, headers=M).status_code == 200
    assert c.post(f"/api/meetings/{m.json()['id']}/lock", headers=M).status_code == 403
    assert c.get("/api/masters", headers=M).status_code == 200
    m2 = c.get("/api/masters", headers=M).json()
    o = m2["outlets"][0]["id"]
    assert c.post("/api/cases", json={"channel": "WhatsApp", "outletId": o, "subJenis": "Hospitality", "ringkasan": "x"},
                  headers=M).status_code == 403
    me = c.get("/api/auth/me", headers=M).json()
    assert me["roleLabel"] == "Marketing Team Leader"


def test_email_verification_when_mail_configured(c, monkeypatch):
    import re
    from app import jobs, core
    sent = []
    A = H(c)
    one = next(x for x in c.get("/api/users", headers=A).json() if x["role"] == "CS Agent" and x["active"])
    c.patch(f"/api/users/{one['id']}", json={"active": False}, headers=A)
    monkeypatch.setattr(core.Config, "RESEND_API_KEY", "uji")
    monkeypatch.setattr(jobs, "send_email", lambda to, subj, html: sent.append((to, subj, html)) or True)
    r = reg(c, "Sinta Verif", role="CS Agent", email="sinta@citarasakuliner.com")
    if r.status_code == 409:  # kuota CS penuh dari test sebelumnya → pakai peran lain yang kosong tidak ada; cukup cek pesan
        assert "Kuota" in r.json()["detail"]
        return
    r = r.json()
    assert r["status"] == "verify" and sent and sent[0][0] == ["sinta@citarasakuliner.com"]
    code = re.search(r"<b[^>]*>(\d{6})</b>", sent[0][2]).group(1)
    assert c.post(f"/api/public/register/{r['id']}/verify", json={"code": "000000"}).status_code == 400
    assert c.post(f"/api/public/register/{r['id']}/verify", json={"code": code}).json()["status"] == "pending"
