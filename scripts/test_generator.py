from src.infrastructure.db.connection import SessionLocal
from src.infrastructure.db.models import TrainingProfileTable, DEFAULT_PROFILE_ID
from src.services.generator_service import GeneratorService

db = SessionLocal()
profile = db.query(TrainingProfileTable).filter(TrainingProfileTable.id == DEFAULT_PROFILE_ID).first()

if not profile:
    print("❌ ما فيه بروفايل محفوظ. روح /profile-setup وعبّي بياناتك أول.")
else:
    service = GeneratorService(db)

    # 🎯 إرجاع قائمة بالجداول المنشأة لكل يوم بناءً على المصفوفة
    plans = service.generate_plan_for_profile(profile)

    print(f"✅ تم إنشاء البرنامج الأسبوعي بنجاح! عدد الأيام/الجداول: {len(plans)}\n")

    for plan in plans:
        print(f"📌 ═══ {plan.name} (id={plan.id}) ═══")
        plan_details = service.planner.get_plan_with_details(plan.id)
        exercises_list = plan_details.get("exercises", [])
        exercise_names = plan_details.get("exercise_names", {})

        for idx, pe in enumerate(exercises_list, start=1):
            name = exercise_names.get(pe.exercise_id, "Unknown")
            print(f"  {idx}. {name} — {pe.target_sets} sets × {pe.target_reps} reps")
        print()

db.close()
