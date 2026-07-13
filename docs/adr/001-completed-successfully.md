# ADR: إضافة حقل `completed_successfully` إلى Set

## الحالة
مقبول

## السياق
نحتاج لتحديد ما إذا كان الـ Set مكتملاً بنجاح أم لا، خاصة في حالة فشل الـ Set (Failure) أو Dropset. هذا يؤثر على `get_suggested_weight()` لأنه يجب أن يقترح الوزن من آخر Working Set المكتمل بنجاح، وليس آخر Set بشكل عام.

## القرار
إضافة حقل `completed_successfully: bool` إلى كيان `Set` مع القيمة الافتراضية `True`.

## الآثار
- `Set` يصبح قابلاً للتعديل مؤقتاً (لن يتم استخدام Event Sourcing حالياً).
- عند تسجيل Set كفشل (`FAILURE`) أو `DROPSET`، يتم تعيين `completed_successfully = False`.
- `get_suggested_weight()` يبحث عن آخر `Set` حيث `set_type == SetType.WORKING` و `completed_successfully == True`.
- يتطلب تحديث `SessionService.add_set()` لقبول هذا الحقل.

## البدائل
- استخدام `set_type == SetType.FAILURE` كدليل على الفشل. لكن هذا لا يغطي الحالات التي يفشل فيها المستخدم في Reps المطلوبة مع الحفاظ على الوزن.

## المراجع
- Narrative要求: get_suggested_weight() يجب أن يتجاهل Sets الفاشلة.
