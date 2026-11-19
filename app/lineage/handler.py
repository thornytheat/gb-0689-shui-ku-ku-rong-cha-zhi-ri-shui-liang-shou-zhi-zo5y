"""站码沿革核定 HTTP 入口。"""
import csv
import io

from flask import Blueprint, request, jsonify, Response, render_template

from app.errors import DomainError
from app.lineage import store
from app.lineage.service import adjudicate

bp = Blueprint("lineage", __name__)


def _payload(field_text, field_file):
    file = request.files.get(field_file)
    if file is not None:
        return file.read()
    value = (request.get_json(silent=True) or request.form).get(field_text)
    if value is None:
        raise DomainError("BODY", f"缺少 {field_text}")
    if not isinstance(value, str):
        raise DomainError("BODY", f"{field_text} 必须是文本")
    return value


@bp.route("/api/lineage", methods=["POST"])
def run_lineage():
    if request.files:
        params = _form_params()
        obs_raw = _payload("observations", "obs_file")
        mig_raw = _payload("migrations", "mig_file")
    else:
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            raise DomainError("BODY", "请求必须是对象")
        params = body.get("params") or {}
        obs_raw, mig_raw = body.get("observations"), body.get("migrations")
        if not isinstance(obs_raw, str) or not isinstance(mig_raw, str):
            raise DomainError("BODY", "observations 与 migrations 必须是CSV文本")
    result = adjudicate(obs_raw, mig_raw, params)
    site = (result["segments"][0]["site"] if result["segments"] else
            (result["parallel_windows"][0]["site"] if result["parallel_windows"] else "未登记站"))
    saved, reused = store.save(result, site)
    return jsonify(saved)


@bp.route("/api/lineage/resume/<fingerprint>", methods=["POST"])
def resume_lineage(fingerprint):
    if request.files:
        params = _form_params()
        obs_raw = _payload("observations", "obs_file")
        mig_raw = _payload("migrations", "mig_file")
    else:
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            raise DomainError("BODY", "请求必须是对象")
        params = body.get("params") or {}
        obs_raw, mig_raw = body.get("observations"), body.get("migrations")
    new_result = adjudicate(obs_raw, mig_raw, params)
    saved, reused = store.resume(fingerprint, new_result)
    return jsonify(saved)


@bp.route("/api/lineage/<fingerprint>")
def get_lineage(fingerprint):
    return jsonify(store.fetch(fingerprint))


@bp.route("/api/lineage")
def lineage_history():
    return jsonify(store.history())


@bp.route("/api/lineage/<fingerprint>/ledgers")
def lineage_ledgers(fingerprint):
    return jsonify(store.ledgers(fingerprint))


@bp.route("/api/lineage/<fingerprint>/evidence.csv")
def lineage_evidence(fingerprint):
    result = store.fetch(fingerprint)
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(["逻辑站", "段类型", "采用站码", "开始 UTC", "结束 UTC", "原始行号", "说明"])
    for seg in result["segments"]:
        writer.writerow([seg["site"], seg["kind_label"], seg["adopted_code"],
                         seg["start"], seg["end"], "|".join(map(str, seg["row_lines"])), seg["note"]])
    for w in result["parallel_windows"]:
        writer.writerow([w["site"], "并行/" + w["state"],
                         f"{w['old_code']}//{w['new_code']}", w["start"], w["end"],
                         "旧:" + "|".join(map(str, w["old_lines"])) +
                         " 新:" + "|".join(map(str, w["new_lines"])), w["reason"]])
    writer.writerow([])
    writer.writerow(["逻辑站", "日期", "采用站码", "入库 m³", "出库 m³", "库容变化 m³", "收支差 m³", "状态"])
    for row in store.ledgers(fingerprint):
        writer.writerow([row["station"], row["date"], row.get("station_code", ""),
                         row["in_m3"], row["out_m3"], row["storage_change"],
                         row["residual"], row["state"]])
    return Response("﻿" + stream.getvalue(), content_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition":
                             f"attachment; filename=lineage_{fingerprint}.csv"})


@bp.route("/lineage")
def lineage_page():
    return render_template("lineage.html")


def _form_params():
    import json
    try:
        return json.loads(request.form.get("params", "{}"))
    except ValueError:
        raise DomainError("PARAMS", "参数格式错误")
