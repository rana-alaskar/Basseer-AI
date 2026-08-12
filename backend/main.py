"""
بصير AI – واجهة برمجة التطبيقات الخلفية v3
Basseer AI – Backend API v3 (FastAPI)

Endpoints:
  POST /validate           - التحقق من سجل (يرجع النتيجة فوراً)
  POST /ingest             - التحقق + التخزين + تحديث المؤشرات
  POST /validate_response  - (legacy) متوافق مع الإصدار السابق
  GET  /stats              - إحصائيات جودة البيانات
  GET  /heatmap            - بيانات خريطة الحرارة
  GET  /responses          - آخر الاستجابات
  GET  /cell_detail        - تفاصيل خلية خريطة الحرارة
  GET  /health             - صحة النظام
  GET  /llm_settings       - إعدادات LLM الحالية
  POST /llm_settings       - تحديث إعدادات LLM
  POST /review             - تحديث حالة مراجعة سجل
  GET  /field_researcher   - قائمة السجلات التي تحتاج مراجعة
  GET  /recommendations    - التوصيات المجمّعة
"""

import sys
import os
import json
import csv
import io
import time
import zipfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# تحميل .env
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from fastapi import FastAPI, Depends, Query, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional

from storage.db import init_db, get_db
from storage.models import SurveyResponse, ValidationLog
from services.pipeline import run_pipeline
from backend.validators.llm_layer import get_llm_stats, get_llm_config, save_llm_config, is_llm_configured

# ─── App ───
app = FastAPI(
    title="Basseer AI – Semantic Guardian API v3",
    description="واجهة الكشف عن التناقضات المنطقية والدلالية في بيانات الاستبيانات",
    version="3.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_db()


# ─── Pydantic Models ───

class RecordInput(BaseModel):
    age: int = Field(..., ge=1, le=120)
    experience_years: int = Field(..., ge=0, le=80)
    education: str = Field(..., min_length=1)
    job_title: str = Field(..., min_length=1)
    income: float = Field(..., ge=0)
    region: str = Field(..., min_length=1)
    employment_status: str = Field(..., min_length=1)
    enumerator_id: Optional[str] = Field(default="default")
    question_id: Optional[str] = Field(default="")


class ValidateRequest(BaseModel):
    record: RecordInput
    survey_schema: Optional[dict] = None
    context: Optional[dict] = None


class ValidateResponse(BaseModel):
    confidence_score: float
    confidence_label: str
    confidence_label_ar: str
    confidence_reason_ar: str
    confidence_reason_en: str
    contradictions_count: int
    missing_fields_count: int
    warnings: list[dict]
    recommendations: list[dict]
    detected_by: str
    llm_used: bool
    llm_provider: str
    latency_ms: float


class IngestResponse(BaseModel):
    response_id: int
    confidence_score: float
    confidence_label: str
    confidence_label_ar: str
    confidence_reason_ar: str
    confidence_reason_en: str
    contradictions_count: int
    warnings: list[dict]
    recommendations: list[dict]
    detected_by: str
    llm_used: bool
    latency_ms: float


class LLMSettingsInput(BaseModel):
    provider: str
    api_key: str
    model: Optional[str] = ""


class ReviewInput(BaseModel):
    response_id: int
    status: str  # reviewed | confirmed | escalated | correction_requested
    note: Optional[str] = ""


# ─── Helper: store to DB ───

def _store_result(data: dict, result: dict, db: Session) -> int:
    resp = SurveyResponse(
        age=data["age"], experience_years=data["experience_years"],
        education=data["education"], job_title=data["job_title"],
        income=data["income"], region=data["region"],
        employment_status=data["employment_status"],
        enumerator_id=data.get("enumerator_id", "default"),
        question_id=data.get("question_id", ""),
        confidence_score=result["confidence_score"],
        confidence_label=result["confidence_label"],
        confidence_reason_ar=result["confidence_reason_ar"],
        confidence_reason_en=result.get("confidence_reason_en", ""),
        warnings_json=json.dumps(result["warnings"], ensure_ascii=False),
        recommendations_json=json.dumps(result["recommendations"], ensure_ascii=False),
        contradictions_count=result["contradictions_count"],
        missing_fields_count=result["missing_fields_count"],
        detected_by=result.get("detected_by", "rule"),
        llm_used=result["llm_used"],
        llm_provider=result["llm_provider"],
        latency_ms=result["latency_ms"],
        review_status="pending" if result["contradictions_count"] > 0 else "confirmed",
    )
    db.add(resp)
    db.flush()

    for w in result["warnings"]:
        db.add(ValidationLog(
            response_id=resp.id,
            rule_name=w.get("rule", "unknown"),
            severity=w.get("severity", "medium"),
            field=w.get("field", "unknown"),
            message=w.get("message_en", w.get("message_ar", "")),
            source=w.get("source", "rules"),
        ))

    db.commit()
    db.refresh(resp)
    return resp.id


# ═══════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════

@app.post("/validate", response_model=ValidateResponse)
def validate(req: ValidateRequest):
    """التحقق من سجل — لا يخزّن، يرجع النتيجة فوراً"""
    data = req.record.model_dump()
    result = run_pipeline(data)
    return ValidateResponse(**result)


@app.post("/ingest", response_model=IngestResponse)
def ingest(req: ValidateRequest, db: Session = Depends(get_db)):
    """التحقق + التخزين + تحديث المؤشرات"""
    data = req.record.model_dump()
    result = run_pipeline(data)
    rid = _store_result(data, result, db)
    return IngestResponse(
        response_id=rid,
        confidence_score=result["confidence_score"],
        confidence_label=result["confidence_label"],
        confidence_label_ar=result["confidence_label_ar"],
        confidence_reason_ar=result["confidence_reason_ar"],
        confidence_reason_en=result.get("confidence_reason_en", ""),
        contradictions_count=result["contradictions_count"],
        warnings=result["warnings"],
        recommendations=result["recommendations"],
        detected_by=result.get("detected_by", "rule"),
        llm_used=result["llm_used"],
        latency_ms=result["latency_ms"],
    )


@app.post("/validate_response")
def validate_response_legacy(survey: RecordInput, db: Session = Depends(get_db)):
    """(Legacy) متوافق مع الإصدار السابق"""
    data = survey.model_dump()
    result = run_pipeline(data)
    rid = _store_result(data, result, db)
    return {
        "confidence_score": result["confidence_score"],
        "confidence_label": result["confidence_label"],
        "confidence_label_ar": result["confidence_label_ar"],
        "confidence_reason_ar": result["confidence_reason_ar"],
        "confidence_reason_en": result.get("confidence_reason_en", ""),
        "contradictions_count": result["contradictions_count"],
        "warnings": result["warnings"],
        "recommendations": result["recommendations"],
        "detected_by": result.get("detected_by", "rule"),
        "response_id": rid,
        "llm_used": result["llm_used"],
        "latency_ms": result["latency_ms"],
    }


# ─── Health ───

@app.get("/health")
def health_check():
    """System health monitoring endpoint."""
    llm_cfg = get_llm_config()
    llm_stats = get_llm_stats()
    return {
        "api_status": "running",
        "version": "3.0.0",
        "llm_enabled": is_llm_configured(),
        "llm_provider": llm_cfg["provider"],
        "llm_model": llm_cfg["model"],
        "database_status": "connected",
        "llm_stats": {
            "total_calls": llm_stats["total_calls"],
            "successful_calls": llm_stats["successful_calls"],
            "failed_calls": llm_stats["failed_calls"],
            "cache_hits": llm_stats["cache_hits"],
            "cache_hit_rate": llm_stats["cache_hit_rate"],
            "average_latency_ms": llm_stats["average_latency_ms"],
            "cache_size": llm_stats["cache_size"],
            "last_error": llm_stats["last_error"],
        },
    }


# ─── LLM Settings ───

@app.get("/llm_settings")
def get_settings():
    """Get current LLM configuration (key is masked)."""
    cfg = get_llm_config()
    key = cfg["api_key"]
    masked = (key[:4] + "****" + key[-4:]) if len(key) > 8 else ("****" if key else "")
    return {
        "provider": cfg["provider"],
        "api_key_masked": masked,
        "model": cfg["model"],
        "is_configured": is_llm_configured(),
    }


@app.post("/llm_settings")
def update_settings(settings: LLMSettingsInput):
    """Update LLM provider settings."""
    try:
        save_llm_config(settings.provider, settings.api_key, settings.model or "")
        return {"status": "ok", "message": "تم حفظ الإعدادات بنجاح", "provider": settings.provider}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ─── Field Researcher ───

@app.post("/review")
def update_review(req: ReviewInput, db: Session = Depends(get_db)):
    """Update review status of a survey response."""
    resp = db.query(SurveyResponse).filter(SurveyResponse.id == req.response_id).first()
    if not resp:
        return {"status": "error", "message": "السجل غير موجود"}
    resp.review_status = req.status
    resp.reviewer_note = req.note or ""
    db.commit()
    return {"status": "ok", "response_id": req.response_id, "new_status": req.status}


@app.get("/field_researcher")
def field_researcher_list(
    status: str = Query("pending", regex="^(pending|reviewed|confirmed|escalated|correction_requested|all)$"),
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """List survey responses for field researcher review."""
    q = db.query(SurveyResponse).filter(SurveyResponse.contradictions_count > 0)
    if status != "all":
        q = q.filter(SurveyResponse.review_status == status)
    responses = q.order_by(SurveyResponse.confidence_score.asc()).limit(limit).all()
    return {
        "responses": [{
            "id": r.id, "age": r.age, "experience_years": r.experience_years,
            "education": r.education, "job_title": r.job_title, "income": r.income,
            "region": r.region, "employment_status": r.employment_status,
            "enumerator_id": r.enumerator_id,
            "confidence_score": r.confidence_score, "confidence_label": r.confidence_label,
            "confidence_reason_ar": r.confidence_reason_ar,
            "contradictions_count": r.contradictions_count,
            "detected_by": r.detected_by or "rule",
            "review_status": r.review_status or "pending",
            "reviewer_note": r.reviewer_note or "",
            "llm_used": r.llm_used, "latency_ms": r.latency_ms,
            "warnings": json.loads(r.warnings_json) if r.warnings_json else [],
            "recommendations": json.loads(r.recommendations_json) if r.recommendations_json else [],
            "created_at": r.created_at.isoformat() if r.created_at else None,
        } for r in responses],
        "total": len(responses),
    }


# ─── Recommendations ───

@app.get("/recommendations")
def get_recommendations(db: Session = Depends(get_db)):
    """Get aggregated recommendations based on all stored data."""
    field_labels = {
        "age": "العمر", "experience_years": "سنوات الخبرة",
        "education": "التعليم", "job_title": "المسمى الوظيفي",
        "income": "الدخل", "employment_status": "حالة التوظيف",
    }

    # Top problematic fields
    top_fields = db.query(
        ValidationLog.field, func.count(ValidationLog.id).label("c")
    ).group_by(ValidationLog.field).order_by(func.count(ValidationLog.id).desc()).limit(10).all()

    # Top problematic regions
    top_regions = db.query(
        SurveyResponse.region, func.sum(SurveyResponse.contradictions_count).label("t")
    ).group_by(SurveyResponse.region).order_by(func.sum(SurveyResponse.contradictions_count).desc()).limit(5).all()

    # Top problematic enumerators
    top_enums = db.query(
        SurveyResponse.enumerator_id,
        func.count(SurveyResponse.id).label("c"),
        func.avg(SurveyResponse.confidence_score).label("avg_conf"),
    ).filter(SurveyResponse.contradictions_count > 0).group_by(
        SurveyResponse.enumerator_id
    ).order_by(func.count(SurveyResponse.id).desc()).limit(5).all()

    total = db.query(func.count(SurveyResponse.id)).scalar() or 1

    recs = []

    # Field-level recommendations
    for field, count in top_fields:
        rate = round((count / total) * 100, 1)
        label_ar = field_labels.get(field, field)
        if rate > 20:
            recs.append({
                "type": "question_rephrase",
                "priority": "high",
                "field": field,
                "message_ar": f"يُنصح بإعادة صياغة سؤال '{label_ar}' — معدل الخطأ: {rate}%",
                "message_en": f"Consider rephrasing '{field}' question — error rate: {rate}%",
                "error_count": count,
            })
        elif rate > 10:
            recs.append({
                "type": "field_review",
                "priority": "medium",
                "field": field,
                "message_ar": f"يُنصح بمراجعة سؤال '{label_ar}' — معدل الخطأ: {rate}%",
                "message_en": f"Consider reviewing '{field}' question — error rate: {rate}%",
                "error_count": count,
            })

    # Region-level recommendations
    for region, total_errors in top_regions:
        if total_errors and int(total_errors) > 5:
            recs.append({
                "type": "researcher_training",
                "priority": "high" if int(total_errors) > 15 else "medium",
                "field": "region",
                "message_ar": f"يُنصح بمراجعة تدريب الباحثين الميدانيين في منطقة {region} ({int(total_errors)} خطأ)",
                "message_en": f"Consider reviewing field researcher training in {region} region ({int(total_errors)} errors)",
                "error_count": int(total_errors),
            })

    # Enumerator-level recommendations
    for enum_id, count, avg_conf in top_enums:
        if count >= 5 and avg_conf and float(avg_conf) < 60:
            recs.append({
                "type": "enumerator_review",
                "priority": "high",
                "field": "enumerator_id",
                "message_ar": f"يُنصح بمراجعة أداء الباحث {enum_id} — {count} سجل بمشاكل، متوسط ثقة: {float(avg_conf):.0f}",
                "message_en": f"Review enumerator {enum_id} — {count} flagged records, avg confidence: {float(avg_conf):.0f}",
                "error_count": count,
            })

    return {"recommendations": recs, "total": len(recs)}


# ─── Stats ───

@app.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    total = db.query(func.count(SurveyResponse.id)).scalar() or 0
    total_contradictions = db.query(func.sum(SurveyResponse.contradictions_count)).scalar() or 0
    avg_score = db.query(func.avg(SurveyResponse.confidence_score)).scalar() or 0
    avg_latency = db.query(func.avg(SurveyResponse.latency_ms)).scalar() or 0
    llm_count = db.query(func.count(SurveyResponse.id)).filter(SurveyResponse.llm_used == True).scalar() or 0

    high_c = db.query(func.count(SurveyResponse.id)).filter(SurveyResponse.confidence_label == "High confidence").scalar() or 0
    med_c = db.query(func.count(SurveyResponse.id)).filter(SurveyResponse.confidence_label == "Medium confidence").scalar() or 0
    low_c = db.query(func.count(SurveyResponse.id)).filter(SurveyResponse.confidence_label == "Low confidence").scalar() or 0

    quality_pct = round((high_c / max(total, 1)) * 100, 1)

    # Review status counts
    pending_count = db.query(func.count(SurveyResponse.id)).filter(SurveyResponse.review_status == "pending", SurveyResponse.contradictions_count > 0).scalar() or 0
    reviewed_count = db.query(func.count(SurveyResponse.id)).filter(SurveyResponse.review_status == "reviewed").scalar() or 0
    escalated_count = db.query(func.count(SurveyResponse.id)).filter(SurveyResponse.review_status == "escalated").scalar() or 0

    top_field = db.query(
        ValidationLog.field, func.count(ValidationLog.id).label("c")
    ).group_by(ValidationLog.field).order_by(func.count(ValidationLog.id).desc()).first()

    top_region = db.query(
        SurveyResponse.region, func.sum(SurveyResponse.contradictions_count).label("t")
    ).group_by(SurveyResponse.region).order_by(func.sum(SurveyResponse.contradictions_count).desc()).first()

    # Detection source distribution
    rule_only = db.query(func.count(SurveyResponse.id)).filter(SurveyResponse.detected_by == "rule", SurveyResponse.contradictions_count > 0).scalar() or 0
    llm_only = db.query(func.count(SurveyResponse.id)).filter(SurveyResponse.detected_by == "llm").scalar() or 0
    hybrid = db.query(func.count(SurveyResponse.id)).filter(SurveyResponse.detected_by == "hybrid").scalar() or 0

    top_questions = db.query(
        ValidationLog.field,
        ValidationLog.severity,
        func.count(ValidationLog.id).label("count"),
    ).group_by(ValidationLog.field, ValidationLog.severity).order_by(
        func.count(ValidationLog.id).desc()
    ).limit(20).all()

    top_q_list = [{"field": q[0], "severity": q[1], "count": q[2]} for q in top_questions]

    return {
        "total_responses": total,
        "total_contradictions": int(total_contradictions),
        "average_confidence_score": round(float(avg_score), 1),
        "average_latency_ms": round(float(avg_latency), 1),
        "quality_percentage": quality_pct,
        "llm_validated_count": llm_count,
        "confidence_distribution": {"high": high_c, "medium": med_c, "low": low_c},
        "detection_distribution": {"rule": rule_only, "llm": llm_only, "hybrid": hybrid},
        "review_status": {"pending": pending_count, "reviewed": reviewed_count, "escalated": escalated_count},
        "top_problematic_field": top_field[0] if top_field else "N/A",
        "top_problematic_field_count": top_field[1] if top_field else 0,
        "top_problematic_region": top_region[0] if top_region else "N/A",
        "top_problematic_region_errors": int(top_region[1]) if top_region else 0,
        "top_questions_table": top_q_list,
    }


# ─── Heatmap ───

@app.get("/heatmap")
def get_heatmap(
    metric: str = Query("count", regex="^(count|percentage|avg_confidence|llm_disagreement)$"),
    axis: str = Query("region", regex="^(region|enumerator|question)$"),
    db: Session = Depends(get_db),
):
    fields = ["age", "experience_years", "education", "job_title", "income", "employment_status"]
    field_labels = {
        "age": "العمر", "experience_years": "سنوات الخبرة",
        "education": "التعليم", "job_title": "المسمى الوظيفي",
        "income": "الدخل", "employment_status": "حالة التوظيف",
    }

    # Determine axis values (region, enumerator, or question)
    if axis == "enumerator":
        axis_vals = db.query(SurveyResponse.enumerator_id).distinct().all()
        axis_vals = sorted([r[0] for r in axis_vals if r[0]]) if axis_vals else []
        axis_column = SurveyResponse.enumerator_id
        axis_label = "الباحث"
    elif axis == "question":
        axis_vals = db.query(SurveyResponse.question_id).distinct().all()
        axis_vals = sorted([r[0] for r in axis_vals if r[0] and r[0].strip()]) if axis_vals else []
        axis_column = SurveyResponse.question_id
        axis_label = "السؤال"
    else:
        axis_vals = db.query(SurveyResponse.region).distinct().all()
        axis_vals = sorted([r[0] for r in axis_vals]) if axis_vals else []
        axis_column = SurveyResponse.region
        axis_label = "المنطقة"

    if not axis_vals:
        return {
            "regions": [], "fields": fields, "field_labels": field_labels,
            "matrix": [], "annotations": [], "metric": metric, "axis": axis,
            "axis_label": axis_label,
            "top_question": "N/A", "top_question_label": "N/A", "top_question_errors": 0,
            "top_region": "N/A", "top_region_errors": 0,
        }

    total_per_axis = {}
    avg_conf_per_axis = {}
    for val in axis_vals:
        total_per_axis[val] = db.query(func.count(SurveyResponse.id)).filter(
            axis_column == val).scalar() or 1
        avg_conf_per_axis[val] = db.query(func.avg(SurveyResponse.confidence_score)).filter(
            axis_column == val).scalar() or 100

    matrix, annotations = [], []
    for field in fields:
        row, ann = [], []
        for val in axis_vals:
            count = db.query(func.count(ValidationLog.id)).join(
                SurveyResponse, ValidationLog.response_id == SurveyResponse.id
            ).filter(axis_column == val, ValidationLog.field == field).scalar() or 0

            if metric == "percentage":
                v = round((count / total_per_axis[val]) * 100, 1)
                ann.append(f"{v}%")
            elif metric == "avg_confidence":
                v = round(float(avg_conf_per_axis[val]), 1)
                ann.append(f"{v}")
            elif metric == "llm_disagreement":
                # LLM disagreement: fields where rule and LLM gave different results
                rule_count = db.query(func.count(ValidationLog.id)).join(
                    SurveyResponse, ValidationLog.response_id == SurveyResponse.id
                ).filter(axis_column == val, ValidationLog.field == field,
                         ValidationLog.source == "rules").scalar() or 0
                llm_count_v = db.query(func.count(ValidationLog.id)).join(
                    SurveyResponse, ValidationLog.response_id == SurveyResponse.id
                ).filter(axis_column == val, ValidationLog.field == field,
                         ValidationLog.source == "llm").scalar() or 0
                v = abs(rule_count - llm_count_v)
                ann.append(str(v))
            else:
                v = count
                ann.append(str(count))
            row.append(v)
        matrix.append(row)
        annotations.append(ann)

    field_totals = {fields[i]: sum(matrix[i]) for i in range(len(fields))}
    axis_totals = {axis_vals[j]: sum(matrix[i][j] for i in range(len(fields))) for j in range(len(axis_vals))} if axis_vals else {}
    top_q = max(field_totals, key=field_totals.get) if field_totals else "N/A"
    top_a = max(axis_totals, key=axis_totals.get) if axis_totals else "N/A"

    return {
        "regions": axis_vals,  # keep key name for backward compat
        "fields": fields, "field_labels": field_labels,
        "matrix": matrix, "annotations": annotations, "metric": metric,
        "axis": axis, "axis_label": axis_label,
        "top_question": top_q, "top_question_label": field_labels.get(top_q, top_q),
        "top_question_errors": field_totals.get(top_q, 0),
        "top_region": top_a, "top_region_errors": axis_totals.get(top_a, 0),
    }


# ─── Cell Detail ───

@app.get("/cell_detail")
def cell_detail(
    field: str,
    region: str,
    axis: str = Query("region", regex="^(region|enumerator|question)$"),
    db: Session = Depends(get_db),
):
    """تفاصيل خلية من خريطة الحرارة — لعرض أمثلة + توصية"""
    if axis == "enumerator":
        axis_column = SurveyResponse.enumerator_id
    elif axis == "question":
        axis_column = SurveyResponse.question_id
    else:
        axis_column = SurveyResponse.region

    logs = db.query(ValidationLog).join(
        SurveyResponse, ValidationLog.response_id == SurveyResponse.id
    ).filter(axis_column == region, ValidationLog.field == field).limit(10).all()

    examples = []
    for l in logs:
        resp = db.query(SurveyResponse).filter(SurveyResponse.id == l.response_id).first()
        if resp:
            examples.append({
                "id": resp.id, "age": resp.age, "experience_years": resp.experience_years,
                "education": resp.education, "job_title": resp.job_title,
                "income": resp.income, "severity": l.severity, "message": l.message,
                "source": l.source, "detected_by": resp.detected_by or "rule",
            })

    total_axis = db.query(func.count(SurveyResponse.id)).filter(axis_column == region).scalar() or 1
    error_count = db.query(func.count(ValidationLog.id)).join(
        SurveyResponse, ValidationLog.response_id == SurveyResponse.id
    ).filter(axis_column == region, ValidationLog.field == field).scalar() or 0
    rate = round((error_count / total_axis) * 100, 1)

    # Most frequent violated rules for this cell
    top_rules = db.query(
        ValidationLog.rule_name, func.count(ValidationLog.id).label("c")
    ).join(SurveyResponse, ValidationLog.response_id == SurveyResponse.id).filter(
        axis_column == region, ValidationLog.field == field
    ).group_by(ValidationLog.rule_name).order_by(func.count(ValidationLog.id).desc()).limit(5).all()

    # LLM explanation samples
    llm_explanations = db.query(ValidationLog.message).join(
        SurveyResponse, ValidationLog.response_id == SurveyResponse.id
    ).filter(axis_column == region, ValidationLog.field == field,
             ValidationLog.source == "llm").limit(3).all()

    # Average confidence for this cell
    avg_conf = db.query(func.avg(SurveyResponse.confidence_score)).join(
        ValidationLog, ValidationLog.response_id == SurveyResponse.id
    ).filter(axis_column == region, ValidationLog.field == field).scalar() or 0

    high_rate = rate > 30
    field_labels = {"age": "العمر", "experience_years": "سنوات الخبرة",
                    "education": "التعليم", "job_title": "المسمى الوظيفي",
                    "income": "الدخل", "employment_status": "حالة التوظيف"}
    field_ar = field_labels.get(field, field)

    rec_ar = f"يُوصى بإعادة صياغة سؤال '{field_ar}' أو إضافة توضيح للمستجيبين" if high_rate else "المعدل مقبول — متابعة المراقبة"
    rec_en = f"Consider rephrasing '{field}' question or adding guidance for respondents" if high_rate else "Rate acceptable — continue monitoring"

    return {
        "field": field, "region": region, "error_count": error_count,
        "conflict_rate_pct": rate,
        "average_confidence": round(float(avg_conf), 1),
        "top_rules": [{"rule": r[0], "count": r[1]} for r in top_rules],
        "llm_explanations": [e[0] for e in llm_explanations],
        "examples": examples,
        "recommendation_ar": rec_ar,
        "recommendation_en": rec_en,
    }


@app.get("/responses")
def get_responses(limit: int = 50, db: Session = Depends(get_db)):
    responses = db.query(SurveyResponse).order_by(SurveyResponse.created_at.desc()).limit(limit).all()
    return {
        "responses": [{
            "id": r.id, "age": r.age, "experience_years": r.experience_years,
            "education": r.education, "job_title": r.job_title, "income": r.income,
            "region": r.region, "employment_status": r.employment_status,
            "enumerator_id": r.enumerator_id,
            "question_id": getattr(r, 'question_id', '') or '',
            "confidence_score": r.confidence_score, "confidence_label": r.confidence_label,
            "confidence_reason_ar": r.confidence_reason_ar,
            "contradictions_count": r.contradictions_count,
            "detected_by": r.detected_by or "rule",
            "review_status": r.review_status or "pending",
            "llm_used": r.llm_used, "latency_ms": r.latency_ms,
            "warnings": json.loads(r.warnings_json) if r.warnings_json else [],
            "recommendations": json.loads(r.recommendations_json) if r.recommendations_json else [],
            "created_at": r.created_at.isoformat() if r.created_at else None,
        } for r in responses],
        "total": len(responses),
    }


# ═══════════════════════════════════════
# CSV Upload & Download Endpoints
# ═══════════════════════════════════════

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEMO_DIR = os.path.join(PROJECT_ROOT, "data", "demo")

REQUIRED_CSV_COLUMNS = {"age", "experience_years", "education", "job_title",
                        "income", "region", "employment_status"}
OPTIONAL_CSV_COLUMNS = {"enumerator_id", "question_id"}

CSV_FIELDNAMES = ["age", "experience_years", "education", "job_title",
                  "income", "region", "employment_status", "enumerator_id", "question_id"]


def _validate_csv_row(row: dict, row_num: int) -> tuple[dict | None, str | None]:
    """Validate and normalize a single CSV row. Returns (clean_data, error_msg)."""
    try:
        age = int(float(row.get("age", 0)))
    except (ValueError, TypeError):
        return None, f"صف {row_num}: قيمة العمر غير صالحة"
    try:
        exp = int(float(row.get("experience_years", 0)))
    except (ValueError, TypeError):
        return None, f"صف {row_num}: قيمة سنوات الخبرة غير صالحة"
    try:
        income = float(row.get("income", 0))
    except (ValueError, TypeError):
        return None, f"صف {row_num}: قيمة الدخل غير صالحة"

    education = str(row.get("education", "")).strip()
    job_title = str(row.get("job_title", "")).strip()
    region = str(row.get("region", "")).strip()
    emp_status = str(row.get("employment_status", "")).strip()

    if not education:
        return None, f"صف {row_num}: حقل التعليم فارغ"
    if not job_title:
        return None, f"صف {row_num}: حقل المسمى الوظيفي فارغ"
    if not region:
        return None, f"صف {row_num}: حقل المنطقة فارغ"
    if not emp_status:
        return None, f"صف {row_num}: حقل حالة التوظيف فارغ"

    if age < 1 or age > 120:
        age = max(1, min(120, age))

    return {
        "age": age,
        "experience_years": max(0, exp),
        "education": education,
        "job_title": job_title,
        "income": max(0, income),
        "region": region,
        "employment_status": emp_status,
        "enumerator_id": str(row.get("enumerator_id", "default")).strip() or "default",
        "question_id": str(row.get("question_id", "")).strip(),
    }, None


@app.post("/upload_csv")
async def upload_csv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """
    Upload a CSV file for bulk validation.
    Supports up to 6000 rows. Processes each row through the validation pipeline.
    """
    t0 = time.time()

    # ── File type check ──
    if not file.filename:
        return {"status": "error", "message": "لم يتم اختيار ملف"}
    if not file.filename.lower().endswith(".csv"):
        return {"status": "error", "message": "نوع الملف غير صحيح. يرجى رفع ملف CSV فقط"}

    # ── Read content ──
    try:
        content = await file.read()
        if len(content) == 0:
            return {"status": "error", "message": "الملف فارغ. يرجى رفع ملف يحتوي على بيانات"}
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = content.decode("latin-1")
        except Exception:
            return {"status": "error", "message": "تعذر قراءة الملف. تأكد من ترميز UTF-8"}

    # ── Parse CSV ──
    try:
        reader = csv.DictReader(io.StringIO(text))
        if reader.fieldnames is None:
            return {"status": "error", "message": "الملف لا يحتوي على عناوين أعمدة"}
    except Exception:
        return {"status": "error", "message": "تعذر تحليل ملف CSV. تأكد من صحة التنسيق"}

    # ── Validate columns ──
    headers = set(h.strip() for h in reader.fieldnames if h)
    missing_cols = REQUIRED_CSV_COLUMNS - headers
    if missing_cols:
        return {
            "status": "error",
            "message": f"أعمدة مفقودة: {', '.join(sorted(missing_cols))}. الأعمدة المطلوبة: {', '.join(sorted(REQUIRED_CSV_COLUMNS))}"
        }

    # ── Read all rows ──
    raw_rows = list(reader)
    if len(raw_rows) == 0:
        return {"status": "error", "message": "الملف لا يحتوي على بيانات (عناوين فقط)"}
    if len(raw_rows) > 6000:
        return {"status": "error", "message": f"عدد الصفوف ({len(raw_rows)}) يتجاوز الحد الأقصى (6000)"}

    # ── Process rows ──
    results = []
    errors = []
    total_rule_issues = 0
    total_llm_issues = 0
    total_valid = 0
    total_flagged = 0
    score_sum = 0.0

    for i, raw_row in enumerate(raw_rows, start=1):
        data, err = _validate_csv_row(raw_row, i)
        if err:
            errors.append({"row_number": i, "error": err})
            results.append({
                "row_number": i,
                "confidence_score": 0,
                "confidence_label": "Error",
                "detected_by": "parse_error",
                "issue_summary": err,
                "recommendation": "يرجى تصحيح البيانات وإعادة الرفع",
                "llm_used": False,
                "region": raw_row.get("region", ""),
                "enumerator_id": raw_row.get("enumerator_id", ""),
                "question_id": raw_row.get("question_id", ""),
            })
            continue

        # Run validation pipeline
        result = run_pipeline(data)

        # Store to DB
        rid = _store_result(data, result, db)

        score = result["confidence_score"]
        score_sum += score
        detected = result.get("detected_by", "rule")
        n_warnings = result["contradictions_count"]

        if n_warnings > 0:
            total_flagged += 1
            if detected in ("rule", "hybrid"):
                total_rule_issues += n_warnings
            if detected in ("llm", "hybrid"):
                total_llm_issues += n_warnings
        else:
            total_valid += 1

        # Build issue summary
        warning_msgs = [w.get("message_en", w.get("message_ar", "")) for w in result["warnings"][:3]]
        issue_summary = "; ".join(warning_msgs) if warning_msgs else "No issues"

        rec_msgs = [r.get("message_en", r.get("message_ar", "")) for r in result["recommendations"][:2]]
        recommendation = "; ".join(rec_msgs) if rec_msgs else "Data is consistent"

        results.append({
            "row_number": i,
            "confidence_score": score,
            "confidence_label": result["confidence_label"],
            "detected_by": detected,
            "issue_summary": issue_summary,
            "recommendation": recommendation,
            "llm_used": result["llm_used"],
            "region": data["region"],
            "enumerator_id": data["enumerator_id"],
            "question_id": data.get("question_id", ""),
        })

    elapsed = round(time.time() - t0, 2)
    total_processed = len(results)
    avg_score = round(score_sum / max(total_processed - len(errors), 1), 1)

    # ── Top issues ──
    issue_counter = {}
    region_counter = {}
    enum_counter = {}
    for r in results:
        if r["confidence_score"] < 75 and r["detected_by"] != "parse_error":
            summary = r["issue_summary"]
            if summary != "No issues":
                for part in summary.split(";"):
                    part = part.strip()[:60]
                    if part:
                        issue_counter[part] = issue_counter.get(part, 0) + 1
            region_counter[r["region"]] = region_counter.get(r["region"], 0) + 1
            enum_counter[r["enumerator_id"]] = enum_counter.get(r["enumerator_id"], 0) + 1

    top_issues = sorted(issue_counter.items(), key=lambda x: -x[1])[:5]
    top_region = max(region_counter.items(), key=lambda x: x[1]) if region_counter else ("N/A", 0)
    top_enum = max(enum_counter.items(), key=lambda x: x[1]) if enum_counter else ("N/A", 0)

    return {
        "status": "ok",
        "summary": {
            "total_rows": total_processed,
            "valid_rows": total_valid,
            "flagged_rows": total_flagged,
            "error_rows": len(errors),
            "avg_confidence": avg_score,
            "rule_issues": total_rule_issues,
            "llm_issues": total_llm_issues,
            "processing_time_sec": elapsed,
            "top_issues": [{"issue": t[0], "count": t[1]} for t in top_issues],
            "top_region": {"name": top_region[0], "errors": top_region[1]},
            "top_enumerator": {"name": top_enum[0], "errors": top_enum[1]},
        },
        "results": results,
        "errors": errors,
    }


@app.get("/download_template")
def download_template():
    """Download an empty CSV template."""
    tpl_path = os.path.join(DEMO_DIR, "survey_template.csv")
    if os.path.exists(tpl_path):
        return FileResponse(tpl_path, media_type="text/csv", filename="survey_template.csv")
    # Generate on-the-fly
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_FIELDNAMES)
    writer.writeheader()
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=survey_template.csv"},
    )


@app.get("/download_demo_files")
def download_demo_files():
    """Download all demo CSV files as a ZIP."""
    if not os.path.isdir(DEMO_DIR):
        return {"status": "error", "message": "Demo files not found"}

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname in os.listdir(DEMO_DIR):
            if fname.endswith(".csv"):
                fpath = os.path.join(DEMO_DIR, fname)
                zf.write(fpath, fname)

    zip_buffer.seek(0)
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=basseer_demo_files.zip"},
    )


@app.get("/download_demo/{filename}")
def download_single_demo(filename: str):
    """Download a single demo CSV file."""
    safe_name = os.path.basename(filename)
    fpath = os.path.join(DEMO_DIR, safe_name)
    if not os.path.exists(fpath) or not safe_name.endswith(".csv"):
        return {"status": "error", "message": "ملف غير موجود"}
    return FileResponse(fpath, media_type="text/csv", filename=safe_name)


@app.get("/")
def root():
    provider = os.environ.get("LLM_PROVIDER", "offline")
    return {
        "name": "Basseer AI – Semantic Guardian", "name_ar": "بصير AI – الحارس الدلالي",
        "version": "3.0.0", "status": "running", "llm_provider": provider,
        "llm_configured": is_llm_configured(),
        "endpoints": ["/validate", "/ingest", "/validate_response", "/stats",
                      "/heatmap", "/cell_detail", "/responses", "/health",
                      "/llm_settings", "/field_researcher", "/review", "/recommendations",
                      "/upload_csv", "/download_template", "/download_demo_files"],
    }
