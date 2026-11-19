"""站码沿革专用输入解析。

观测 CSV 契约：id,station,code,time,level,inflow,outflow,flow_unit,version
迁移单 CSV 契约：site,old_code,new_code,activate_at,deactivate_at,note
其中 deactivate_at 留空表示迁移单未写清旧码停用时刻。
"""
import csv
import io

from app.normalize import decode, instant, number
from app.errors import DomainError
from app.reasons import rejected

OBS_HEADER = ["id", "station", "code", "time", "level", "inflow",
              "outflow", "flow_unit", "version"]
MIG_HEADER = ["site", "old_code", "new_code", "activate_at", "deactivate_at", "note"]


def _read_csv(raw, required, label):
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    text, encoding = decode(raw)
    if not text.strip():
        raise DomainError("EMPTY", f"{label}文件没有数据")
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    try:
        header = next(reader)
    except (StopIteration, csv.Error):
        raise DomainError("HEADER", f"{label}字段名读取失败")
    header = [v.strip().lstrip("﻿") for v in header]
    if len(header) != len(set(header)) or not set(required) <= set(header):
        raise DomainError("HEADER", f"{label}字段名不符合契约：{','.join(required)}")
    rows = []
    bad = []
    try:
        for cells in reader:
            if not cells or not any(v.strip() for v in cells):
                continue
            if len(cells) != len(header):
                bad.append(rejected({"_line": reader.line_num}, "COLUMN_COUNT", repr(cells)))
                continue
            row = dict(zip(header, (v.strip() for v in cells)))
            row["_line"] = reader.line_num
            rows.append(row)
    except csv.Error:
        raise DomainError("CSV", f"{label}CSV引号未闭合")
    if not rows:
        raise DomainError("HEADER_ONLY", f"{label}只有字段名")
    return rows, bad, encoding


def parse_observations(raw):
    rows, bad, encoding = _read_csv(raw, OBS_HEADER, "观测")
    good = []
    for row in rows:
        if not row["id"] or not row["code"]:
            bad.append(rejected(row, "MISSING", "测次或站码缺失"))
            continue
        try:
            parsed = {
                "id": row["id"], "station": row["station"], "code": row["code"],
                "time": instant(row["time"]),
                "level": number(row["level"]),
                "inflow": number(row["inflow"]),
                "outflow": number(row["outflow"]),
                "flow_unit": row["flow_unit"], "version": row["version"],
                "_line": row["_line"],
            }
            if parsed["flow_unit"] == "L/s":
                parsed["inflow"] /= 1000
                parsed["outflow"] /= 1000
                parsed["flow_unit"] = "m3/s"
            elif parsed["flow_unit"] != "m3/s":
                raise DomainError("UNIT", "流量单位无效")
        except DomainError as exc:
            bad.append(rejected(row, exc.code, exc.message))
            continue
        good.append(parsed)
    return {"observations": good, "quarantine": bad, "encoding": encoding,
            "input_count": len(rows) + len(bad)}


def parse_migrations(raw):
    rows, bad, encoding = _read_csv(raw, MIG_HEADER, "迁移单")
    migrations = []
    for row in rows:
        migrations.append({
            "site": row["site"], "old_code": row["old_code"], "new_code": row["new_code"],
            "activate_at": row["activate_at"] or None,
            "deactivate_at": row["deactivate_at"] or None,
            "note": row.get("note", ""), "_line": row["_line"],
        })
    return {"migrations": migrations, "quarantine": bad, "encoding": encoding}
