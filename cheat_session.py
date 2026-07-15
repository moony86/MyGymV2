from datetime import datetime, timezone, timedelta
from src.infrastructure.db.connection import SessionLocal
from src.infrastructure.db.models import SessionTable
from src.domain.enums import SessionStatus

db = SessionLocal()

# 1. تحقق أولاً للتأكد من عدم وجود جلسة نشطة حالياً لتجنب المشاكل
active_session = db.query(SessionTable).filter(SessionTable.status == SessionStatus.ACTIVE.value).first()

if active_session:
    print("❌ خطأ: لديك جلسة مفتوحة بالفعل في التطبيق! قم بإغلاقها أولاً من الواجهة قبل تنفيذ الخدعة.")
else:
    # 2. حدد التاريخ القديم (مثلاً: قبل يومين الساعة 6 مساءً)
    day = datetime.now(timezone.utc) - timedelta(days=2)
    backdated_start = day.replace(hour=18, minute=0, second=0, microsecond=0)

    # 3. إنشاء جلسة بحالة ACTIVE ولكن بتاريخ قديم
    session = SessionTable(
        status=SessionStatus.ACTIVE.value,
        started_at=backdated_start
    )
    
    db.add(session)
    db.commit()
    
    print(f"✅ تم بنجاح زرع جلسة نشطة بتاريخ قديم ({backdated_start.strftime('%Y-%m-%d %H:%M')})")
    print("📱 افتح الواجهة الآن، ستجد الجلسة مفتوحة بانتظارك لتعديلها وإضافة تمارينك!")
