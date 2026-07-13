# استعلامات قاعدة البيانات - الإرشادات

## المبادئ العامة

1. **لا توجد N+1 Queries**
   - استخدم `selectinload` أو `joinedload` للعلاقات دائماً.
   - لا تقم بالاستعلام داخل حلقات Python.

2. **استخدم SQL للتجميع**
   - استخدم `SUM`, `COUNT`, `AVG`, `MAX` في SQL بدلاً من جلب كل الصفوف وحسابها في Python.
   - مثال:
     ```python
     # خاطئ
     sets = db.query(Set).all()
     total = sum(s.weight * s.reps for s in sets)

     # صحيح
     total = db.query(func.sum(Set.weight * Set.reps)).scalar()
     ```

3. **حدود الاستعلام**
   - جميع استعلامات التاريخ (`History`) يجب أن تدعم `limit` و `offset`.
   - استخدم `paginate()` أو `limit()` دائماً للجداول الكبيرة.

4. **الفهارس (Indexes)**
   - أضف فهرساً على أي عمود يُستخدم في `filter()` أو `order_by()` بشكل متكرر.
   - راجع `models.py` لمعرفة الفهارس المفعلة.

5. **الفصل بين الاستعلامات والخدمات**
   - استعلامات SQL البسيطة تذهب إلى `queries/`.
   - منطق الأعمال يبقى في `services/`.
   - لا تضع SQL مباشرة في Services.

6. **العلاقات**
   - استخدم `selectinload` للجلب الكلي للعلاقات One-to-Many.
   - استخدم `joinedload` للعلاقات Many-to-One أو One-to-One.

7. **الأنواع**
   - استخدم `Numeric` للأوزان والمالية.
   - استخدم `DateTime` دائماً مع `timezone.utc`.
   - لا تستخدم `Float` للأوزان.

8. **الأداء**
   - تجنب `SELECT *`.
   - اختر الأعمدة المطلوبة فقط (`select(Column1, Column2)`).
   - استخدم `scalar_one_or_none()` بدلاً من `first()` عندما تتوقع قيمة واحدة.

## مثال على الاستعلام الأمثل

```python
from sqlalchemy import select, func
from src.infrastructure.db.models import SetTable, PerformedExerciseTable

def get_exercise_volume(db, exercise_id: str, limit: int = 10):
    stmt = (
        select(
            PerformedExerciseTable.exercise_id,
            func.sum(SetTable.weight * SetTable.reps).label("total_volume")
        )
        .join(SetTable, SetTable.performed_exercise_id == PerformedExerciseTable.id)
        .where(PerformedExerciseTable.exercise_id == exercise_id)
        .group_by(PerformedExerciseTable.exercise_id)
        .order_by(func.sum(SetTable.weight * SetTable.reps).desc())
        .limit(limit)
    )
    return db.execute(stmt).all()
```
