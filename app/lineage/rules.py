"""站码沿革核定纯规则。

输入均为已解析的 Python 基本结构（datetime 用 UTC），不触碰数据库与 Web，
便于单元测试与交接复核。术语：

- 站码 code：遥测站换号前后的业务编码（旧码/新码）。
- 逻辑站 site：同一只站在换号前后的统一身份，日账按 site 连成一条。
- 迁移单 migration：旧码 -> 新码的对照表，含新码启用时刻 activate_at；
  旧码停用时刻 deactivate_at 允许缺省（缺省即无法自动裁定并行段）。
- 并行窗口 parallel window：同一逻辑站旧码与新码均出现观测的时段。
"""
from collections import defaultdict

from app.normalize import instant
from app.errors import DomainError

# 时间区间端点语义：[start, end)，与日账半开区间保持一致。
USAGE = {
    "old_only": "仅旧码",
    "new_only": "仅新码",
    "parallel": "并行",
    "gap": "缺测",
}


def usage_windows(observations):
    """按站码汇总实际出现观测的活动窗口与逐时刻观测。

    observations: [{'code','time'(datetime),'level','inflow','outflow',
                    'flow_unit','version','_line','id'}]
    返回 {code: {'first':dt,'last':dt,'times':sorted[dt], 'rows':[row...]}}
    """
    windows = {}
    for row in observations:
        code = row["code"]
        item = windows.setdefault(code, {"first": row["time"], "last": row["time"],
                                         "times": [], "rows": []})
        item["first"] = min(item["first"], row["time"])
        item["last"] = max(item["last"], row["time"])
        item["times"].append(row["time"])
        item["rows"].append(row)
    for item in windows.values():
        item["times"] = sorted(set(item["times"]))
    return windows


def validate_migrations(migrations):
    """校验迁移单结构，返回归一化后的列表。

    每条：{'site','old_code','new_code','activate_at'(datetime|None),
           'deactivate_at'(datetime|None),'note'}
    """
    if not isinstance(migrations, list) or not migrations:
        raise DomainError("MIGRATION", "迁移对照表不能为空")
    norm = []
    seen_pairs = set()
    new_codes = set()
    old_codes = set()
    for raw in migrations:
        if not isinstance(raw, dict):
            raise DomainError("MIGRATION", "迁移单条目必须是对象")
        for key in ("site", "old_code", "new_code"):
            if not str(raw.get(key, "")).strip():
                raise DomainError("MIGRATION", f"迁移单缺少 {key}")
        site, old, new = raw["site"].strip(), raw["old_code"].strip(), raw["new_code"].strip()
        if old == new:
            raise DomainError("MIGRATION", f"站 {site} 新旧码相同，不构成换号")
        pair = (site, old, new)
        if pair in seen_pairs:
            raise DomainError("MIGRATION", f"迁移单重复：{old} -> {new}")
        seen_pairs.add(pair)
        if old in old_codes:
            raise DomainError("MIGRATION", f"旧码 {old} 在迁移单中重复出现")
        if new in new_codes:
            raise DomainError("MIGRATION", f"新码 {new} 被映射到多个逻辑站")
        old_codes.add(old)
        new_codes.add(new)
        activate = _opt_time(raw.get("activate_at"), "新码启用时刻")
        deactivate = _opt_time(raw.get("deactivate_at"), "旧码停用时刻")
        if activate is None:
            raise DomainError("MIGRATION", f"迁移单缺少新码启用时刻：{old} -> {new}")
        if deactivate is not None and deactivate < activate:
            raise DomainError("DEACTIVATION", "旧码停用时刻早于新码启用时刻")
        norm.append({"site": site, "old_code": old, "new_code": new,
                     "activate_at": activate, "deactivate_at": deactivate,
                     "note": str(raw.get("note", ""))})
    # 一个码不能在一条迁移里当新码、另一条里当旧码（连环换号需另开迁移单）。
    if old_codes & new_codes:
        raise DomainError("MIGRATION", "迁移链存在环接码，需拆分为独立换号单")
    return norm


def _opt_time(value, label):
    if value in (None, ""):
        return None
    try:
        return instant(value)
    except DomainError:
        raise DomainError("MIGRATION", f"{label}格式无效")


def build_segments(migration, windows, max_gap_hours):
    """按一条迁移单，把旧码/新码的实际活动切成带采用站码的沿革段。

    max_gap_hours 为最大允许采样间隔（小时），超过即判定真实缺测断点。
    返回 (segments, parallel_windows, continuity)。
    - segments：可直接采用的连续沿革段，每段标注 adopted_code。
    - parallel_windows：无法仅凭迁移单裁定的并行时段。
    - continuity：断点信息（并行窗口外侧若出现观测空洞在此暴露）。
    """
    old, new = migration["old_code"], migration["new_code"]
    old_w = windows.get(old)
    new_w = windows.get(new)
    if old_w is None and new_w is None:
        raise DomainError("LINEAGE", f"迁移单 {old} -> {new} 在观测数据中无任何站码记录")
    if old_w is None:
        # 只有新码：迁移单与数据不匹配，不能凭空补一段旧码沿革。
        raise DomainError("LINEAGE", f"缺少旧码 {old} 的观测，无法核定换号沿革")
    if new_w is None:
        raise DomainError("LINEAGE", f"新码 {new} 从未出现，换号沿革不成立")

    activate, deactivate = migration["activate_at"], migration["deactivate_at"]
    if new_w["first"] < activate:
        raise DomainError("MIGRATION",
                          f"新码 {new} 首测 {new_w['first'].isoformat()} 早于启用时刻 {activate.isoformat()}")

    parallel_start = max(activate, new_w["first"])
    parallel_end = min(old_w["last"], new_w["last"])
    has_parallel = parallel_start < parallel_end or (
        parallel_start == parallel_end and parallel_start in set(old_w["times"]) & set(new_w["times"]))

    segments = []
    parallel_windows = []
    before_activate = [r for r in old_w["rows"] if r["time"] < activate]

    if not has_parallel:
        # 无重叠：硬切在启用点。启用点前旧码、之后新码；启用点本身取新码。
        if before_activate:
            segments.append(_segment(migration, old, "old_only",
                                     min(r["time"] for r in before_activate),
                                     max(r["time"] for r in before_activate), before_activate))
        post_rows = [r for r in new_w["rows"] if r["time"] >= activate]
        if post_rows:
            segments.append(_segment(migration, new, "new_only",
                                     min(r["time"] for r in post_rows),
                                     max(r["time"] for r in post_rows), post_rows))
        tail_old = [r for r in old_w["rows"] if r["time"] >= activate]
        if tail_old:
            # 新码已启用却仍只有旧码延续：没有第二个码可对照，按旧码保留并标注。
            segments.append(_segment(migration, old, "old_only",
                                     min(r["time"] for r in tail_old),
                                     max(r["time"] for r in tail_old), tail_old,
                                     note="新码启用后旧码仍单独延续"))
        return segments, parallel_windows, _continuity(segments, (), max_gap_hours)

    if deactivate is None:
        # 迁移单没写清旧码何时停用 -> 整个并行时段无法裁定。
        parallel_windows.append(_parallel(migration, old, new,
                                          parallel_start, parallel_end, old_w, new_w,
                                          decidable=False,
                                          reason="迁移单未登记旧码停用时刻，并行时段无法裁定"))
        # 并行窗口两侧仍然可以确认：窗口前旧码、窗口后新码。
        if before_activate:
            segments.append(_segment(migration, old, "old_only",
                                     min(r["time"] for r in before_activate),
                                     max(r["time"] for r in before_activate), before_activate))
        after = [r for r in new_w["rows"] if r["time"] > parallel_end]
        if after:
            segments.append(_segment(migration, new, "new_only",
                                     min(r["time"] for r in after),
                                     max(r["time"] for r in after), after))
        return segments, parallel_windows, _continuity(segments, parallel_windows, max_gap_hours)

    # 登记了停用时刻：并行期 [activate, deactivate) 按规则裁定。
    decidable, detail = _adjudicate_parallel(migration, old_w, new_w, deactivate)
    window = _parallel(migration, old, new, parallel_start,
                       min(parallel_end, deactivate), old_w, new_w,
                       decidable=decidable, reason=detail)
    parallel_windows.append(window)

    if before_activate:
        segments.append(_segment(migration, old, "old_only",
                                 min(r["time"] for r in before_activate),
                                 max(r["time"] for r in before_activate), before_activate))
    if decidable:
        # 并行期可裁定：停用前采用旧码、停用起采用新码，逐刻去重，不产生重复日账。
        old_phase = [r for r in old_w["rows"] if activate <= r["time"] < deactivate]
        bridge_new = [r for r in new_w["rows"] if activate <= r["time"] < deactivate]
        chosen = _dedupe_window(old_phase, bridge_new, old, new)
        if chosen:
            segments.append(_segment(migration, "MIXED", "parallel",
                                     min(r["time"] for r in chosen),
                                     max(r["time"] for r in chosen), chosen,
                                     note=detail))
        new_phase = [r for r in new_w["rows"] if r["time"] >= deactivate]
        if new_phase:
            segments.append(_segment(migration, new, "new_only",
                                     min(r["time"] for r in new_phase),
                                     max(r["time"] for r in new_phase), new_phase))
    else:
        # 停用时刻已登记但并行数据矛盾（同刻新旧值不一致），窗口挂起，两侧确认段照算。
        after = [r for r in new_w["rows"] if r["time"] > parallel_end]
        if after:
            segments.append(_segment(migration, new, "new_only",
                                     min(r["time"] for r in after),
                                     max(r["time"] for r in after), after))
    return segments, parallel_windows, _continuity(segments, parallel_windows, max_gap_hours)


def _adjudicate_parallel(migration, old_w, new_w, deactivate):
    """停用时刻已知时，逐刻比对并行观测是否可裁定。

    同刻新旧两码的水位/流量三元组一致才允许去重采信；任一时刻矛盾即整窗挂起。
    """
    old_by = {r["time"]: r for r in old_w["rows"]}
    new_by = {r["time"]: r for r in new_w["rows"]}
    common = sorted(set(old_by) & set(new_by))
    for t in common:
        a, b = old_by[t], new_by[t]
        sig = lambda r: (str(r.get("level")), str(r.get("inflow")), str(r.get("outflow")))
        if sig(a) != sig(b):
            return False, f"并行时刻 {t.isoformat()} 新旧码水文值矛盾，窗口挂起待人工裁定"
    stray_old = [r for r in old_w["rows"] if r["time"] >= deactivate]
    if stray_old:
        return False, "旧码在登记停用时刻之后仍有观测，停用时刻存疑"
    if not common:
        return False, "并行期内新旧码无同刻观测，无法交叉验证"
    return True, f"并行 {len(common)} 个同刻观测一致，停用前采旧码、停用起采新码"


def _dedupe_window(old_phase, bridge_new, old, new):
    """并行可裁定窗口内逐刻只保留一条观测，杜绝双算。"""
    chosen = {}
    for r in old_phase:
        chosen.setdefault(r["time"], {**r, "adopted_code": old})
    for r in bridge_new:
        # 同刻优先旧码（停用前旧码为正式码），新码仅作交叉验证留痕。
        chosen.setdefault(r["time"], {**r, "adopted_code": new})
    return [chosen[t] for t in sorted(chosen)]


def _segment(migration, adopted_code, kind, start, end, rows, note=""):
    return {
        "site": migration["site"], "kind": kind, "kind_label": USAGE[kind],
        "adopted_code": adopted_code, "start": start, "end": end,
        "row_lines": sorted(r.get("_line", "") for r in rows),
        "note": note or migration.get("note", ""),
    }


def _parallel(migration, old, new, start, end, old_w, new_w, decidable, reason):
    return {
        "site": migration["site"], "old_code": old, "new_code": new,
        "start": start, "end": end, "decidable": decidable,
        "state": "可裁定" if decidable else "待人工裁定",
        "old_lines": sorted(r.get("_line", "") for r in old_w["rows"]
                            if start <= r["time"] <= end),
        "new_lines": sorted(r.get("_line", "") for r in new_w["rows"]
                            if start <= r["time"] <= end),
        "reason": reason,
    }


def _continuity(segments, parallel_windows=(), max_gap_hours=2):
    """检查逻辑站沿革是否在换号点断成缺测。

    连续性以实际观测时刻覆盖为准：相邻确认段端点间隔不超过 max_gap_hours
    视为衔接，超过才是真实缺测；可裁定并行窗口是衔接段不计断点，
    只有挂起窗口或真实时间空洞才阻断。
    """
    breaks = []
    for w in parallel_windows:
        if not w["decidable"]:
            breaks.append({"after": w["start"].isoformat(), "before": w["end"].isoformat(),
                           "blocked": w["reason"]})

    by_site = defaultdict(list)
    for seg in segments:
        by_site[seg["site"]].append(seg)
    for site, segs in by_site.items():
        segs.sort(key=lambda s: s["start"])
        for a, b in zip(segs, segs[1:]):
            if a["end"] < b["start"]:
                gap_hours = (b["start"] - a["end"]).total_seconds() / 3600
                if gap_hours > float(max_gap_hours):
                    breaks.append({"site": site, "after": a["end"].isoformat(),
                                   "before": b["start"].isoformat()})
    return {"breaks": breaks, "continuous": not breaks}


def canonical_observations(observations, migrations, result):
    """把每条观测映射到逻辑站并标注采用/挂起，供日账续算与原始追溯。

    返回 {'canonical':[...], 'suspended':[...], 'unmapped':[...]}。
    - canonical：进入日账的观测，station 改为逻辑站，station_code 保留采用码，
      raw_code 保留原始站码；可裁定并行窗口内同刻只保留一条，杜绝双算。
    - suspended：落在无法裁定并行窗口内的观测，不进日账（避免双算/缺测误判）。
    - unmapped：迁移单未登记站码的观测。
    """
    code_to_site = {}
    for m in migrations:
        code_to_site[m["old_code"]] = m["site"]
        code_to_site[m["new_code"]] = m["site"]
    blocked = set()
    for w in result.get("parallel_windows", []):
        if not w["decidable"]:
            for ln in w["old_lines"] + w["new_lines"]:
                blocked.add(ln)

    canonical, suspended, unmapped = [], [], []
    # 同逻辑站同刻去重：旧码优先（停用前旧码为正式码），新码留痕不重复入账。
    chosen = {}
    for row in observations:
        site = code_to_site.get(row["code"])
        if site is None:
            unmapped.append({**row, "reason": "站码未登记于迁移单"})
            continue
        out = dict(row)
        out["station"] = site
        out["raw_code"] = row["code"]
        out["station_code"] = row.get("adopted_code", row["code"])
        if row.get("_line", "") in blocked:
            suspended.append({**out, "suspend_reason": "PARALLEL"})
            continue
        key = (site, row["time"])
        incumbent = chosen.get(key)
        if incumbent is None:
            chosen[key] = out
            continue
        # 同刻已有一条：旧码优先，否则保留先到者；被去重者仍可经 raw_code 追溯。
        if incumbent["raw_code"] != row["code"]:
            old_code = next((m["old_code"] for m in migrations if m["site"] == site), None)
            if row["code"] == old_code and incumbent["raw_code"] != old_code:
                out["deduped"] = incumbent.get("deduped", []) + [
                    {"line": incumbent.get("_line", ""), "raw_code": incumbent["raw_code"]}]
                chosen[key] = out
            else:
                incumbent.setdefault("deduped", []).append(
                    {"line": row.get("_line", ""), "raw_code": row["code"]})
    canonical = [chosen[k] for k in sorted(chosen, key=lambda k: (k[0], k[1]))]
    return {"canonical": canonical, "suspended": suspended, "unmapped": unmapped}


def fingerprint(migrations, observations_digest):
    """换号指纹：标识“同一次换号”的稳定身份。

    只取逻辑站与新旧码对照关系 + 观测摘要，刻意排除停用时刻/备注等会在补裁
    过程中变更的字段，使“挂起 -> 补登停用时刻续算”落在同一版本线上；
    不同换号（码对或观测不同）指纹必然不同，杜绝跨换号串号与重复日账。
    """
    import hashlib, json
    identity = [{"site": m["site"], "old_code": m["old_code"], "new_code": m["new_code"]}
                for m in sorted(migrations, key=lambda m: (m["site"], m["old_code"]))]
    payload = json.dumps({"identity": identity, "digest": observations_digest},
                         sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()[:20]
