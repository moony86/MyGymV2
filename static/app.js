/**
 * =========================================================================
 * 🏋️ MYGYM CORE APP - ARCHITECTURE V2.4 (MONOLITHIC PRODUCTION)
 * =========================================================================
 * V2.3: إضافة دعم استئناف الجلسة المخططة بعد تحديث الصفحة / إغلاق التطبيق
 * دون فقدان تقدم المستخدم (لا يُعاد إنشاء جلسة جديدة إذا وُجدت جلسة نشطة).
 * V2.4: مصدر الحقيقة للتمارين الإضافية أصبح GET /workouts/{id}/exercises
 * (السيرفر)، بدل اشتقاقها محليًا من state.workout.sets.
 */

// 1️⃣ STATE (مستودع البيانات المركزي النظيف والمدمج)
const state = {
    workout: null,     // كائن الجلسة الموحد القادم من السيرفر ActiveSessionDTO { session, sets, last_set, total_volume }
    exercises: []      // مكتبة التمارين الكاملة المحملة من الباكيند
};

let timerInterval = null;

function createOperationId() {
    if (window.crypto && window.crypto.randomUUID) {
        return window.crypto.randomUUID();
    }
    return `op-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

// 2️⃣ API LAYER (الطبقة الوحيدة المسؤولة عن الـ fetch والاتصال بالشبكة)
const API = {
    BASE_URL: '/api',

    async request(path, options = {}) {
        const url = `${this.BASE_URL}${path}`;
        const config = {
            headers: {
                'Content-Type': 'application/json',
                ...(localStorage.getItem('mygym_profile_id')
                    ? { 'X-Profile-Id': localStorage.getItem('mygym_profile_id') }
                    : {}),
                ...options.headers,
            },
            ...options
        };

        let res;
        try {
            res = await fetch(url, config);
        } catch (error) {
            if (options.queueWhenOffline) {
                OfflineQueue.enqueue({ path, options });
                return { queued: true };
            }
            throw error;
        }
        if (!res.ok) {
            const error = await res.json().catch(() => ({ detail: res.statusText }));
            throw new Error(error.detail || res.statusText);
        }
        return res.json();
    },

    async get(path) { return this.request(path, { method: 'GET' }); },
    async post(path, body, queueWhenOffline = false) {
        return this.request(path, {
            method: 'POST',
            body: JSON.stringify(body),
            queueWhenOffline,
        });
    },
    async delete(path) { return this.request(path, { method: 'DELETE' }); }
};

const OfflineQueue = {
    STORAGE_KEY: 'mygym_offline_queue_v1',

    _read() {
        try {
            return JSON.parse(localStorage.getItem(this.STORAGE_KEY) || '[]');
        } catch (e) {
            return [];
        }
    },

    enqueue(request) {
        const queue = this._read();
        const options = { ...request.options, queueWhenOffline: false };
        queue.push({ path: request.path, options });
        localStorage.setItem(this.STORAGE_KEY, JSON.stringify(queue));
        UI.showSnackbar('تم الحفظ محلياً، ستتم المزامنة عند عودة الاتصال', 'info');
    },

    async flush() {
        const queue = this._read();
        if (!queue.length) return;

        const remaining = [];
        for (const request of queue) {
            try {
                await API.request(request.path, request.options);
            } catch (e) {
                remaining.push(request);
                break;
            }
        }

        localStorage.setItem(this.STORAGE_KEY, JSON.stringify(remaining));
        if (queue.length !== remaining.length) {
            UI.showSnackbar('تمت مزامنة البيانات المحفوظة محلياً', 'success');
            await SessionManager.restore();
            UI.renderWorkoutPage();
        }
    },
};

window.addEventListener('online', () => OfflineQueue.flush());
window.addEventListener('load', () => OfflineQueue.flush());

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
        return await API.post(`/workouts/${state.workout.session.id}/sets`, setData, true);
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
    _draftInputHandler: null,   // مرجع لمستمع الحفظ التلقائي (لمنع التراكم)

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

        // لو فيه مسودة محفوظة محليًا لنفس التمرين بهذه الجلسة، نستعيدها
        // بدل ما نبدأ بجدول فاضي (حماية من فقدان قيم كُتبت قبل انقطاع/إغلاق).
        const draftRows = ExerciseDraft.restore(select.value);
        if (draftRows && draftRows.length > 0) {
            draftRows.forEach(r => this.addNewRow(r.weight, r.reps, r.operation_id, r.rpe, r.rir));
            UI.showSnackbar('↩️ تم استرجاع قيم لم تُحفظ من قبل', 'info');
        } else {
            for (let i = 1; i <= 3; i++) { this.addNewRow(); }
        }

        this.attachDraftAutosave();
    },

    // يربط أي تغيير بأي خانة وزن/عدات بحفظ فوري بالـ localStorage
    attachDraftAutosave() {
        const tbody = document.getElementById('dynamic-sets-body');
        const select = document.getElementById('exercise-select');
        if (!tbody || !select.value) return;

        // إزالة المستمع السابق إن وُجد (يمنع تراكم الـ listeners)
        if (this._draftInputHandler) {
            tbody.removeEventListener('input', this._draftInputHandler);
        }

        // إنشاء مستمع جديد وحفظ مرجعه
        this._draftInputHandler = () => {
            const rows = Array.from(tbody.querySelectorAll('tr')).map(row => ({
                weight: row.querySelector('.weight-input').value,
                reps: row.querySelector('.reps-input').value,
                operation_id: row.dataset.operationId,
                rpe: row.querySelector('.rpe-input').value,
                rir: row.querySelector('.rir-input').value,
            }));
            ExerciseDraft.save(select.value, rows);
        };

        tbody.addEventListener('input', this._draftInputHandler);
    },

    addNewRow(initialWeight = null, initialReps = null, operationId = null, initialRpe = null, initialRir = null) {
        const tbody = document.getElementById('dynamic-sets-body');
        const rowCount = tbody.rows.length + 1;

        let defaultWeight = initialWeight !== null ? initialWeight : '';
        let defaultReps = initialReps !== null ? initialReps : '';
        const rows = Array.from(tbody.rows);

        if (initialWeight === null && initialReps === null) {
            for (let i = rows.length - 1; i >= 0; i--) {
                const wVal = rows[i].querySelector('.weight-input').value;
                const rVal = rows[i].querySelector('.reps-input').value;
                if (wVal || rVal) {
                    defaultWeight = wVal;
                    defaultReps = rVal;
                    break;
                }
            }
        }

        const tr = document.createElement('tr');
        tr.className = 'set-table-row';
        tr.dataset.operationId = operationId || createOperationId();
        tr.innerHTML = `
        <td class="set-number-cell">${rowCount}</td>
        <td><input type="number" class="table-input weight-input" step="0.1" inputmode="decimal" value="${defaultWeight}" placeholder="0"></td>
        <td><input type="number" class="table-input reps-input" inputmode="numeric" value="${defaultReps}" placeholder="0"></td>
        <td><input type="number" class="table-input rpe-input" min="1" max="10" step="0.5" value="${initialRpe ?? ''}" placeholder="RPE"></td>
        <td><input type="number" class="table-input rir-input" min="0" max="10" step="1" value="${initialRir ?? ''}" placeholder="RIR"></td>
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

        // حفظ القيمة قبل التصفير لتجنب الشرط الفارغ
        const completedExerciseId = select.value;

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
                exercise_id: completedExerciseId,
                weight: parseFloat(weight),
                reps: parseInt(reps, 10),
                client_operation_id: row.dataset.operationId,
                rpe: row.querySelector('.rpe-input').value ? parseFloat(row.querySelector('.rpe-input').value) : null,
                rir: row.querySelector('.rir-input').value ? parseInt(row.querySelector('.rir-input').value, 10) : null,
            });
        });

        if (!isValid) {
            UI.showSnackbar('الرجاء تعبئة خانات الوزن والعدات لجميع السطور المتوفرة بالجدول', 'error');
            return;
        }

        UI.setButtonLoading(buttonEl, '⏳ جاري الحفظ...', true);

        // نبدأ من حيث توقفنا لو كانت هذه محاولة إعادة إرسال بعد فشل جزئي،
        // بدل إعادة إرسال المجموعات اللي نجحت أصلاً (تكرار).
        const alreadySavedCount = ExerciseDraft.getSavedCount(completedExerciseId);
        const remaining = setsData.slice(alreadySavedCount);

        let queuedAny = false;
        try {
            for (const setData of remaining) {
                const savedSet = await SessionManager.addSet(setData);
                if (savedSet && savedSet.queued) {
                    queuedAny = true;
                    UI.showSnackbar('تم حفظ المجموعة محلياً بانتظار الاتصال', 'info');
                    break;
                }
                state.workout.last_set = savedSet;
                state.workout.sets.push(savedSet);
                state.workout.total_volume += (setData.weight * setData.reps);
                ExerciseDraft.markSetSaved(completedExerciseId);
            }

            if (queuedAny) {
                return;
            }

            // تنظيف المسودة قبل تصفير select.value (لضمان استخدام المفتاح الصحيح)
            ExerciseDraft.clear(completedExerciseId);

            UI.showSnackbar(`🔒 تم قفل وحفظ جهاز: ${exerciseName}`);
            select.value = '';
            document.getElementById('dynamic-sets-section').style.display = 'none';

            // إدارة الرسم: مرة واحدة فقط
            const isPlannedExercise = (
                typeof PlannedSession !== 'undefined' &&
                PlannedSession.isActive &&
                completedExerciseId === PlannedSession.currentExerciseId
            );

            if (isPlannedExercise) {
                await PlannedSession.completeCurrentExercise(); // تستدعي renderUI وبالتالي UI.renderWorkoutPage
            } else {
                UI.renderWorkoutPage(); // تحديث قائمة المجموعات للتمارين الإضافية/الحرة
            }

        } catch (e) {
            // لا نمسح الـ Draft هنا: المجموعات اللي نجحت محفوظة (markSetSaved)،
            // والباقي لسه بالجدول. إعادة الضغط على الزر ترسل الباقي فقط.
            UI.showSnackbar('خطأ أثناء عملية الحفظ والاتصال، جرّب اضغط "حفظ" مرة ثانية لاحقًا', 'error');
        } finally {
            UI.setButtonLoading(buttonEl, '🔒 حفظ وقفل الجهاز', false);
        }
    }
};

// =========================================================================
// ExerciseDraft: حفظ محلي بسيط لما يكتبه المستخدم بالجدول الحالي،
// حتى لا يضيع عند إغلاق التطبيق أو تحديث الصفحة أو انقطاع النت.
// السيرفر يبقى دائمًا مصدر الحقيقة للمجموعات المحفوظة فعليًا؛ هذا فقط
// يحمي "المسودة" (القيم المكتوبة ولم تُرسل بعد) + عدّاد ما أُرسل فعليًا
// لمنع الإرسال المكرر عند إعادة المحاولة بعد فشل جزئي.
// =========================================================================
const ExerciseDraft = {
    _key(exerciseId) {
        const sessionId = state.workout && state.workout.session ? state.workout.session.id : 'no-session';
        return `mygym_draft_${sessionId}_${exerciseId}`;
    },

    save(exerciseId, rowsData) {
        try {
            const existing = this._read(exerciseId);
            localStorage.setItem(this._key(exerciseId), JSON.stringify({
                rows: rowsData,
                savedCount: existing ? existing.savedCount : 0,
            }));
        } catch (e) {
            console.warn('ExerciseDraft.save failed:', e);
        }
    },

    _read(exerciseId) {
        try {
            const raw = localStorage.getItem(this._key(exerciseId));
            return raw ? JSON.parse(raw) : null;
        } catch (e) {
            return null;
        }
    },

    restore(exerciseId) {
        const data = this._read(exerciseId);
        return data ? data.rows : null;
    },

    getSavedCount(exerciseId) {
        const data = this._read(exerciseId);
        return data ? data.savedCount : 0;
    },

    markSetSaved(exerciseId) {
        const data = this._read(exerciseId) || { rows: [], savedCount: 0 };
        data.savedCount += 1;
        try {
            localStorage.setItem(this._key(exerciseId), JSON.stringify(data));
        } catch (e) {
            console.warn('ExerciseDraft.markSetSaved failed:', e);
        }
    },

    clear(exerciseId) {
        try {
            localStorage.removeItem(this._key(exerciseId));
        } catch (e) {
            // تجاهل
        }
    },
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

        const volumeEl = document.getElementById('total-volume');
        if (volumeEl) {
            volumeEl.textContent = this.formatVolume(state.workout.total_volume);
        }

        const list = document.getElementById('sets-list');
        if (!list) return;

        list.innerHTML = '';

        if (state.workout.sets && state.workout.sets.length > 0) {
            state.workout.sets.forEach(set => {
                const row = document.createElement('div');
                row.className = 'set-row';
                row.innerHTML = `
                <div class="set-main">
                <span class="set-badge">${set.exercise_name}</span>
                <span class="set-info">${set.weight} كجم × ${set.reps} عدات${set.rpe != null ? ` · RPE ${set.rpe}` : ''}${set.rir != null ? ` · RIR ${set.rir}` : ''}</span>
                </div>
                `;
                list.appendChild(row);
            });
        } else {
            list.innerHTML = '<p class="text-muted">لا توجد مجموعات محفوظة في هذه الجلسة بعد</p>';
        }
    },

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

// =================================================================
// HISTORY VIEWER (لعرض تفاصيل الجلسات السابقة)
// =================================================================
const History = {
    currentSessionId: null,  // لتخزين معرف الجلسة المعروضة

    async open(sessionId) {
        this.currentSessionId = sessionId;  // حفظ المعرف
        try {
            const data = await API.get(`/workouts/${sessionId}`);
            this.renderModal(data);
        } catch (e) {
            UI.showSnackbar('فشل تحميل تفاصيل الجلسة', 'error');
            console.error(e);
        }
    },

    renderModal(data) {
        const { session, sets, total_volume } = data;

        const titleEl = document.getElementById('modal-session-title');
        const dateEl = document.getElementById('modal-session-date');
        const durationEl = document.getElementById('modal-session-duration');
        const volumeEl = document.getElementById('modal-session-volume');

        if (titleEl) {
            const dateObj = new Date(session.started_at);
            const dayName = dateObj.toLocaleDateString('ar-SA', { weekday: 'long' });
            titleEl.textContent = `جلسة ${dayName}`;
        }

        if (dateEl) {
            const d = new Date(session.started_at);
            dateEl.textContent = d.toLocaleDateString('ar-SA', {
                year: 'numeric',
                month: 'long',
                day: 'numeric'
            });
        }

        if (durationEl) {
            if (session.ended_at) {
                const start = new Date(session.started_at);
                const end = new Date(session.ended_at);
                const diffSec = Math.floor((end - start) / 1000);
                const hrs = Math.floor(diffSec / 3600);
                const mins = Math.floor((diffSec % 3600) / 60);
                let text = '';
                if (hrs > 0) text += `${hrs} ساعة `;
                text += `${mins} دقيقة`;
                durationEl.textContent = `⏱️ ${text}`;
            } else {
                durationEl.textContent = '⏱️ غير معروف';
            }
        }

        if (volumeEl) {
            volumeEl.textContent = `🏋️ ${total_volume || 0} كجم`;
        }

        // تجميع المجموعات حسب اسم التمرين
        const groups = {};
        if (sets && sets.length) {
            sets.forEach(set => {
                const name = set.exercise_name || 'تمرين غير معروف';
                if (!groups[name]) groups[name] = [];
                groups[name].push({ weight: set.weight, reps: set.reps, rpe: set.rpe, rir: set.rir });
            });
        }

        const container = document.getElementById('modal-exercises-list');
        container.innerHTML = '';

        if (Object.keys(groups).length === 0) {
            container.innerHTML = '<p class="text-muted">لا توجد مجموعات مسجلة</p>';
        } else {
            for (const [exerciseName, setList] of Object.entries(groups)) {
                const groupDiv = document.createElement('div');
                groupDiv.className = 'modal-exercise-group';

                const nameDiv = document.createElement('div');
                nameDiv.className = 'modal-exercise-name';
                nameDiv.textContent = exerciseName;
                groupDiv.appendChild(nameDiv);

                const setsDiv = document.createElement('div');
                setsDiv.className = 'modal-exercise-sets';

                setList.forEach((set) => {
                    const item = document.createElement('div');
                    item.className = 'modal-set-item';
                    item.innerHTML = `
                    <span class="modal-set-weight">${set.weight} كجم</span>
                    <span class="modal-set-reps">× ${set.reps} عدات</span>
                    ${set.rpe != null ? `<span>RPE ${set.rpe}</span>` : ''}
                    ${set.rir != null ? `<span>RIR ${set.rir}</span>` : ''}
                    `;
                    setsDiv.appendChild(item);
                });

                groupDiv.appendChild(setsDiv);
                container.appendChild(groupDiv);
            }
        }

        document.getElementById('history-modal').style.display = 'flex';
    },

    close() {
        document.getElementById('history-modal').style.display = 'none';
    },

    async deleteCurrentSession() {
        if (!this.currentSessionId) return;
        if (!confirm('هل أنت متأكد من حذف هذه الجلسة نهائياً؟')) return;
        try {
            await API.delete(`/workouts/${this.currentSessionId}`);
            UI.showSnackbar('✅ تم حذف الجلسة بنجاح');
            this.close();
            loadHistory(); // إعادة تحميل القائمة
        } catch (e) {
            UI.showSnackbar('فشل حذف الجلسة', 'error');
            console.error(e);
        }
    }
};

// 7️⃣ ROUTER LAYER
const Router = {
    home() { if (window.location.pathname !== '/') window.location.href = '/'; },
    workout() { if (window.location.pathname !== '/workout') window.location.href = '/workout'; },
    navigate(page) {
        if (page === 'home') this.home();
        if (page === 'workout') this.workout();
    }
};
const router = Router;

// 8️⃣ INTERACTION HANDLERS (مستقبلات الأحداث المحدثة لتمرير العناصر الحالية `this`)
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

async function loadHistory() {
    const list = document.getElementById("history-list");
    if (!list) return;

    try {
        const sessions = await API.get('/workouts/history');

        if (!sessions.length) {
            list.innerHTML = `
            <div class="history-empty">
            لا توجد تمارين سابقة
            </div>
            `;
            return;
        }

        list.innerHTML = "";

        sessions.forEach(session => {
            const row = document.createElement("div");
            row.className = "history-row";
            row.onclick = () => History.open(session.id);

            let durationText = '';
            if (session.ended_at) {
                const start = new Date(session.started_at);
                const end = new Date(session.ended_at);
                const diffMin = Math.floor((end - start) / 60000);
                durationText = diffMin > 0 ? `${diffMin} دقيقة` : '< 1 دقيقة';
            }

            row.innerHTML = `
            <div class="history-date">
            ${new Date(session.started_at).toLocaleDateString("ar-SA")}
            </div>
            <div class="history-volume">
            ${session.volume_kg || 0} كجم
            </div>
            <div class="history-sets">
            ${session.sets_count || 0} مجموعات
            ${durationText ? `<span style="font-size:0.8rem; color:#6b7280; margin-right:8px;">⏱️ ${durationText}</span>` : ''}
            </div>
            `;

            list.appendChild(row);
        });

    } catch (err) {
        console.error(err);

        list.innerHTML = `
        <div class="history-empty">
        فشل تحميل السجل
        </div>
        `;
    }
}

function handleExerciseChange() { ExerciseManager.handleChange(); }
function addNewSetRow() { ExerciseManager.addNewRow(); }
function saveWholeExercise(btn) { ExerciseManager.saveWholeExercise(btn); }
function finishWorkout(btn) { SessionManager.finish(btn); }

// 9️⃣ BOOTSTRAP (نقطة الدخول والتحميل المركزية الصلبة)
document.addEventListener('DOMContentLoaded', async () => {
    const path = window.location.pathname;

    if (path === '/workout') {
        await ExerciseManager.loadExercises();
        const sessionData = await SessionManager.restore();

        const params = new URLSearchParams(window.location.search);
        const planId = params.get('plan_id');

        if (sessionData?.session) {
            if (sessionData.session.plan_id != null) {
                await PlannedSession.resume(sessionData.session.id);
            } else {
                UI.renderWorkoutPage();
            }
        } else if (planId) {
            await PlannedSession.init(planId);
        } else {
            UI.showSnackbar('لا توجد جلسة نشطة، تحويل للرئيسية...', 'error');
            setTimeout(() => Router.home(), 1000);
        }

    } else {
        UI.stopTimerDOM();
        await SessionManager.restore();
        UI.renderHome();
        await loadHistory();
    }
});

// ====== ========================= ======
// ====== PLANNED SESSION EXECUTION ======
// ====== ========================= ======

const PlannedSession = {
    sessionId: null,
    exercises: [],
    currentExerciseId: null,   // مؤشر تقدم الخطة فقط
    activeSelectionId: null,   // التمرين المعروض حاليًا (خطة أو إضافي)
    extraExercises: [],        // [{exercise_id, name, isExtra: true}] -- الآن من السيرفر فقط
    isActive: false,

    // إرجاع التمرين المحدد حاليًا (من الخطة أو الإضافي)
    getActiveExercise() {
        return this.exercises.find(e => e.exercise_id === this.activeSelectionId)
        || this.extraExercises.find(e => e.exercise_id === this.activeSelectionId);
    },

    // 🆕 V2.4: مصدر الحقيقة الوحيد -- GET /workouts/{session_id}/exercises
    // بدل الاشتقاق المحلي من state.workout.sets (كان عرضة لعدم الدقة
    // ويعتمد على مطابقة الاسم). الآن يعتمد على exercise_id فعلي من السيرفر.
    async loadExtraExercisesFromServer() {
        try {
            const allExercises = await API.get(`/workouts/${this.sessionId}/exercises`);
            this.extraExercises = allExercises
            .filter(ex => !ex.is_planned)
            .map(ex => ({
                exercise_id: ex.exercise_id,
                name: ex.exercise_name,
                isExtra: true,
            }));
        } catch (e) {
            console.warn('فشل تحميل التمارين الإضافية من السيرفر:', e);
            this.extraExercises = [];
        }
    },

    async init(planId) {
        try {
            const data = await API.post(`/planner/plans/${planId}/start`, { notes: "" });

            this.sessionId = data.session_id;
            this.exercises = data.planned_exercises.map(ex => ({
                ...ex,
                is_completed: false,
            }));

            this.currentExerciseId = this.exercises.length > 0 ? this.exercises[0].exercise_id : null;
            this.activeSelectionId = this.currentExerciseId;
            this.extraExercises = []; // خطة جديدة، لسه ما فيها تمارين إضافية

            this.isActive = true;
            await SessionManager.restore(); // تحديث state.workout بالجلسة الجديدة
            this.startCurrentExercise();    // تستدعي renderUI داخلياً
        } catch (e) {
            UI.showSnackbar('فشل بدء الخطة: ' + e.message, 'error');
        }
    },

    async resume(sessionId) {
        try {
            const data = await API.get(`/planner/sessions/${sessionId}/progress`);
            this.sessionId = data.session_id;
            this.exercises = data.planned_exercises;

            const nextPending = this.exercises.find(e => !e.is_completed);
            this.currentExerciseId = nextPending ? nextPending.exercise_id : null;
            this.activeSelectionId = this.currentExerciseId;

            this.isActive = true;

            // 🆕 من السيرفر مباشرة، مو اشتقاق محلي
            await this.loadExtraExercisesFromServer();

            if (this.currentExerciseId) {
                this.startCurrentExercise(); // تستدعي renderUI داخلياً
                UI.showSnackbar('↩️ تم استئناف جلستك المخططة', 'info');
            } else {
                this.renderUI();
                UI.showSnackbar('🎉 كفو! أكملت جميع تمارين الخطة!', 'success');
            }
        } catch (e) {
            UI.showSnackbar('فشل استئناف الخطة: ' + e.message, 'error');
        }
    },

    renderUI() {
        const plannedSection = document.getElementById('planned-section');
        const freeSection = document.getElementById('free-section');
        plannedSection.style.display = 'block';
        freeSection.style.display = 'none';

        const nameEl = document.getElementById('plan-current-exercise-name');
        const current = this.getActiveExercise();

        if (nameEl) {
            if (current) {
                if (current.isExtra) {
                    nameEl.textContent = `▶️ ${current.name} (تمرين إضافي)`;
                } else {
                    nameEl.textContent = `▶️ ${current.name} (${current.target_sets || '?'} مجموعات${current.target_reps ? ` × ${current.target_reps}` : ''})`;
                }
            } else {
                nameEl.textContent = '🎉 أكملت كل تمارين الخطة';
            }
        }

        const chipsRow = document.getElementById('plan-chips-row');
        chipsRow.innerHTML = '';

        // تمارين الخطة
        this.exercises.forEach((ex, idx) => {
            const chip = document.createElement('div');
            const isSelected = ex.exercise_id === this.activeSelectionId;
            chip.className = 'plan-chip' + (ex.is_completed ? ' is-completed' : (isSelected ? ' is-current' : ''));
            chip.textContent = ex.is_completed ? '✓' : (idx + 1);
            chip.title = ex.name;
            if (!ex.is_completed) {
                chip.onclick = () => this.startCurrentExercise(ex.exercise_id);
            }
            chipsRow.appendChild(chip);
        });

        // التمارين الإضافية
        this.extraExercises.forEach((ex, idx) => {
            const chip = document.createElement('div');
            const isSelected = ex.exercise_id === this.activeSelectionId;
            chip.className = 'plan-chip plan-chip-extra' + (isSelected ? ' is-current' : '');
            chip.textContent = this.exercises.length + idx + 1;
            chip.title = ex.name + ' (خارج الخطة)';
            chip.onclick = () => this.selectExtraExercise(ex.exercise_id);
            chipsRow.appendChild(chip);
        });

        UI.renderWorkoutPage();
    },

    // للتمارين الإضافية فقط -- يضبط الاختيار ويُحضر الجدول
    selectExtraExercise(exerciseId) {
        this.activeSelectionId = exerciseId;
        const select = document.getElementById('exercise-select');
        select.value = exerciseId;
        ExerciseManager.handleChange();
        this.renderUI();
    },

    // 🆕 V2.4: يحفظ التمرين الإضافي بالسيرفر فورًا (POST)، مو RAM فقط.
    // بهذا يبقى موجودًا حتى لو صار Refresh قبل ما تسجّل أي Set له --
    // بالضبط سيناريو "أضيفه بالنية، أتمرنه بعدين نفس اليوم".
    async addExtraExercise(exerciseId, exerciseName) {
        try {
            await API.post(`/workouts/${this.sessionId}/exercises`, { exercise_id: exerciseId });

            const alreadyAdded = this.extraExercises.some(e => e.exercise_id === exerciseId);
            if (!alreadyAdded) {
                this.extraExercises.push({
                    exercise_id: exerciseId,
                    name: exerciseName,
                    isExtra: true
                });
            }
            this.selectExtraExercise(exerciseId);
        } catch (e) {
            UI.showSnackbar('فشل إضافة التمرين: ' + e.message, 'error');
        }
    },

    // خاص بتمارين الخطة فقط (يُستخدم داخليًا ومع الأزرار الخاصة بالخطة)
    startCurrentExercise(exercise_id = null) {
        const targetId = exercise_id || this.currentExerciseId;
        if (!targetId) {
            UI.showSnackbar('لا يوجد تمرين محدد', 'error');
            return;
        }

        const ex = this.exercises.find(e => e.exercise_id === targetId);
        if (!ex) {
            UI.showSnackbar('التمرين غير موجود في الخطة', 'error');
            return;
        }

        this.currentExerciseId = targetId;
        this.activeSelectionId = targetId;

        const select = document.getElementById('exercise-select');
        select.value = targetId;
        ExerciseManager.handleChange();

        const rows = document.querySelectorAll('#dynamic-sets-body tr');
        if (ex.suggested_weight !== null && ex.suggested_weight !== undefined) {
            rows.forEach(row => {
                row.querySelector('.weight-input').value = ex.suggested_weight;
                row.querySelector('.reps-input').value = ex.suggested_reps || '';
            });
        } else {
            rows.forEach(row => {
                row.querySelector('.weight-input').value = '';
                row.querySelector('.reps-input').value = '';
            });
        }

        if (ex.target_sets) {
            const tbody = document.getElementById('dynamic-sets-body');
            const currentRows = tbody.rows.length;
            if (currentRows < ex.target_sets) {
                for (let i = currentRows; i < ex.target_sets; i++) ExerciseManager.addNewRow();
            } else if (currentRows > ex.target_sets) {
                for (let i = currentRows; i > ex.target_sets; i--) tbody.deleteRow(i - 1);
            }
            ExerciseManager.reindexRows();
        }

        UI.showSnackbar(`🏋️ ابدأ: ${ex.name}`, 'info');
        this.renderUI();
    },

    async completeCurrentExercise() {
        const currentEx = this.exercises.find(e => e.exercise_id === this.currentExerciseId);
        if (currentEx) {
            currentEx.is_completed = true;
        }
        const nextPending = this.exercises.find(e => !e.is_completed);
        if (nextPending) {
            this.currentExerciseId = nextPending.exercise_id;
            this.startCurrentExercise(this.currentExerciseId);
            UI.showSnackbar(`✅ تم الحفظ، انتقل إلى: ${nextPending.name}`);
        } else {
            this.currentExerciseId = null;
            this.activeSelectionId = null;
            this.renderUI();
            UI.showSnackbar('🎉 كفو! أكملت جميع تمارين الخطة!', 'success');
        }
    },

    cancel() {
        if (!confirm('هل تريد إلغاء الخطة والعودة للوضع الحر؟')) return;
        this.isActive = false;
        this.sessionId = null;

        this.exercises = [];
        this.extraExercises = [];

        this.currentExerciseId = null;
        this.activeSelectionId = null;

        document.getElementById('planned-section').style.display = 'none';
        document.getElementById('free-section').style.display = 'block';
        document.getElementById('session-title').textContent = 'جلسة جديدة';
        document.getElementById('exercise-select').value = '';
        document.getElementById('dynamic-sets-section').style.display = 'none';
        UI.renderWorkoutPage();
    }
};


function cancelPlannedSession() {
    PlannedSession.cancel();
}

// =========================================================================
// إضافة تمرين إضافي أثناء تنفيذ الخطة (خارج التمارين المخططة أصلًا)
// =========================================================================
function toggleExtraExercise() {
    const section = document.getElementById('extra-exercise-section');
    const isHidden = section.style.display === 'none';
    section.style.display = isHidden ? 'block' : 'none';

    if (isHidden) {
        populateExtraExerciseSelect();
    }
}

function populateExtraExerciseSelect() {
    const select = document.getElementById('extra-exercise-select');
    if (!select || select.options.length > 1) return;

    state.exercises.forEach(ex => {
        const opt = document.createElement('option');
        opt.value = ex.id;
        opt.textContent = ex.name;
        select.appendChild(opt);
    });
}

async function handleExtraExerciseChange() {
    const extraSelect = document.getElementById('extra-exercise-select');
    if (!extraSelect.value) return;

    const exerciseName = extraSelect.options[extraSelect.selectedIndex].text;
    await PlannedSession.addExtraExercise(extraSelect.value, exerciseName);

    document.getElementById('extra-exercise-section').style.display = 'none';
    extraSelect.value = '';

    const dynamicSection = document.getElementById('dynamic-sets-section');
    if (dynamicSection) {
        dynamicSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
}

// التنبيه عند انقطاع الاتصال
window.addEventListener('offline', () => {
    alert("⚠️ لقد فقدت الاتصال بالسيرفر! تأكد من تشغيل الـ VPN.");
});

// ====== Body Tracking Toggle ======
async function toggleBodyTracking() {
    const section = document.getElementById('body-tracking-dashboard');
    if (!section) return;
    const isHidden = section.style.display === 'none' || section.style.display === '';
    section.style.display = isHidden ? 'block' : 'none';
    if (isHidden) {
        await loadLatestMeasurement();
    }
}

async function loadLatestMeasurement() {
    const container = document.getElementById('latest-measurement');
    if (!container) return;
    try {
        const res = await fetch('/api/profile/measurements/latest', {
            headers: localStorage.getItem('mygym_profile_id')
                ? { 'X-Profile-Id': localStorage.getItem('mygym_profile_id') }
                : {},
        });
        if (!res.ok) throw new Error('Failed');
        const m = await res.json();
        if (!m) {
            container.innerHTML = '<p style="color: var(--text-secondary);">لا توجد قياسات بعد</p>';
            return;
        }
        container.innerHTML = `
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 4px; font-size: 0.9em;">
                ${m.weight ? `<span>⚖️ الوزن: ${m.weight} كجم</span>` : ''}
                ${m.body_fat ? `<span>📊 دهون: ${m.body_fat}%</span>` : ''}
                ${m.waist ? `<span>📏 خصر: ${m.waist} سم</span>` : ''}
                ${m.chest ? `<span>📏 صدر: ${m.chest} سم</span>` : ''}
                ${m.hips ? `<span>📏 أوراك: ${m.hips} سم</span>` : ''}
                ${m.neck ? `<span>📏 عنق: ${m.neck} سم</span>` : ''}
                ${m.left_arm ? `<span>💪 ذراع يسار: ${m.left_arm} سم</span>` : ''}
                ${m.right_arm ? `<span>💪 ذراع يمين: ${m.right_arm} سم</span>` : ''}
                ${m.left_thigh ? `<span>🦵 فخذ يسار: ${m.left_thigh} سم</span>` : ''}
                ${m.right_thigh ? `<span>🦵 فخذ يمين: ${m.right_thigh} سم</span>` : ''}
            </div>
            <p style="margin-top: 8px; font-size: 0.8em; color: var(--text-secondary);">
                ${m.date} • ${m.type === 'weekly' ? 'أسبوعي' : 'شهري'}
                ${m.goal ? ' • ' + m.goal : ''}
            </p>
        `;
    } catch (err) {
        container.innerHTML = '<p style="color: var(--text-secondary);">لا توجد قياسات بعد</p>';
    }
}
