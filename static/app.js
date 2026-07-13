const API_BASE = '/api';

const state = {
    currentPage: 'home',
    activeSessionId: null,
    exercises: [],
    lastSet: null,
    timerInterval: null,
    sessionStartTime: null
};

const router = {
    navigate(page, params = {}) {
        state.currentPage = page;
        
        if (page === 'home') {
            window.location.href = '/';
        } else if (page === 'workout') {
            const sessionId = params.session_id || state.activeSessionId;
            if (sessionId) {
                window.location.href = `/workout?session_id=${sessionId}`;
            } else {
                showSnackbar('لا توجد جلسة نشطة', 'error');
                this.navigate('home');
            }
        }
    }
};

async function api(path, options = {}) {
    const url = `${API_BASE}${path}`;
    const res = await fetch(url, {
        headers: {
            'Content-Type': 'application/json',
            ...options.headers
        },
        ...options
    });
    
    if (!res.ok) {
        const error = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(error.detail || res.statusText);
    }
    
    return res.json();
}

function showSnackbar(message, type = 'success') {
    const snackbar = document.getElementById('snackbar');
    snackbar.textContent = message;
    snackbar.className = `snackbar ${type} show`;
    setTimeout(() => {
        snackbar.className = 'snackbar';
    }, 2500);
}

function formatVolume(kg) {
    return `${Number(kg).toFixed(1)} كجم`;
}

function formatTime(dateStr) {
    const date = new Date(dateStr);
    return date.toLocaleString('ar-EG', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

async function loadExercises() {
    try {
        state.exercises = await api('/exercises');
        const select = document.getElementById('exercise-select');
        if (select) {
            select.innerHTML = '<option value="">اختر تمرين...</option>' +
                state.exercises.map(ex => `<option value="${ex.id}">${ex.name}</option>`).join('');
        }
    } catch (e) {
        console.error('Failed to load exercises:', e);
        showSnackbar('خطأ في تحميل التمارين', 'error');
    }
}

async function checkActiveSession() {
    try {
        const data = await api('/workouts/active');
        if (data.session) {
            state.activeSessionId = data.session.id;
            state.lastSet = data.last_set;
            updateActiveSection(data);
        } else {
            state.activeSessionId = null;
            state.lastSet = null;
        }
    } catch (e) {
        console.error('Failed to check active session:', e);
    }
}

function updateActiveSection(data) {
    const section = document.getElementById('active-section');
    const timeEl = document.getElementById('active-time');
    
    if (section && data.session) {
        section.style.display = 'block';
        if (timeEl) {
            timeEl.textContent = `بدأت: ${formatTime(data.session.started_at)}`;
        }
    }
}

async function startWorkout() {
    try {
        const data = await api('/workouts/start', {
            method: 'POST',
            body: JSON.stringify({ notes: '' })
        });
        
        state.activeSessionId = data.id;
        state.sessionStartTime = new Date(data.started_at);
        startTimer();
        
        showSnackbar('تم بدء التمرين!');
        router.navigate('workout', { session_id: data.id });
    } catch (e) {
        showSnackbar('خطأ: ' + e.message, 'error');
    }
}

async function addSet() {
    const exerciseSelect = document.getElementById('exercise-select');
    const weightInput = document.getElementById('weight-input');
    const repsInput = document.getElementById('reps-input');
    
    const exerciseId = exerciseSelect.value;
    const weight = weightInput.value;
    const reps = repsInput.value;
    
    if (!exerciseId) {
        showSnackbar('اختر تمرينًا', 'error');
        return;
    }
    if (!weight || !reps) {
        showSnackbar('أدخل الوزن والعدات', 'error');
        return;
    }
    
    try {
        const data = await api(`/workouts/${state.activeSessionId}/sets`, {
            method: 'POST',
            body: JSON.stringify({
                exercise_id: exerciseId,
                weight: parseFloat(weight),
                reps: parseInt(reps, 10)
            })
        });
        
        state.lastSet = data;
        renderSet(data);
        updateVolume(data);
        
        weightInput.value = '';
        repsInput.value = '';
        weightInput.focus();
        
        showSnackbar('✓ تم حفظ المجموعة');
    } catch (e) {
        showSnackbar('خطأ: ' + e.message, 'error');
    }
}

function repeatLastSet() {
    if (!state.lastSet) {
        showSnackbar('لا توجد مجموعة سابقة', 'error');
        return;
    }
    
    const weightInput = document.getElementById('weight-input');
    const repsInput = document.getElementById('reps-input');
    
    weightInput.value = state.lastSet.weight;
    repsInput.value = state.lastSet.reps;
    weightInput.focus();
    
    showSnackbar('تم ملء آخر مجموعة');
}

function renderSet(setData) {
    const list = document.getElementById('sets-list');
    const emptyMsg = list.querySelector('.text-muted');
    if (emptyMsg) {
        emptyMsg.remove();
    }
    
    const row = document.createElement('div');
    row.className = 'set-row';
    row.innerHTML = `
        <span class="set-info">${setData.exercise_name || 'تمرين'}</span>
        <span class="set-badge">${setData.weight} كجم × ${setData.reps}</span>
    `;
    list.insertBefore(row, list.firstChild);
}

function updateVolume(setData) {
    const volumeEl = document.getElementById('total-volume');
    if (!volumeEl) return;
    
    const currentVolume = parseFloat(volumeEl.textContent) || 0;
    const newVolume = currentVolume + (parseFloat(setData.weight) * parseInt(setData.reps));
    volumeEl.textContent = formatVolume(newVolume);
}

async function finishWorkout() {
    if (!confirm('إنهاء التمرين وتسجيله؟')) return;
    
    try {
        await api(`/workouts/${state.activeSessionId}/finish`, {
            method: 'POST'
        });
        
        stopTimer();
        state.activeSessionId = null;
        state.lastSet = null;
        
        showSnackbar('تم تسجيل التمرين بنجاح!');
        router.navigate('home');
    } catch (e) {
        showSnackbar('خطأ: ' + e.message, 'error');
    }
}

async function abandonActiveSession() {
    if (!confirm('إنهاء الجلسة بدون تسجيل؟')) return;
    
    try {
        await api(`/workouts/${state.activeSessionId}/abandon`, {
            method: 'POST'
        });
        
        state.activeSessionId = null;
        state.lastSet = null;
        updateActiveSection({ session: null });
        showSnackbar('تم إنهاء الجلسة');
    } catch (e) {
        showSnackbar('خطأ: ' + e.message, 'error');
    }
}

function startTimer() {
    state.sessionStartTime = new Date();
    updateTimer();
    state.timerInterval = setInterval(updateTimer, 1000);
}

function stopTimer() {
    if (state.timerInterval) {
        clearInterval(state.timerInterval);
        state.timerInterval = null;
    }
}

function updateTimer() {
    const timerEl = document.getElementById('session-timer');
    if (!timerEl || !state.sessionStartTime) return;
    
    const diff = Math.floor((Date.now() - state.sessionStartTime.getTime()) / 1000);
    const mins = Math.floor(diff / 60);
    const secs = diff % 60;
    timerEl.textContent = `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

async function loadWorkoutPage() {
    const params = new URLSearchParams(window.location.search);
    const sessionId = params.get('session_id');
    
    if (!sessionId) {
        router.navigate('home');
        return;
    }
    
    state.activeSessionId = sessionId;
    
    try {
        const data = await api(`/workouts/${sessionId}`);
        
        if (data.session) {
            state.sessionStartTime = new Date(data.session.started_at);
            startTimer();
            document.getElementById('session-title').textContent = 
                `جلسة • ${formatTime(data.session.started_at)}`;
        }
        
        if (data.last_set) {
            state.lastSet = data.last_set;
        }
        
        data.sets.forEach(set => renderSet(set));
        
        const volumeEl = document.getElementById('total-volume');
        if (volumeEl && data.total_volume) {
            volumeEl.textContent = formatVolume(data.total_volume);
        }
    } catch (e) {
        showSnackbar('خطأ في تحميل الجلسة', 'error');
        router.navigate('home');
    }
}

async function loadHomePage() {
    stopTimer();
    await checkActiveSession();
}

document.addEventListener('DOMContentLoaded', () => {
    const path = window.location.pathname;
    
    if (path === '/workout') {
        loadExercises().then(() => loadWorkoutPage());
    } else {
        loadExercises().then(() => loadHomePage());
    }
});
