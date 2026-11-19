import pytest

from app.main import create_app
from app.config import SAMPLES
from app.lineage import store
from app.lineage.service import adjudicate

OBS = (SAMPLES / "lineage_observations.csv").read_bytes()
MIG_PENDING = (SAMPLES / "lineage_migration_pending.csv").read_bytes()
MIG_DECIDED = (SAMPLES / "lineage_migration_decided.csv").read_bytes()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    return create_app().test_client()


def _post(client, obs, mig, url="/api/lineage"):
    return client.post(url, json={"observations": obs.decode("utf-8"),
                                  "migrations": mig.decode("utf-8")})


def test_failed_adjudication_keeps_pending_and_no_ledger(client):
    reply = _post(client, OBS, MIG_PENDING)
    assert reply.status_code == 200
    body = reply.json
    assert body["adjudicated"] is False
    assert body["version"] == 0 and body["status"] == "挂起待裁定"
    assert store.ledgers(body["fingerprint"]) == []


def test_same_renumber_rerun_is_idempotent_no_duplicate(client):
    first = _post(client, OBS, MIG_DECIDED).json
    second = _post(client, OBS, MIG_DECIDED).json
    assert first["fingerprint"] == second["fingerprint"]
    assert second["reused"] is True
    ledgers = store.ledgers(first["fingerprint"])
    # 同一 (逻辑站,日期) 唯一键，重跑不新增重复日账。
    keys = [(x["station"], x["date"]) for x in ledgers]
    assert len(keys) == len(set(keys)) == 2


def test_resume_from_pending_promotes_version_and_writes_ledger(client):
    pending = _post(client, OBS, MIG_PENDING).json
    fp = pending["fingerprint"]
    # 旧版（挂起）保留：仍可取回，版本号 0。
    assert store.fetch(fp)["version"] == 0
    reply = client.post(f"/api/lineage/resume/{fp}",
                        json={"observations": OBS.decode(),
                              "migrations": MIG_DECIDED.decode()})
    assert reply.status_code == 200
    decided = reply.json
    assert decided["fingerprint"] == fp  # 同一换号版本线
    assert decided["version"] == 1 and decided["status"] == "已核定"
    assert len(store.ledgers(fp)) == 2


def test_resume_rejects_cross_fingerprint(client):
    pending = _post(client, OBS, MIG_PENDING).json
    other_obs = (SAMPLES / "lineage_observations_conflict.csv").read_bytes()
    reply = client.post(f"/api/lineage/resume/{pending['fingerprint']}",
                        json={"observations": other_obs.decode(),
                              "migrations": MIG_DECIDED.decode()})
    assert reply.status_code == 422 and reply.json["code"] == "FINGERPRINT"


def test_resume_rerun_after_decision_reuses(client):
    pending = _post(client, OBS, MIG_PENDING).json
    fp = pending["fingerprint"]
    client.post(f"/api/lineage/resume/{fp}",
                json={"observations": OBS.decode(), "migrations": MIG_DECIDED.decode()})
    again = client.post(f"/api/lineage/resume/{fp}",
                        json={"observations": OBS.decode(), "migrations": MIG_DECIDED.decode()}).json
    assert again["reused"] is True
    assert len(store.ledgers(fp)) == 2


def test_resume_continues_confirmed_watermark_without_regression(client):
    pending = _post(client, OBS, MIG_PENDING).json
    fp = pending["fingerprint"]
    prior_mark = pending["confirmed_watermark"]["青岚库"]
    decided = client.post(f"/api/lineage/resume/{fp}",
                          json={"observations": OBS.decode(),
                                "migrations": MIG_DECIDED.decode()}).json
    # 续算后的水位线不得早于挂起版已确认段水位线（只增不减、不回退）。
    assert decided["confirmed_watermark"]["青岚库"] >= prior_mark
    assert decided["confirmed_watermark"]["青岚库"] == "2026-11-17T16:00:00+00:00"


def test_evidence_csv_and_page(client):
    body = _post(client, OBS, MIG_DECIDED).json
    fp = body["fingerprint"]
    csv_reply = client.get(f"/api/lineage/{fp}/evidence.csv")
    assert csv_reply.status_code == 200
    assert "采用站码" in csv_reply.text and "QL01" in csv_reply.text
    assert client.get("/lineage").status_code == 200
    assert client.get("/api/lineage").status_code == 200
    assert client.get(f"/api/lineage/{fp}/ledgers").status_code == 200


def test_invalid_migration_returns_422(client):
    bad_mig = "site,old_code,new_code,activate_at,deactivate_at,note\n青岚库,QL01,QL01,,,\n"
    reply = _post(client, OBS, bad_mig.encode())
    assert reply.status_code == 422
    assert reply.json["code"] == "MIGRATION"


def test_unknown_fingerprint_404(client):
    assert client.get("/api/lineage/nope").status_code == 404
