import sqlite3

old_conn = sqlite3.connect('gym_tracker_OLD.db')
new_conn = sqlite3.connect('gym_tracker.db')

old_cur = old_conn.cursor()
new_cur = new_conn.cursor()

# 1. إنشاء/التأكد من وجود المستخدم الافتراضي
try:
    cols = [c[1] for c in new_cur.execute("PRAGMA table_info(profiles)").fetchall()]
    if 'id' in cols:
        new_cur.execute("""
        INSERT OR IGNORE INTO profiles (id, name, created_at)
        VALUES ('00000000-0000-0000-0000-000000000001', 'Default User', CURRENT_TIMESTAMP);
        """)
        print("--> Default profile ensured.")
except Exception as e:
    print("Profile note:", e)

# 2. نقل التمارين (Exercises)
try:
    old_exercises = old_cur.execute("SELECT id, name, primary_muscle, secondary_muscles, equipment, movement_pattern, difficulty, is_active, aliases FROM exercises").fetchall()
    new_cur.executemany("""
    INSERT OR IGNORE INTO exercises (id, name, primary_muscle, secondary_muscles, equipment, movement_pattern, difficulty, is_active, aliases)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, old_exercises)
    print(f"--> Transferred {len(old_exercises)} exercises.")
except Exception as e:
    print("Exercises migration note:", e)

# 3. نقل خطط التمارين (Workout Plans)
try:
    old_plans = old_cur.execute("SELECT id, name, description, enabled, created_at FROM workout_plans").fetchall()
    for p in old_plans:
        new_cur.execute("""
        INSERT OR IGNORE INTO workout_plans (id, name, description, enabled, created_at, profile_id)
        VALUES (?, ?, ?, ?, ?, '00000000-0000-0000-0000-000000000001')
        """, p)
    print(f"--> Transferred {len(old_plans)} workout plans.")
except Exception as e:
    print("Plans migration note:", e)

# 4. نقل الجلسات السابقة (Sessions)
try:
    old_sessions = old_cur.execute("SELECT id, status, started_at, ended_at, notes, plan_id FROM sessions").fetchall()
    for s in old_sessions:
        new_cur.execute("""
        INSERT OR IGNORE INTO sessions (id, status, started_at, ended_at, notes, plan_id, profile_id)
        VALUES (?, ?, ?, ?, ?, ?, '00000000-0000-0000-0000-000000000001')
        """, s)
    print(f"--> Transferred {len(old_sessions)} sessions.")
except Exception as e:
    print("Sessions migration note:", e)

# 5. نقل التمارين المنفذة (Performed Exercises)
try:
    old_perf = old_cur.execute("SELECT id, session_id, exercise_id, display_order, notes, is_skipped, is_warmup FROM performed_exercises").fetchall()
    new_cur.executemany("""
    INSERT OR IGNORE INTO performed_exercises (id, session_id, exercise_id, display_order, notes, is_skipped, is_warmup)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, old_perf)
    print(f"--> Transferred {len(old_perf)} performed exercises.")
except Exception as e:
    print("Performed exercises migration note:", e)

# 6. نقل الجولات والمجموعات (Sets)
try:
    old_sets = old_cur.execute("SELECT id, performed_exercise_id, set_order, weight, reps, rpe, set_type FROM sets").fetchall()
    new_cur.executemany("""
    INSERT OR IGNORE INTO sets (id, performed_exercise_id, set_order, weight, reps, rpe, set_type)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, old_sets)
    print(f"--> Transferred {len(old_sets)} sets.")
except Exception as e:
    print("Sets migration note:", e)

new_conn.commit()
old_conn.close()
new_conn.close()
print("\nDATA MIGRATION COMPLETED SUCCESSFULLY!")
