import pytest
from decimal import Decimal as D
from datetime import timezone, timedelta

from app.errors import DomainError
from app.normalize import instant
from app.lineage.rules import (usage_windows, validate_migrations, build_segments,
                               canonical_observations, fingerprint)
from app.lineage.inputs import parse_observations, parse_migrations
from app.lineage.service import adjudicate
from app.config import SAMPLES

OBS = (SAMPLES / "lineage_observations.csv").read_bytes()
OBS_CONFLICT = (SAMPLES / "lineage_observations_conflict.csv").read_bytes()
MIG_PENDING = (SAMPLES / "lineage_migration_pending.csv").read_bytes()
MIG_DECIDED = (SAMPLES / "lineage_migration_decided.csv").read_bytes()
TZ = timezone(timedelta(hours=8))


def _windows():
    return usage_windows(parse_observations(OBS)["observations"])


def test_usage_windows_cover_two_codes():
    w = _windows()
    assert set(w) == {"QL01", "QL2026"}
    # 旧码贯穿到并行期末（11-17 15:00 +08），新码自启用点起。
    assert w["QL01"]["last"] == instant("2026-11-17T15:00:00+08:00")
    assert w["QL2026"]["first"] == instant("2026-11-17T08:00:00+08:00")


def test_migration_requires_activation():
    with pytest.raises(DomainError, match="启用时刻"):
        validate_migrations([{"site": "青岚库", "old_code": "A", "new_code": "B",
                              "activate_at": None}])


def test_migration_rejects_same_code_and_duplicate():
    base = {"site": "s", "old_code": "A", "new_code": "B",
            "activate_at": "2026-11-17T08:00:00+08:00"}
    with pytest.raises(DomainError, match="新旧码相同"):
        validate_migrations([{**base, "old_code": "B", "new_code": "B"}])
    with pytest.raises(DomainError):
        validate_migrations([base, {**base, "new_code": "C"}])


def test_migration_rejects_deactivate_before_activate():
    with pytest.raises(DomainError, match="停用"):
        validate_migrations([{"site": "s", "old_code": "A", "new_code": "B",
                              "activate_at": "2026-11-17T08:00:00+08:00",
                              "deactivate_at": "2026-11-17T07:00:00+08:00"}])


def test_pending_window_is_blocked_when_deactivate_missing():
    # 迁移单没写清旧码何时停用 -> 并行段必须挂起，不能硬切、不能双算。
    r = adjudicate(OBS, MIG_PENDING, {})
    assert r["adjudicated"] is False
    win = r["parallel_windows"][0]
    assert win["decidable"] is False
    assert win["start"] == instant("2026-11-17T08:00:00+08:00").isoformat()
    assert win["end"] == instant("2026-11-17T15:00:00+08:00").isoformat()
    # 两侧确认段仍标明采用站码：窗口前旧码、窗口后新码。
    adopted = [(s["kind"], s["adopted_code"]) for s in r["segments"]]
    assert ("old_only", "QL01") in adopted and ("new_only", "QL2026") in adopted


def test_pending_window_suspends_both_codes_no_double_count():
    r = adjudicate(OBS, MIG_PENDING, {})
    # 并行 8 个时刻 × 新旧两码 = 16 行全部挂起，不进日账。
    assert r["suspended_count"] == 16
    suspended_codes = {x["raw_code"] for x in r["suspended"]}
    assert suspended_codes == {"QL01", "QL2026"}
    # 挂起行不参与积分，日账只覆盖确认段，不会把并行算两遍。
    assert r["canonical_count"] == 41
    # 11-17 仅剩窗口后的新码确认段，覆盖不足 24h 标缺测；并行 8 刻绝不重复入账。
    tail = next(b for b in r["budgets"] if b["date"] == "2026-11-17")
    assert tail["state"] == "缺测" and tail["coverage_hours"] == "15.0"


def test_decided_window_dedupes_to_one_series():
    # 停用时刻补登后：并行 8 刻同值，逐刻去重，49 个时刻只留 49 条。
    r = adjudicate(OBS, MIG_DECIDED, {})
    assert r["adjudicated"] is True
    assert r["canonical_count"] == 49
    deduped = sum(len(x.get("deduped", [])) for x in r["canonical"])
    assert deduped == 8  # 新码的 8 条并行观测被去重，旧码为正式码
    # 日账连成一条，两个自然日均完整 24h，无重复。
    assert [(b["date"], b["state"], b["coverage_hours"]) for b in r["budgets"]] == [
        ("2026-11-16", "完整", "24.0"), ("2026-11-17", "完整", "24.0")]


def test_raw_code_remains_traceable():
    r = adjudicate(OBS, MIG_DECIDED, {})
    by_time = {x["time"]: x for x in r["canonical"]}
    # 并行期采用旧码，但原始新码观测仍记录在 deduped 留痕里。
    bridge = by_time[instant("2026-11-17T10:00:00+08:00").isoformat()]
    assert bridge["station_code"] == "QL01"
    assert bridge["raw_code"] == "QL01"
    assert any(d["raw_code"] == "QL2026" for d in bridge.get("deduped", []))
    # 停用后采用新码，逻辑站统一为青岚库。
    after = by_time[instant("2026-11-17T16:00:00+08:00").isoformat()]
    assert after["station_code"] == "QL2026" and after["station"] == "青岚库"


def test_conflicting_parallel_values_block_window():
    r = adjudicate(OBS_CONFLICT, MIG_DECIDED, {})
    assert r["adjudicated"] is False
    win = r["parallel_windows"][0]
    assert win["decidable"] is False and "矛盾" in win["reason"]
    assert r["suspended_count"] == 16


def test_fingerprint_stable_across_lifecycle_but_distinct_per_change():
    a = adjudicate(OBS, MIG_PENDING, {})
    b = adjudicate(OBS, MIG_DECIDED, {})
    # 同一次换号：补登停用时刻不换指纹，才能在同一版本线上续算。
    assert a["fingerprint"] == b["fingerprint"]
    c = adjudicate(OBS_CONFLICT, MIG_DECIDED, {})
    assert c["fingerprint"] != a["fingerprint"]


def test_unmapped_code_is_quarantined():
    # 追加一条迁移单未登记的站码观测 -> 隔离为 UNMAPPED，不影响青岚库沿革。
    extra = "90001,邻库,XG99,2026-11-16T00:00:00+08:00,101.0,2,1,m3/s,1"
    obs = OBS.decode("utf-8").rstrip() + "\n" + extra
    r = adjudicate(obs, MIG_DECIDED, {})
    assert any(q["code"] == "UNMAPPED" for q in r["quarantine"])
    assert r["adjudicated"] is True


def test_hard_cut_without_overlap_stays_continuous():
    rows = ["id,station,code,time,level,inflow,outflow,flow_unit,version"]
    n = 1
    for h in range(24):
        rows.append(f"{n},青岚库,QL01,2026-11-16T{h:02d}:00:00+08:00,101.0,2,1,m3/s,1"); n += 1
    for h in range(24):
        rows.append(f"{n},青岚库,QL9,2026-11-17T{h:02d}:00:00+08:00,102.0,2,1,m3/s,1"); n += 1
    mig = ("site,old_code,new_code,activate_at,deactivate_at,note\n"
           "青岚库,QL01,QL9,2026-11-17T00:00:00+08:00,,硬切\n")
    r = adjudicate("\n".join(rows), mig, {})
    assert r["adjudicated"] is True and r["parallel_windows"] == []
    assert {s["adopted_code"] for s in r["segments"]} == {"QL01", "QL9"}


def test_stray_old_code_after_deactivation_blocks():
    obs = ("id,station,code,time,level,inflow,outflow,flow_unit,version\n"
           "1,库,A1,2026-11-17T07:00:00+08:00,101.0,2,1,m3/s,1\n"
           "2,库,A1,2026-11-17T08:00:00+08:00,101.1,2,1,m3/s,1\n"
           "3,库,A9,2026-11-17T08:00:00+08:00,101.1,2,1,m3/s,1\n"
           "4,库,A1,2026-11-17T17:00:00+08:00,101.2,2,1,m3/s,1\n"
           "5,库,A9,2026-11-17T17:00:00+08:00,101.2,2,1,m3/s,1")
    mig = ("site,old_code,new_code,activate_at,deactivate_at,note\n"
           "库,A1,A9,2026-11-17T08:00:00+08:00,2026-11-17T16:00:00+08:00,停用后旧码仍发\n")
    r = adjudicate(obs, mig, {})
    assert r["adjudicated"] is False
    assert "停用时刻存疑" in r["parallel_windows"][0]["reason"]


def test_observation_hole_beyond_max_gap_breaks_continuity():
    obs = ("id,station,code,time,level,inflow,outflow,flow_unit,version\n"
           "1,库,A1,2026-11-16T00:00:00+08:00,101.0,2,1,m3/s,1\n"
           "2,库,A9,2026-11-17T12:00:00+08:00,101.2,2,1,m3/s,1")
    mig = ("site,old_code,new_code,activate_at,deactivate_at,note\n"
           "库,A1,A9,2026-11-17T00:00:00+08:00,,硬切大间隔\n")
    r = adjudicate(obs, mig, {"max_gap_hours": "2"})
    assert r["adjudicated"] is False
    assert r["continuity"]["continuous"] is False and r["continuity"]["breaks"]


def test_l_per_second_normalized_before_ledger():
    obs = ("id,station,code,time,level,inflow,outflow,flow_unit,version\n"
           "1,甲库,A1,2026-11-16T00:00:00+08:00,101.0,2000,1500,L/s,1")
    parsed = parse_observations(obs)["observations"][0]
    assert parsed["flow_unit"] == "m3/s"
    assert parsed["inflow"] == D("2") and parsed["outflow"] == D("1.5")
