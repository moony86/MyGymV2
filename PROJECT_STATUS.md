# حالة مشروع Gym Knowledge Engine — ملخص للاستئناف

## ✅ منجز وشغال
1. القاعدة المعرفية (YAML) + Loader/Provider/Queries/Validator — موجودة مسبقًا وسليمة (src/knowledge/)
2. عمود الربط `knowledge_variant_id` على `ExerciseTable` — مضاف عبر alembic migration
3. كل الـ 28 صف بجدول `exercises` مربوطة بـ variants القاعدة المعرفية (عبر match_exercises_to_knowledge.py + apply_knowledge_matching.py)
4. `src/services/generator_service.py` — GeneratorService شغال فعليًا:
   - يختار Template مناسب حسب experience/days/goal
   - يختار تمرين + variant لكل حركة مطلوبة (movement_selection.required)
   - عنده fallback: يجرب كل الـ variants المتاحة لين يلقى وحدة مربوطة بجدول exercises (بدل التخطي الصامت)
   - يسجل تحذيرات صريحة بـ self.warnings لو فشلت حركة معينة بالكامل
   - يحسب sets/reps من training_rules.yaml حسب الهدف
   - يحفظ الخطة فعليًا عبر PlannerService الموجود (create_plan + add_exercise_to_plan)
   - تم اختباره: يطلع خطة Full Body كاملة 6/6 تمارين بدون تحذيرات

## ✅ إنجازات إضافية (الجلسة الثانية)
5. إصلاح خلل جوهري بالمطابقة: `target_categories` صارت تستخدم IDs رسمية
   (`group.chest` بدل `"chest"` كنص حر) + الكود صار يطابق عبر
   `provider.muscle(id).group` بدل substring matching الهش.
6. Round-robin بدل القطع الأعمى بأول 6 تمارين: يوزّع الاختيار بالتساوي
   بين target_categories، ويستخدم primary_muscles + secondary_muscles
   معًا (بدل primary فقط) لضمان عدم إقصاء أي مجموعة عضلية بصمت.
7. إصلاح خلل PPL: كان يُختار الأبسط (complexity_index الأقل) دائمًا،
   فـ PPL يستحيل يظهر رغم دعمه لعدد الأيام. الآن يُختار الأقرب لـ
   supported_days.recommended.
8. اختيار قالب يدوي اختياري (template_id) + تحذير صريح لو غير مناسب
   لمستوى/هدف/أيام المستخدم، بدل رفض أو تجاهل صامت.
9. program_group_id + day_index على WorkoutPlanTable: تربط كل خطط
   الأيام الناتجة من استدعاء توليد واحد تحت "برنامج" أسبوعي واحد.
   مُختبر وشغّال (نفس group_id عبر كل الأيام، day_index مرتب صح).
10. EvaluatorService: يحسب weekly working sets فعلي لكل عضلة عبر
    برنامج كامل (primary=وزن 1.0، secondary=وزن 0.5)، يرفعها لمستوى
    المجموعة العضلية، ويقارنها بـ weekly_volume (training_rules.yaml)
    حسب هدف المستخدم. يرجّع تقرير PASS/WARNING/FAIL لكل عضلة رئيسية
    وثانوية + قائمة تمارين غير محسوبة (بدون ربط معرفي).
11. واجهة أمامية: زر "توليد برنامج تلقائي" مع اختيار قالب اختياري،
    عرض تحذيرات الـ Generator، وزر "تقييم تغطية البرنامج" يعرض تقرير
    الـ Evaluator كجدول (عضلة / حجم فعلي / موصى به / حالة).

## 🔲 التالي (لم يُنفَّذ بعد)
1. **بيانات جسدية غير مستغلة (الطول/الوزن/العمر)**: موجودة بالبروفايل لكن الـ Generator
   ما يستخدمها. استخدام مستقبلي منطقي: حساب TDEE لهدف FAT_LOSS (معادلة Mifflin-St Jeor
   تحتاج الطول+الوزن+العمر+الجنس)، وربما تقدير حمل تمارين وزن الجسم.

2. **نقص بيانات بجدول exercises**: بعض الـ variants الآمنة (خصوصًا لـ hip_hinge مثل
   Cable Pull Through أو Back Extension) موجودة بالقاعدة المعرفية لكن ما فيها صف مقابل
   بجدول exercises بعد، فالـ Generator يضطر يستخدم بدائل أقل أفضلية أحيانًا. يحتاج
   إضافة صفوف جديدة + تشغيل matching script عليها.

3. **تحسين تجميلي (مؤجل، مو أولوية)**: ترتيب target_categories بالـ round-robin ثابت
   (نفس الفئة تاخذ "الحصة الزايدة" دائمًا). يمكن shuffle الترتيب بين الأسابيع لاحقًا.

4. **تحسين تجميلي (مؤجل)**: weekly_volume بملف training_rules.yaml معرّف بشكل عام
   (hypertrophy/strength) بدون تمييز لكل عضلة/مجموعة على حدة. لو احتجنا دقة أعلى
   لاحقًا (مثلاً عضلات صغيرة تحتاج حجم أقل من عضلات كبيرة)، نحتاج نفصّل القواعد أكثر.

## ملفات مهمة (بالمشروع)
- src/knowledge/{loader,models,provider,queries,validator}.py — القاعدة المعرفية (جاهزة)
- src/services/generator_service.py — الملف الرئيسي المطلوب تطويره بالخطوات القادمة
- src/services/planner_service.py — يوفر create_plan/add_exercise_to_plan (لا تغيير مطلوب عليه)
- knowledge/generator_rules.yaml — هنا سيُضاف قسم split_definitions لاحقًا
- knowledge/training_rules.yaml — يحتوي exercise_limits المستخدمة لإضافة accessories

## طريقة الاستئناف
ألصق هذا الملف كامل بأول رسالة بمحادثة جديدة، وقل: "نكمل من نقطة [1 أو 2 أو 3]"
