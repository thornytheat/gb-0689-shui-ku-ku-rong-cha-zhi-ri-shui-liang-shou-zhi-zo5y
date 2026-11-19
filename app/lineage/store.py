"""站码沿革持久化：版本保留、指纹幂等、日账去重。

- 同一换号指纹重跑：复用既有沿革版本，不新增重复日账。
- 核定失败（adjudicated=False）：状态记为挂起，绝不覆盖已确认沿革；
  已确认段水位线参与下次续算。
- 日账以 (逻辑站, 日期) 为业务唯一键，重复换号运行不会产生第二条。
"""
import json

from app import store as base
from app.errors import DomainError


def _db():
    db = base.connection()
    db.execute("""CREATE TABLE IF NOT EXISTS lineage_versions(
        fingerprint TEXT PRIMARY KEY,
        site TEXT NOT NULL,
        version INTEGER NOT NULL,
        status TEXT NOT NULL,
        payload TEXT NOT NULL,
        created TEXT NOT NULL DEFAULT (datetime('now')))""")
    db.execute("""CREATE TABLE IF NOT EXISTS lineage_ledgers(
        fingerprint TEXT NOT NULL,
        site TEXT NOT NULL,
        date TEXT NOT NULL,
        payload TEXT NOT NULL,
        PRIMARY KEY(fingerprint, site, date))""")
    return db


def save(result, site):
    """按指纹保存核定结果。返回 (payload, reused)。

    成功（adjudicated）才推进版本号；失败只登记挂起快照并保留旧版沿革。
    """
    fp = result["fingerprint"]
    with _db() as db:
        existing = db.execute("SELECT version,status,payload FROM lineage_versions WHERE fingerprint=?",
                              (fp,)).fetchone()
        if existing is not None:
            # 同一换号重跑：原样返回既有版本，日账唯一键保证不重复入账。
            payload = json.loads(existing["payload"])
            payload["reused"] = True
            return payload, True

        if result["adjudicated"]:
            version, status = 1, "已核定"
        else:
            version, status = 0, "挂起待裁定"
        db.execute("INSERT INTO lineage_versions(fingerprint,site,version,status,payload) VALUES(?,?,?,?,?)",
                   (fp, site, version, status, json.dumps(result, ensure_ascii=False)))
        if result["adjudicated"]:
            _upsert_ledgers(db, fp, result["budgets"])
        payload = dict(result)
        payload["reused"] = False
        payload["version"] = version
        payload["status"] = status
        return payload, False


def _upsert_ledgers(db, fingerprint, budgets):
    for row in budgets:
        db.execute("INSERT OR IGNORE INTO lineage_ledgers(fingerprint,site,date,payload) VALUES(?,?,?,?)",
                   (fingerprint, row["station"], row["date"],
                    json.dumps(row, ensure_ascii=False)))


def _merge_watermark(prior_marks, new_marks):
    """续算水位线：同逻辑站取新旧两版的较大时刻，保证不回退。"""
    merged = dict(prior_marks or {})
    for site, t in (new_marks or {}).items():
        merged[site] = max(merged.get(site, t), t)
    return merged


def resume(fingerprint, new_result):
    """挂起沿革补裁后续算：保留已确认段，仅在可裁定时推进版本。

    新结果指纹必须与挂起快照同源（迁移单+输入摘要一致），否则拒绝，防止串号。
    """
    with _db() as db:
        row = db.execute("SELECT version,status,payload FROM lineage_versions WHERE fingerprint=?",
                         (fingerprint,)).fetchone()
        if row is None:
            raise DomainError("NOT_FOUND", "沿革版本不存在", 404)
        if row["status"] == "已核定":
            payload = json.loads(row["payload"])
            payload["reused"] = True
            return payload, True
        if new_result["fingerprint"] != fingerprint:
            raise DomainError("FINGERPRINT", "换号指纹不一致，禁止跨换号续算")
        prior = json.loads(row["payload"])
        if not new_result["adjudicated"]:
            # 仍无法裁定：旧版（挂起快照）原样保留，确认段水位线不回退。
            prior["reused"] = True
            return prior, True
        # 从旧版已确认段水位线续算：合并后水位线只增不减，不回退。
        from app.normalize import serial
        new_result["confirmed_watermark"] = serial(
            _merge_watermark(prior.get("confirmed_watermark"),
                             new_result.get("confirmed_watermark")))
        version = row["version"] + 1 if row["version"] else 1
        db.execute("UPDATE lineage_versions SET version=?,status=?,payload=? WHERE fingerprint=?",
                   (version, "已核定", json.dumps(new_result, ensure_ascii=False), fingerprint))
        _upsert_ledgers(db, fingerprint, new_result["budgets"])
        payload = dict(new_result)
        payload["reused"] = False
        payload["version"] = version
        payload["status"] = "已核定"
        return payload, False


def fetch(fingerprint):
    with _db() as db:
        row = db.execute("SELECT * FROM lineage_versions WHERE fingerprint=?", (fingerprint,)).fetchone()
    if row is None:
        raise DomainError("NOT_FOUND", "沿革版本不存在", 404)
    payload = json.loads(row["payload"])
    payload["version"] = row["version"]
    payload["status"] = row["status"]
    return payload


def ledgers(fingerprint):
    with _db() as db:
        rows = db.execute("SELECT payload FROM lineage_ledgers WHERE fingerprint=? ORDER BY site,date",
                          (fingerprint,)).fetchall()
    return [json.loads(r["payload"]) for r in rows]


def history():
    with _db() as db:
        rows = db.execute("""SELECT fingerprint,site,version,status,created
                             FROM lineage_versions ORDER BY rowid DESC LIMIT 100""").fetchall()
    return [dict(r) for r in rows]
