"""站码沿革核定编排与日账续算。

设计约束（对应交接要求）：
1. 每段标明采用站码；无法裁定的并行时段单列，不进日账，杜绝双算与硬切缺测。
2. 原始站码 raw_code 全程保留，可追溯到 CSV 行号。
3. 核定失败不覆盖已确认沿革（store 层版本保留），从已确认段的水位线续算。
4. 同一换号指纹重跑复用同一沿革版本，不新增重复日账。
"""
import hashlib

from app.lineage.inputs import parse_observations, parse_migrations
from app.lineage.rules import (usage_windows, validate_migrations, build_segments,
                               canonical_observations, fingerprint)
from app.modules.m3_integrate.rules import integrate
from app.modules.m5_budget.rules import day_budget
from app.modules.m4_storage.service import level_to_volume
from app.normalize import number, serial
from app.errors import DomainError
from app.config import LINEAGE_RULE_VERSION


def digest_raw(raw):
    """对解码后的规范化文本取摘要。

    先经 decode 归一编码（utf-8-sig/gb18030），避免 BOM、CRLF、GB18030 等
    传输差异把同一次换号拆成两条版本线。
    """
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    from app.normalize import decode
    text, _ = decode(raw)
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def adjudicate(obs_raw, mig_raw, params, prior=None):
    """纯内存核定，不写库。prior 为上一版沿革（可为 None）。"""
    params = params or {}
    max_gap = number(params.get("max_gap_hours", "2"))
    if max_gap <= 0 or max_gap > 24:
        raise DomainError("RANGE", "缺口参数无效")
    curve = _curve(params)

    obs = parse_observations(obs_raw)
    mig = parse_migrations(mig_raw)
    observations, quarantine = obs["observations"], obs["quarantine"] + mig["quarantine"]
    migrations = validate_migrations(mig["migrations"])

    windows = usage_windows(observations)
    segments, parallel_windows, continuity = [], [], {"breaks": [], "continuous": True}
    for migration in migrations:
        seg, win, cont = build_segments(migration, windows, max_gap)
        segments.extend(seg)
        parallel_windows.extend(win)
        continuity["breaks"].extend(cont["breaks"])
    continuity["continuous"] = not continuity["breaks"]

    mapping = canonical_observations(observations, migrations,
                                     {"parallel_windows": parallel_windows})
    quarantine.extend({"line": r.get("_line", ""), "key": r.get("id", ""),
                       "code": "UNMAPPED", "reason": "未登记的业务编码",
                       "detail": r.get("reason", ""), "raw": {k: v for k, v in r.items()
                                                              if not k.startswith("_")}}
                      for r in mapping["unmapped"])

    # 挂起的并行观测不进入日账；其余按逻辑站连成一条账。
    canonical = mapping["canonical"]
    flows, gaps = integrate(canonical, max_gap)
    budgets = day_budget(flows, curve, level_to_volume)

    blocked_lines = {r["_line"] for r in mapping["suspended"]}
    confirmed = _confirmed_watermark(canonical, prior)

    result = {
        "rules": LINEAGE_RULE_VERSION,
        "input_count": obs["input_count"],
        "canonical_count": len(canonical),
        "suspended_count": len(mapping["suspended"]),
        "segments": serial(segments),
        "parallel_windows": serial(parallel_windows),
        "continuity": serial(continuity),
        "canonical": serial(canonical),
        "suspended": serial(mapping["suspended"]),
        "quarantine": serial(quarantine),
        "flows": serial(flows),
        "gaps": serial(gaps),
        "budgets": serial(budgets),
        "confirmed_watermark": serial(confirmed),
        "blocked_lines": sorted(blocked_lines),
        "adjudicated": all(w["decidable"] for w in parallel_windows) and continuity["continuous"],
        "fingerprint": fingerprint(migrations, digest_raw(obs_raw)),
        "migration_digest": digest_raw(mig_raw),
    }
    return result


def _curve(params):
    from app.modules.m2_curve.rules import validate_curve
    from app.config import DEFAULTS
    return validate_curve(params.get("curve", DEFAULTS["curve"]))


def _confirmed_watermark(canonical, prior):
    """每个逻辑站已确认段的末时刻；有旧版时从旧版水位线续算，不回退。"""
    marks = {}
    for row in canonical:
        site = row["station"]
        marks[site] = max(marks.get(site, row["time"]), row["time"])
    if prior:
        for site, t in (prior.get("confirmed_watermark") or {}).items():
            marks[site] = max(marks.get(site, t), t)
    return marks
