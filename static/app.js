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
    async post(path, body) { return this.request(path, { method: 'POST', body: JSON.stringify(body) }); },
    async delete(path) { return this.request(path, { method: 'DELETE' }); }
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
                state.workout.last_set = savedSet;
                state.workout.sets.push(savedSet);
                state.workout.total_volume += (setData.weight * setData.reps);
            }

            UI.showSnackbar(`🔒 تم قفل وحفظ جهاز: ${exerciseName}`);
            select.value = '';
            document.getElementById('dynamic-sets-section').style.display = 'none';

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
                <span class="set-info">${set.weight} كجم × ${set.reps} عدات</span>
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
// 🆕 6️⃣ HISTORY VIEWER (تمت إضافته لعرض تفاصيل الجلسات السابقة)
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
                groups[name].push({ weight: set.weight, reps: set.reps });
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

// ⚠️ تم تعديل هذه الدالة (أضفنا onclick + مدة التمرين)
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
            // ✨ جعل البطاقة قابلة للضغط
            row.onclick = () => History.open(session.id);

            // حساب المدة إذا كانت منتهية
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
        await loadHistory();
    }
});
