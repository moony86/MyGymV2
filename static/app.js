/**
 * =========================================================================
 * 🏋️ MYGYM CORE APP - ARCHITECTURE V2.2 (MONOLITHIC PRODUCTION)
 * =========================================================================
 * نسخة مطهرة بالكامل بناءً على مراجعة معمارية رفيعة المستوى.
 * تم توحيد مصدر الحقيقة، إلغاء تعديلات الـ UI للـ State، ودعم أزرار التحميل الديناميكية.
 */

// 1️⃣ STATE (مستودع البيانات المركزي النظيف والمدمج)
const state = {
    workout: null,     // كائن الجلسة الموحد القادم من السيرفر ActiveSessionDTO { session, sets, last_set, total_volume }
    exercises: []      // مكتبة التمارين الكاملة المحملة من الباكيند
};

let timerInterval = null;

// 2️⃣ API LAYER (الطبقة الوحيدة المسؤولة عن الـ fetch والاتصال بالشبكة)
const API = {
    BASE_URL: '/api',

    async request(path, options = {}) {
        const url = `${this.BASE_URL}${path}`;
        const config = {
            headers: { 'Content-Type': 'application/json', ...options.headers },
            ...options
        };

        const res = await fetch(url, config);
        if (!res.ok) {
            const error = await res.json().catch(() => ({ detail: res.statusText }));
            throw new Error(error.detail || res.statusText);
        }
        return res.json();
    },

    async get(path) { return this.request(path, { method: 'GET' }); },
    async post(path, body) { return this.request(path, { method: 'POST', body: JSON.stringify(body) }); }
};

// 3️⃣ SESSION MANAGER (إدارة دورة حياة الجلسات الرياضية - السيرفر هو مصدر الحقيقة الكامل)
const SessionManager = {
    async restore() {
        try {
            const data = await API.get('/workouts/active');
            if (data && data.session) {
                state.workout = data; // مزامنة كائن الباكيند الموحد بالكامل في الـ state
                return data;
            }
            state.workout = null;
            return null;
        } catch (e) {
            console.error("🔒 فشل في مزامنة الجلسة النشطة من السيرفر:", e);
            state.workout = null;
            return null;
        }
    },

    async start(buttonEl) {
        UI.setButtonLoading(buttonEl, '🚀 جاري البدء...', true);
        try {
            const data = await API.post('/workouts/start', { notes: "" });
            if (data && data.id) {
                // اقتراحك الذكي: الباكيند هو مصدر الحقيقة، نستدعي restore لجلب الكائن كاملاً بدلاً من بنائه يدوياً
                await this.restore();
                UI.showSnackbar('🏋️‍♂️ تم بدء جلسة تدريبية جديدة، كفو!');
                Router.workout();
            } else {
                throw new Error("تنسيق رد السيرفر غير متوافق عند بدء الجلسة");
            }
        } catch (e) {
            UI.showSnackbar(e.message, 'error');
        } finally {
            UI.setButtonLoading(buttonEl, 'ابدأ تمرينًا', false);
        }
    },

    async addSet(setData) {
        if (!state.workout || !state.workout.session) return;
        return await API.post(`/workouts/${state.workout.session.id}/sets`, setData);
    },

    async finish(buttonEl) {
        if (!confirm('هل أنت متأكد من إنهاء الحصة التدريبية بالكامل وحفظها؟')) return;
        const originalText = buttonEl.textContent;
        UI.setButtonLoading(buttonEl, '🏁 جاري الحفظ...', true);
        try {
            await API.post(`/workouts/${state.workout.session.id}/finish`, {});
            UI.showSnackbar('🎉 كفو عليك! تم إنهاء التمرين وحفظه بنجاح.');
            state.workout = null;
            setTimeout(() => Router.home(), 1000);
        } catch (e) {
            UI.showSnackbar(e.message, 'error');
            UI.setButtonLoading(buttonEl, originalText, false);
        }
    },

    async abandon(buttonEl) {
        if (!confirm('هل أنت متأكد من إلغاء وحذف هذه الجلسة؟ سيتم تصفير كل شيء ولن يُسجل أي بيان.')) return;
        const originalText = buttonEl.textContent;
        UI.setButtonLoading(buttonEl, '🗑️ جاري الحذف...', true);
        try {
            await API.post(`/workouts/${state.workout.session.id}/abandon`, {});
            UI.showSnackbar('🗑️ تم إلغاء الحصة وحذفها بنجاح.', 'info');
            state.workout = null;
            setTimeout(() => Router.home(), 1000);
        } catch (e) {
            UI.showSnackbar(e.message, 'error');
            UI.setButtonLoading(buttonEl, originalText, false);
        }
    }
};

// 4️⃣ EXERCISE MANAGER (المسؤول عن معالجة وإدخال المجموعات الذكية)
const ExerciseManager = {
    async loadExercises() {
        try {
            state.exercises = await API.get('/exercises');
            this.populateSelect();
        } catch (e) {
            UI.showSnackbar('خطأ أثناء تحميل مكتبة التمارين', 'error');
        }
    },

    populateSelect() {
        const select = document.getElementById('exercise-select');
        if (!select || select.options.length > 1) return;

        state.exercises.forEach(ex => {
            const opt = document.createElement('option');
            opt.value = ex.id;
            opt.textContent = ex.name;
            select.appendChild(opt);
        });
    },

    handleChange() {
        const select = document.getElementById('exercise-select');
        const dynamicSection = document.getElementById('dynamic-sets-section');
        const tbody = document.getElementById('dynamic-sets-body');

        if (!select.value) {
            dynamicSection.style.display = 'none';
            return;
        }

        dynamicSection.style.display = 'block';
        tbody.innerHTML = '';

        for (let i = 1; i <= 3; i++) { this.addNewRow(); }
    },

    addNewRow() {
        const tbody = document.getElementById('dynamic-sets-body');
        const rowCount = tbody.rows.length + 1;

        let defaultWeight = '';
        let defaultReps = '';
        const rows = Array.from(tbody.rows);

        // البحث العكسي الذكي عن آخر صف يحتوي على قيم مدخلة فعلاً
        for (let i = rows.length - 1; i >= 0; i--) {
            const wVal = rows[i].querySelector('.weight-input').value;
            const rVal = rows[i].querySelector('.reps-input').value;
            if (wVal || rVal) {
                defaultWeight = wVal;
                defaultReps = rVal;
                break;
            }
        }

        const tr = document.createElement('tr');
        tr.className = 'set-table-row';
        tr.innerHTML = `
        <td class="set-number-cell">${rowCount}</td>
        <td><input type="number" class="table-input weight-input" step="0.1" inputmode="decimal" value="${defaultWeight}" placeholder="0"></td>
        <td><input type="number" class="table-input reps-input" inputmode="numeric" value="${defaultReps}" placeholder="0"></td>
        <td><button class="btn-delete-row" onclick="this.closest('tr').remove(); ExerciseManager.reindexRows();">❌</button></td>
        `;
        tbody.appendChild(tr);
    },

    reindexRows() {
        const rows = document.querySelectorAll('#dynamic-sets-body tr');
        rows.forEach((row, idx) => {
            row.querySelector('.set-number-cell').textContent = idx + 1;
        });
    },

    async saveWholeExercise(buttonEl) {
        const select = document.getElementById('exercise-select');
        const rows = document.querySelectorAll('#dynamic-sets-body tr');
        const exerciseName = select.options[select.selectedIndex].text;

        if (rows.length === 0) {
            UI.showSnackbar('الرجاء إضافة مجموعة واحدة على الأقل للاستمرار', 'error');
            return;
        }

        let isValid = true;
        const setsData = [];

        rows.forEach(row => {
            const weight = row.querySelector('.weight-input').value;
            const reps = row.querySelector('.reps-input').value;

            if (!weight || !reps) isValid = false;

            setsData.push({
                exercise_id: select.value,
                weight: parseFloat(weight),
                          reps: parseInt(reps, 10)
            });
        });

        if (!isValid) {
            UI.showSnackbar('الرجاء تعبئة خانات الوزن والعدات لجميع السطور المتوفرة بالجدول', 'error');
            return;
        }

        UI.setButtonLoading(buttonEl, '⏳ جاري الحفظ...', true);

        try {
            for (const setData of setsData) {
                const savedSet = await SessionManager.addSet(setData);
                // تحديث الـ State المركزي فقط دون التدخل في الـ DOM مباشرة من هنا
                state.workout.last_set = savedSet;
                state.workout.sets.push(savedSet);

                // نقوم بزيادة الـ volume في الـ State تحسباً لعدم استدعاء السيرفر مجدداً الآن
                state.workout.total_volume += (setData.weight * setData.reps);
            }

            UI.showSnackbar(`🔒 تم قفل وحفظ جهاز: ${exerciseName}`);
            select.value = '';
            document.getElementById('dynamic-sets-section').style.display = 'none';

            // استدعاء إعادة الرسم الكامل والـ Single Source of Truth للصفحة بناءً على مقترحك العبقري
            UI.renderWorkoutPage();

        } catch (e) {
            UI.showSnackbar('خطأ أثناء عملية الحفظ والاتصال: ' + e.message, 'error');
        } finally {
            UI.setButtonLoading(buttonEl, '🔒 حفظ وقفل الجهاز', false);
        }
    }
};

// 5️⃣ UI LAYER (المسؤول الحصري المباشر عن العرض وقراءة البيانات من الـ State فقط)
const UI = {
    renderHome() {
        const mainBtn = document.getElementById('main-workout-btn');
        const abandonBtn = document.getElementById('abandon-shortcut-btn');
        const sectionTitle = document.getElementById('workout-section-title');

        if (state.workout && state.workout.session) {
            if (sectionTitle) sectionTitle.textContent = '⚡ الجلسة القائمة حالياً';
            if (mainBtn) {
                mainBtn.textContent = 'استمرار التمرين الحالي ⚡';
                mainBtn.style.background = '#10b981';
            }
            if (abandonBtn) abandonBtn.style.display = 'block';
        } else {
            if (sectionTitle) sectionTitle.textContent = '🚀 ابدأ تمرينًا جديدًا';
            if (mainBtn) {
                mainBtn.textContent = 'ابدأ تمرينًا';
                mainBtn.style.background = '#2563eb';
            }
            if (abandonBtn) abandonBtn.style.display = 'none';
        }
    },

    renderWorkoutPage() {
        if (!state.workout || !state.workout.session) return;

        this.startTimerDOM(new Date(state.workout.session.started_at));

        const titleEl = document.getElementById('session-title');
        if (titleEl) {
            titleEl.textContent = `جلسة • ${this.formatTime(state.workout.session.started_at)}`;
        }

        // الحجم الكلي يُقرأ مباشرة من الحالة المركزية المستقرة المستمدة من السيرفر
        const volumeEl = document.getElementById('total-volume');
        if (volumeEl) {
            volumeEl.textContent = this.formatVolume(state.workout.total_volume);
        }

        const list = document.getElementById('sets-list');
        if (!list) return;

        list.innerHTML = ''; // تصفير كامل لإعادة الرسم الموحد والنظيف

        if (state.workout.sets && state.workout.sets.length > 0) {
            // استخدام appendChild لإظهار المجموعات بترتيبها الطبيعي المنسق من السيرفر دون عكس منطقي
            state.workout.sets.forEach(set => {
                const row = document.createElement('div');
                row.className = 'set-row';
                row.innerHTML = `
                <div class="set-main">
                <span class="set-badge">${set.exercise_name}</span>
                <span class="set-info">${set.weight} كجم × ${set.reps} عدات</span>
                </div>
                `;
                list.appendChild(row);
            });
        } else {
            list.innerHTML = '<p class="text-muted">لا توجد مجموعات محفوظة في هذه الجلسة بعد</p>';
        }
    },

    // حل مشكلة 1: دالة تحميل ديناميكية تستقبل الزر المحدد بدقة لتغيير حالته وقفله وحمايته
    setButtonLoading(buttonEl, text, isLoading) {
        if (!buttonEl) return;
        buttonEl.disabled = isLoading;
        buttonEl.textContent = text;
    },

    startTimerDOM(startTime) {
        if (timerInterval) clearInterval(timerInterval);
        const timerEl = document.getElementById('session-timer');
        if (!timerEl) return;

        timerInterval = setInterval(() => {
            const now = new Date();
            const diff = Math.floor((now - startTime) / 1000);

            const hrs = Math.floor(diff / 3600);
            const mins = Math.floor((diff % 3600) / 60);
            const secs = diff % 60;

            let display = '';
            if (hrs > 0) display += `${hrs.toString().padStart(2, '0')}:`;
            display += `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;

            timerEl.textContent = display;
        }, 1000);
    },

    stopTimerDOM() {
        if (timerInterval) {
            clearInterval(timerInterval);
            timerInterval = null;
        }
    },

    showSnackbar(message, type = 'success') {
        const snackbar = document.getElementById('snackbar');
        if (!snackbar) return;
        snackbar.textContent = message;
        snackbar.className = `snackbar ${type} show`;
        setTimeout(() => { snackbar.className = 'snackbar'; }, 3000);
    },

    formatVolume(val) { return `${Number(val).toLocaleString()} كجم`; },
        formatTime(isoStr) {
            return new Date(isoStr).toLocaleTimeString('ar-SA', { hour: '2-digit', minute: '2-digit', hour12: true });
        }
};

// 6️⃣ ROUTER LAYER
const Router = {
    home() { if (window.location.pathname !== '/') window.location.href = '/'; },
    workout() { if (window.location.pathname !== '/workout') window.location.href = '/workout'; },
    navigate(page) {
        if (page === 'home') this.home();
        if (page === 'workout') this.workout();
    }
};
const router = Router;

// 7️⃣ INTERACTION HANDLERS (مستقبلات الأحداث المحدثة لتمرير العناصر الحالية `this`)
function handleMainButtonClick(btn) {
    if (state.workout && state.workout.session) {
        Router.workout();
    } else {
        SessionManager.start(btn);
    }
}

async function abandonActiveSession(btn) {
    await SessionManager.abandon(btn);
}

function handleExerciseChange() { ExerciseManager.handleChange(); }
function addNewSetRow() { ExerciseManager.addNewRow(); }
function saveWholeExercise(btn) { ExerciseManager.saveWholeExercise(btn); }
function finishWorkout(btn) { SessionManager.finish(btn); }

// 8️⃣ BOOTSTRAP (نقطة الدخول والتحميل المركزية الصلبة)
document.addEventListener('DOMContentLoaded', async () => {
    const path = window.location.pathname;

    if (path === '/workout') {
        await ExerciseManager.loadExercises();
        const sessionData = await SessionManager.restore();

        if (sessionData) {
            UI.renderWorkoutPage();
        } else {
            UI.showSnackbar('لا توجد جلسة نشطة قائمة حالياً بالسيرفر، تحويل للرئيسية...', 'error');
            setTimeout(() => Router.home(), 1000);
        }
    } else {
        UI.stopTimerDOM();
        await SessionManager.restore();
        UI.renderHome();
    }
});
