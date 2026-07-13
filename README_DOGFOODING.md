# MyGym Pro Core - Sprint 2 (Dogfooding)

## التشغيل السريع

### 1. تثبيت المتطلبات
```bash
pip install -r requirements.txt
```

### 2. تشغيل الخادم
```bash
python -m src.apis.main
# أو
uvicorn src.apis.main:app --reload --host 0.0.0.0 --port 8000
```

### 3. فتح التطبيق
- **الكمبيوتر:** http://localhost:8000
- **الهاتف (على نفس الشبكة):** http://[your-ip]:8000

## البنية

```
MyGymV2/
├── src/
│   ├── apis/
│   │   ├── main.py           ← FastAPI app
│   │   ├── deps.py           ← Database helpers
│   │   ├── schemas.py        ← Pydantic DTOs
│   │   └── routers/
│   │       ├── sessions.py   ← Workout endpoints
│   │       └── exercises.py  ← Exercise library
│   ├── services/
│   │   ├── session_service.py
│   │   └── units_service.py
│   ├── infrastructure/
│   │   └── db/
│   │       ├── connection.py
│   │       └── models.py
│   └── domain/
│       ├── entities.py
│       └── enums.py
├── static/
│   ├── app.js                ← Frontend logic
│   └── style.css             ← Mobile-first CSS
├── templates/
│   ├── index.html            ← Home / History
│   └── workout.html          ← Active workout
└── requirements.txt
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/workouts/start` | Start new workout |
| GET | `/api/workouts/active` | Get active workout |
| GET | `/api/workouts/{id}` | Get workout details |
| POST | `/api/workouts/{id}/sets` | Add set |
| PATCH | `/api/sets/{id}` | Update set |
| DELETE | `/api/sets/{id}` | Delete set |
| POST | `/api/workouts/{id}/finish` | Finish workout |
| POST | `/api/workouts/{id}/abandon` | Abandon workout |
| GET | `/api/workouts/{id}/last-set` | Get last set for exercise |
| GET | `/api/exercises` | Get exercise library |

## ميزات Sprint 2

- ✅ FastAPI backend مع SQLAlchemy
- ✅ HTML/CSS/JS frontend بسيط (بدون React/Vue)
- ✅ تسجيل التمارين (Start → Add Set → Finish)
- ✅ Exercise Library API
- ✅ تكرار آخر مجموعة (Repeat Last Set)
- ✅ حساب الحجم تلقائي
- ✅ Snackbar notifications بدلاً من alerts
- ✅ تصميم متجاوب للهاتف
- ✅ Transaction boundaries لكل عملية
- ✅ Foreign Keys مفعلة في SQLite
- ✅ Indexes على الأعمدة المستخدمة في الاستعلامات

## Dogfooding Sprint (أسبوع واحد)

1. استخدم التطبيق في كل تمرين
2. سجل الملاحظات:
   - أين يتأخر التطبيق؟
   - أين تحتاج ميزة جديدة؟
   - ما هي الأخطاء؟
3. لا تضيف ميزات جديدة إلا لإصلاح مشكلة
4. بعد أسبوع: قرر الأولويات للتطوير القادم

## الخطوة التالية

بعد أسبوع Dogfooding:
- مراجعة الملاحظات
- إصلاح الأخطاء
- إضافة ميزات بناءً على الاستخدام الحقيقي
