"""
Analytics Queries
==================
استعلامات تحليلية على بيانات التدريب الفعلية.
تُستخدم من /api/analytics/* endpoints.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from src.infrastructure.db.models import (
    ExerciseTable, PerformedExerciseTable, SessionTable, SetTable,
)


def _calculate_e1rm(weight: Decimal, reps: int) -> float:
    """Epley formula: weight * (1 + reps/30)"""
    if weight is None or reps is None or reps <= 0:
        return 0.0
    return float(weight) * (1 + reps / 30.0)


# ═══════════════════════════════════════════════════════════
# 1) Exercise Progress (Deep Dive)
# ═══════════════════════════════════════════════════════════

def get_exercise_sessions(db: Session, profile_id: str, exercise_id: str, limit: int = 30):
    """يجيب كل الجلسات اللي تمارس فيها التمرين (مع e1RM لكل جلسة)."""
    stmt = (
        select(
            SessionTable.id,
            SessionTable.started_at,
            func.max(SetTable.weight).label("max_weight"),
            func.max(SetTable.weight * (1 + SetTable.reps / 30.0)).label("e1rm"),
            func.sum(SetTable.weight * SetTable.reps).label("volume"),
            func.count(SetTable.id).label("sets_count"),
            func.avg(SetTable.rpe).label("avg_rpe"),
            func.avg(SetTable.rir).label("avg_rir"),
        )
        .join(PerformedExerciseTable, PerformedExerciseTable.session_id == SessionTable.id)
        .join(SetTable, SetTable.performed_exercise_id == PerformedExerciseTable.id)
        .where(
            and_(
                SessionTable.profile_id == profile_id,
                SessionTable.status == "COMPLETED",
                PerformedExerciseTable.exercise_id == exercise_id,
                SetTable.set_type == "working",
            )
        )
        .group_by(SessionTable.id, SessionTable.started_at)
        .order_by(SessionTable.started_at.desc())
        .limit(limit)
    )
    rows = db.execute(stmt).all()

    # اعكس الترتيب (الأقدم أولاً للرسم البياني)
    return [
        {
            "session_id": str(r[0]),
            "date": r[1].isoformat() if hasattr(r[1], 'isoformat') else str(r[1]),
            "max_weight": float(r[2] or 0),
            "e1rm": round(float(r[3] or 0), 1),
            "volume": float(r[4] or 0),
            "sets_count": int(r[5] or 0),
            "avg_rpe": round(float(r[6]), 1) if r[6] else None,
            "avg_rir": round(float(r[7]), 1) if r[7] else None,
        }
        for r in reversed(rows)
    ]


def get_exercise_prs(db: Session, profile_id: str, exercise_id: str) -> dict:
    """يجيب الأرقام القياسية (PRs) لتمرين معين."""
    # أفضل وزن
    stmt_max = (
        select(
            func.max(SetTable.weight).label("max_weight"),
        )
        .join(PerformedExerciseTable, SetTable.performed_exercise_id == PerformedExerciseTable.id)
        .join(SessionTable, PerformedExerciseTable.session_id == SessionTable.id)
        .where(
            and_(
                SessionTable.profile_id == profile_id,
                SessionTable.status == "COMPLETED",
                PerformedExerciseTable.exercise_id == exercise_id,
                SetTable.set_type == "working",
            )
        )
    )
    max_weight = db.execute(stmt_max).scalar_one_or_none() or Decimal("0")

    # أفضل e1RM
    stmt_e1rm = (
        select(
            SessionTable.started_at,
            SetTable.weight,
            SetTable.reps,
            (SetTable.weight * (1 + SetTable.reps / 30.0)).label("e1rm"),
        )
        .join(PerformedExerciseTable, SetTable.performed_exercise_id == PerformedExerciseTable.id)
        .join(SessionTable, PerformedExerciseTable.session_id == SessionTable.id)
        .where(
            and_(
                SessionTable.profile_id == profile_id,
                SessionTable.status == "COMPLETED",
                PerformedExerciseTable.exercise_id == exercise_id,
                SetTable.set_type == "working",
                SetTable.reps <= 12,
            )
        )
        .order_by((SetTable.weight * (1 + SetTable.reps / 30.0)).desc())
        .limit(1)
    )
    e1rm_row = db.execute(stmt_e1rm).first()

    # أفضل حجم في جلسة واحدة
    stmt_volume = (
        select(
            SessionTable.started_at,
            func.sum(SetTable.weight * SetTable.reps).label("volume"),
        )
        .join(PerformedExerciseTable, PerformedExerciseTable.session_id == SessionTable.id)
        .join(SetTable, SetTable.performed_exercise_id == PerformedExerciseTable.id)
        .where(
            and_(
                SessionTable.profile_id == profile_id,
                SessionTable.status == "COMPLETED",
                PerformedExerciseTable.exercise_id == exercise_id,
                SetTable.set_type == "working",
            )
        )
        .group_by(SessionTable.id, SessionTable.started_at)
        .order_by(func.sum(SetTable.weight * SetTable.reps).desc())
        .limit(1)
    )
    vol_row = db.execute(stmt_volume).first()

    return {
        "max_weight": {
            "value": float(max_weight),
            "date": None,
        },
        "best_e1rm": {
            "value": round(float(e1rm_row[3]), 1) if e1rm_row else 0.0,
            "weight": float(e1rm_row[1]) if e1rm_row else 0.0,
            "reps": int(e1rm_row[2]) if e1rm_row else 0,
            "date": e1rm_row[0].isoformat() if e1rm_row and hasattr(e1rm_row[0], 'isoformat') else None,
        } if e1rm_row else None,
        "best_volume": {
            "value": float(vol_row[1]) if vol_row else 0.0,
            "date": vol_row[0].isoformat() if vol_row and hasattr(vol_row[0], 'isoformat') else None,
        } if vol_row else None,
    }


def get_exercise_trend(db: Session, profile_id: str, exercise_id: str, days: int = 30):
    """يقارن آخر `days` يوم بـ `days` قبلها."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    recent_start = now - timedelta(days=days)
    older_start = recent_start - timedelta(days=days)

    def _period_stats(start, end):
        stmt = (
            select(
                func.max(SetTable.weight * (1 + SetTable.reps / 30.0)).label("e1rm"),
                func.sum(SetTable.weight * SetTable.reps).label("volume"),
                func.count(SetTable.id).label("sets_count"),
            )
            .join(PerformedExerciseTable, SetTable.performed_exercise_id == PerformedExerciseTable.id)
            .join(SessionTable, PerformedExerciseTable.session_id == SessionTable.id)
            .where(
                and_(
                    SessionTable.profile_id == profile_id,
                    SessionTable.status == "COMPLETED",
                    PerformedExerciseTable.exercise_id == exercise_id,
                    SetTable.set_type == "working",
                    SessionTable.started_at >= start,
                    SessionTable.started_at < end,
                )
            )
        )
        r = db.execute(stmt).first()
        return {
            "e1rm": round(float(r[0] or 0), 1),
            "volume": float(r[1] or 0),
            "sets": int(r[2] or 0),
        }

    recent = _period_stats(recent_start, now)
    older = _period_stats(older_start, recent_start)

    def _pct_change(new, old):
        if old == 0:
            return None
        return round((new - old) / old * 100, 1)

    return {
        "days": days,
        "recent": recent,
        "previous": older,
        "change_pct": {
            "e1rm": _pct_change(recent["e1rm"], older["e1rm"]),
            "volume": _pct_change(recent["volume"], older["volume"]),
            "sets": _pct_change(recent["sets"], older["sets"]),
        },
    }


# ═══════════════════════════════════════════════════════════
# 2) Muscle Balance
# ═══════════════════════════════════════════════════════════

def get_muscle_balance(db: Session, profile_id: str, weeks: int = 4):
    """يرجّع Sets/أسبوع لكل عضلة + تصنيف MEV/MAV/MRV."""
    cutoff = (datetime.now(timezone.utc).replace(tzinfo=None)
              - timedelta(weeks=weeks))

    stmt = (
        select(
            ExerciseTable.primary_muscle,
            func.count(SetTable.id).label("total_sets"),
        )
        .join(PerformedExerciseTable, SetTable.performed_exercise_id == PerformedExerciseTable.id)
        .join(ExerciseTable, PerformedExerciseTable.exercise_id == ExerciseTable.id)
        .join(SessionTable, PerformedExerciseTable.session_id == SessionTable.id)
        .where(
            and_(
                SessionTable.profile_id == profile_id,
                SessionTable.status == "COMPLETED",
                SetTable.set_type == "working",
                SessionTable.started_at >= cutoff,
                ExerciseTable.primary_muscle.is_not(None),
            )
        )
        .group_by(ExerciseTable.primary_muscle)
        .order_by(func.count(SetTable.id).desc())
    )

    # تصنيف MEV (10) / MAV (12-18) / MRV (20+)
    rows = db.execute(stmt).all()
    result = []
    for muscle, total_sets in rows:
        weekly = total_sets / max(weeks, 1)
        if weekly < 10:
            status = "below_mev"
        elif weekly <= 18:
            status = "optimal"
        elif weekly <= 22:
            status = "high"
        else:
            status = "above_mrv"

        result.append({
            "muscle": muscle,
            "weekly_sets": round(weekly, 1),
            "total_sets": int(total_sets),
            "status": status,
        })

    # Push / Pull / Legs
    push_muscles = ("chest", "shoulders", "triceps")
    pull_muscles = ("back", "biceps", "lats", "traps")
    leg_muscles = ("legs", "quads", "hamstrings", "glutes", "calves")

    push = sum(r["total_sets"] for r in result if r["muscle"] in push_muscles)
    pull = sum(r["total_sets"] for r in result if r["muscle"] in pull_muscles)
    legs = sum(r["total_sets"] for r in result if r["muscle"] in leg_muscles)
    total = push + pull + legs

    return {
        "period_weeks": weeks,
        "muscles": result,
        "summary": {
            "push": {"sets": push, "pct": round(push / total * 100, 1) if total else 0},
            "pull": {"sets": pull, "pct": round(pull / total * 100, 1) if total else 0},
            "legs": {"sets": legs, "pct": round(legs / total * 100, 1) if total else 0},
            "push_pull_ratio": round(pull / push, 2) if push else None,
        },
    }


# ═══════════════════════════════════════════════════════════
# 3) Plateau Detection
# ═══════════════════════════════════════════════════════════

def get_plateaus(db: Session, profile_id: str, weeks: int = 3, min_sessions: int = 3):
    """يكتشف التمارين اللي ما تحسّنت في آخر `weeks` أسابيع."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    cutoff = now - timedelta(weeks=weeks)

    # كل التمارين اللي تمارس
    stmt = (
        select(
            ExerciseTable.id,
            ExerciseTable.name,
            ExerciseTable.primary_muscle,
        )
        .join(PerformedExerciseTable, ExerciseTable.id == PerformedExerciseTable.exercise_id)
        .join(SessionTable, PerformedExerciseTable.session_id == SessionTable.id)
        .where(
            and_(
                SessionTable.profile_id == profile_id,
                SessionTable.status == "COMPLETED",
            )
        )
        .group_by(ExerciseTable.id, ExerciseTable.name, ExerciseTable.primary_muscle)
        .having(func.count(func.distinct(SessionTable.id)) >= min_sessions)
    )
    exercises = db.execute(stmt).all()

    plateaus = []
    for ex_id, name, muscle in exercises:
        # e1RM لكل جلسة في آخر `weeks`
        stmt2 = (
            select(
                SessionTable.id,
                SessionTable.started_at,
                func.max(SetTable.weight * (1 + SetTable.reps / 30.0)).label("e1rm"),
            )
            .join(PerformedExerciseTable, SetTable.performed_exercise_id == PerformedExerciseTable.id)
            .join(SessionTable, PerformedExerciseTable.session_id == SessionTable.id)
            .where(
                and_(
                    SessionTable.profile_id == profile_id,
                    SessionTable.status == "COMPLETED",
                    PerformedExerciseTable.exercise_id == ex_id,
                    SetTable.set_type == "working",
                    SetTable.reps <= 12,
                    SessionTable.started_at >= cutoff,
                )
            )
            .group_by(SessionTable.id, SessionTable.started_at)
            .order_by(SessionTable.started_at)
        )
        sessions = db.execute(stmt2).all()

        if len(sessions) < 2:
            continue

        first_e1rm = float(sessions[0][2] or 0)
        max_e1rm = max(float(s[2] or 0) for s in sessions)
        improvement = ((max_e1rm - first_e1rm) / first_e1rm * 100) if first_e1rm > 0 else 0

        if improvement < 2:
            plateaus.append({
                "exercise_id": str(ex_id),
                "name": name,
                "muscle": muscle,
                "sessions_count": len(sessions),
                "first_e1rm": round(first_e1rm, 1),
                "max_e1rm": round(max_e1rm, 1),
                "improvement_pct": round(improvement, 1),
            })

    plateaus.sort(key=lambda x: x["improvement_pct"])
    return {"period_weeks": weeks, "plateaus": plateaus}


# ═══════════════════════════════════════════════════════════
# 4) RIR / RPE Analysis
# ═══════════════════════════════════════════════════════════

def get_effort_analysis(db: Session, profile_id: str, weeks: int = 8):
    """يحلل توزيع RIR و RPE."""
    cutoff = (datetime.now(timezone.utc).replace(tzinfo=None)
              - timedelta(weeks=weeks))

    # الإجمالي
    stmt = (
        select(
            func.count(SetTable.id).label("total"),
            func.avg(SetTable.rir).label("avg_rir"),
            func.avg(SetTable.rpe).label("avg_rpe"),
            func.sum(case((SetTable.rir.is_not(None), 1), else_=0)).label("with_rir"),
            func.sum(case((SetTable.rpe.is_not(None), 1), else_=0)).label("with_rpe"),
        )
        .join(PerformedExerciseTable, SetTable.performed_exercise_id == PerformedExerciseTable.id)
        .join(SessionTable, PerformedExerciseTable.session_id == SessionTable.id)
        .where(
            and_(
                SessionTable.profile_id == profile_id,
                SessionTable.status == "COMPLETED",
                SetTable.set_type == "working",
                SessionTable.started_at >= cutoff,
            )
        )
    )
    total, avg_rir, avg_rpe, with_rir, with_rpe = db.execute(stmt).first()

    # توزيع RIR
    stmt2 = (
        select(SetTable.rir, func.count(SetTable.id))
        .join(PerformedExerciseTable, SetTable.performed_exercise_id == PerformedExerciseTable.id)
        .join(SessionTable, PerformedExerciseTable.session_id == SessionTable.id)
        .where(
            and_(
                SessionTable.profile_id == profile_id,
                SessionTable.status == "COMPLETED",
                SetTable.set_type == "working",
                SetTable.rir.is_not(None),
                SessionTable.started_at >= cutoff,
            )
        )
        .group_by(SetTable.rir)
        .order_by(SetTable.rir)
    )
    rir_dist = [{"rir": int(r), "count": int(c)} for r, c in db.execute(stmt2).all()]

    # توزيع RPE
    stmt3 = (
        select(func.round(SetTable.rpe), func.count(SetTable.id))
        .join(PerformedExerciseTable, SetTable.performed_exercise_id == PerformedExerciseTable.id)
        .join(SessionTable, PerformedExerciseTable.session_id == SessionTable.id)
        .where(
            and_(
                SessionTable.profile_id == profile_id,
                SessionTable.status == "COMPLETED",
                SetTable.set_type == "working",
                SetTable.rpe.is_not(None),
                SessionTable.started_at >= cutoff,
            )
        )
        .group_by(func.round(SetTable.rpe))
        .order_by(func.round(SetTable.rpe))
    )
    rpe_dist = [{"rpe": float(r), "count": int(c)} for r, c in db.execute(stmt3).all()]

    return {
        "period_weeks": weeks,
        "total_sets": int(total or 0),
        "avg_rir": round(float(avg_rir), 2) if avg_rir else None,
        "avg_rpe": round(float(avg_rpe), 2) if avg_rpe else None,
        "coverage": {
            "with_rir_pct": round(int(with_rir or 0) / int(total) * 100, 1) if total else 0,
            "with_rpe_pct": round(int(with_rpe or 0) / int(total) * 100, 1) if total else 0,
        },
        "rir_distribution": rir_dist,
        "rpe_distribution": rpe_dist,
        "warning": (
            "متوسط RIR منخفض جداً (تحت 2) — أنت تتدرب للفشل دائماً. هذا يفسّر التعب السريع."
            if avg_rir is not None and float(avg_rir) < 2
            else None
        ),
    }


# ═══════════════════════════════════════════════════════════
# 5) Weekly Trends
# ═══════════════════════════════════════════════════════════

def get_weekly_trends(db: Session, profile_id: str, weeks: int = 12):
    """يرجّع مجموع Sets و Volume لكل أسبوع."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    start = now - timedelta(weeks=weeks)

    stmt = (
        select(
            func.strftime('%Y-%W', SessionTable.started_at).label("week"),
            func.count(func.distinct(SessionTable.id)).label("sessions"),
            func.count(SetTable.id).label("sets"),
            func.sum(SetTable.weight * SetTable.reps).label("volume"),
        )
        .join(PerformedExerciseTable, PerformedExerciseTable.session_id == SessionTable.id)
        .join(SetTable, SetTable.performed_exercise_id == PerformedExerciseTable.id)
        .where(
            and_(
                SessionTable.profile_id == profile_id,
                SessionTable.status == "COMPLETED",
                SetTable.set_type == "working",
                SessionTable.started_at >= start,
            )
        )
        .group_by(func.strftime('%Y-%W', SessionTable.started_at))
        .order_by(func.strftime('%Y-%W', SessionTable.started_at))
    )

    return [
        {
            "week": r[0],
            "sessions": int(r[1]),
            "sets": int(r[2]),
            "volume": float(r[3] or 0),
        }
        for r in db.execute(stmt).all()
    ]


# ═══════════════════════════════════════════════════════════
# 6) Available Exercises (للقائمة المنسدلة)
# ═══════════════════════════════════════════════════════════

def get_available_exercises(db: Session, profile_id: str):
    """يرجّع التمارين اللي استُخدمت في جلسات (للقائمة المنسدلة)."""
    stmt = (
        select(
            ExerciseTable.id,
            ExerciseTable.name,
            ExerciseTable.primary_muscle,
            func.count(func.distinct(SessionTable.id)).label("sessions_count"),
            func.count(SetTable.id).label("sets_count"),
        )
        .join(PerformedExerciseTable, ExerciseTable.id == PerformedExerciseTable.exercise_id)
        .join(SessionTable, PerformedExerciseTable.session_id == SessionTable.id)
        .join(SetTable, SetTable.performed_exercise_id == PerformedExerciseTable.id)
        .where(
            and_(
                SessionTable.profile_id == profile_id,
                SessionTable.status == "COMPLETED",
                SetTable.set_type == "working",
            )
        )
        .group_by(ExerciseTable.id, ExerciseTable.name, ExerciseTable.primary_muscle)
        .having(func.count(SetTable.id) >= 3)
        .order_by(func.count(SetTable.id).desc())
    )
    return [
        {
            "id": str(r[0]),
            "name": r[1],
            "muscle": r[2],
            "sessions_count": int(r[3]),
            "sets_count": int(r[4]),
        }
        for r in db.execute(stmt).all()
    ]



# ═══════════════════════════════════════════════════════════
# 7) Actionable Insights (القرارات الذكية)
# ═══════════════════════════════════════════════════════════

def get_actionable_insights(db: Session, profile_id: str, weeks: int = 8):
    """يرجّع قائمة قرارات واضحة مبنية على البيانات."""
    insights = []

    # 1) RIR منخفض جداً
    effort = get_effort_analysis(db, profile_id, weeks=weeks)
    if effort["avg_rir"] is not None and effort["avg_rir"] < 2:
        insights.append({
            "priority": "high",
            "icon": "🚨",
            "title": "خفّف الشدة فوراً",
            "message": f"متوسط RIR عندك {effort['avg_rir']} — أنت تتدرب للفشل في كل مجموعة. هذا يفسّر التعب السريع.",
            "action": "في الجلسات القادمة، توقف عندما يتبقى لك 2-3 تكرارات قبل الفشل (RIR 2-3).",
        })

    # 2) Pull/Push غير متوازن
    mb = get_muscle_balance(db, profile_id, weeks=weeks)
    ratio = mb["summary"].get("push_pull_ratio")
    if ratio is not None and ratio < 0.8:
        diff = mb["summary"]["push"]["sets"] - mb["summary"]["pull"]["sets"]
        add_sets = max(6, diff // weeks + 4)
        insights.append({
            "priority": "high",
            "icon": "⚠️",
            "title": "زد تمارين السحب",
            "message": f"Pull/Push = {ratio}. عندك {mb['summary']['push']['sets']} مجموعة دفع مقابل {mb['summary']['pull']['sets']} سحب. هذا يهدد كتفك.",
            "action": f"أضف ~{add_sets} مجموعات سحب أسبوعياً. اقتراح: Face Pull (3)، Reverse Fly (3)، Seated Row (3).",
        })

    # 3) عضلات تحت MEV
    low_muscles = [m for m in mb["muscles"] if m["status"] == "below_mev"][:3]
    if low_muscles:
        names = ", ".join([m["muscle"] for m in low_muscles])
        insights.append({
            "priority": "medium",
            "icon": "📉",
            "title": "عضلات تحت الحد الأدنى",
            "message": f"هذي العضلات أقل من MEV: {names}. لازم 10+ مجموعة أسبوعياً للنمو.",
            "action": "أضف تمرين لكل عضلة ناقصة (3 مجموعات × 2 جلسات = 6 أسبوعياً).",
        })

    # 4) الجمود
    pl = get_plateaus(db, profile_id, weeks=3, min_sessions=2)
    if pl["plateaus"]:
        top = pl["plateaus"][:3]
        names = ", ".join([p["name"] for p in top])
        insights.append({
            "priority": "medium",
            "icon": "⏸️",
            "title": "تمارين في جمود",
            "message": f"{len(pl['plateaus'])} تمارين ما تحسّنت 3 أسابيع: {names}.",
            "action": "لأي تمرين في جمود: زد الوزن 2.5 كجم، أو غيّر التمرين مؤقتاً.",
        })

    # 5) Trends متراجع
    trends = get_weekly_trends(db, profile_id, weeks=weeks)
    if len(trends) >= 4:
        recent = trends[-4:]
        first_avg = sum(t["volume"] for t in recent[:2]) / 2
        last_avg = sum(t["volume"] for t in recent[-2:]) / 2
        if first_avg > 0:
            change = (last_avg - first_avg) / first_avg * 100
            if change < -15:
                insights.append({
                    "priority": "high",
                    "icon": "📉",
                    "title": "الحجم يتراجع",
                    "message": f"الحجم الأسبوعي نقص {abs(change):.0f}% في آخر 4 أسابيع.",
                    "action": "راجع عدد الجلسات — هل تتغيب؟ رجّع لـ 3-4 جلسات أسبوعياً.",
                })
            elif change > 15:
                insights.append({
                    "priority": "low",
                    "icon": "📈",
                    "title": "الحجم يتحسن",
                    "message": f"الحجم الأسبوعي زاد {change:.0f}% — ممتاز!",
                    "action": "استمر بنفس الوتيرة، بس راقب الاستشفاء.",
                })

    # 6) نجاحات (positive feedback)
    if not insights:
        insights.append({
            "priority": "low",
            "icon": "✅",
            "title": "كل شي تمام",
            "message": "ما فيه أي مشاكل واضحة في بياناتك.",
            "action": "استمر بنفس الوتيرة.",
        })
    elif effort["avg_rir"] and effort["avg_rir"] >= 2:
        insights.append({
            "priority": "low",
            "icon": "✅",
            "title": "RIR في النطاق المثالي",
            "message": f"متوسط RIR = {effort['avg_rir']} — مثالي للتضخيم.",
            "action": "استمر على نفس الشدة.",
        })

    # ترتيب حسب الأولوية
    priority_order = {"high": 0, "medium": 1, "low": 2}
    insights.sort(key=lambda x: priority_order.get(x["priority"], 3))

    return insights
