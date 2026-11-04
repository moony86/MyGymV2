import json
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
from src.infrastructure.db.models import PlanOptionsTable,ExerciseTable,PlanScheduleTable

LOCAL=ZoneInfo('Asia/Riyadh')

def get_options(db,plan):
    row=db.get(PlanOptionsTable,plan.id)
    if row:return json.loads(row.payload)
    schedules=[]
    for s in db.query(PlanScheduleTable).filter_by(plan_id=plan.id).all():
        if s.schedule_type=='weekly' and s.days_mask is not None:
            schedules.append(dict(schedule_type='weekly',days_of_week=[d for d in range(7) if s.days_mask & (1<<((d+1)%7))]))
        elif s.schedule_type=='interval' and s.interval_days:
            schedules.append(dict(schedule_type='interval',workout_days=1,rest_days=max(0,s.interval_days-1)))
    return dict(alternatives={},schedules=schedules)

def save_options(db,plan,exercises,schedules):
    options=get_options(db,plan)
    options.pop("generation",None)
    alternatives={}
    for ex in exercises:
        alternate=ex.alternative_exercise_id
        if not alternate:continue
        if alternate==ex.exercise_id:raise ValueError('Alternative must differ from the main exercise')
        row=db.query(ExerciseTable).filter_by(id=alternate,is_active=True).first()
        if not row:raise ValueError('Alternative exercise not found or inactive')
        alternatives[ex.exercise_id]=alternate
    options['alternatives']=alternatives
    if schedules is not None:
        values=[]
        for item in schedules:
            kind=item.schedule_type
            if kind=='weekly':
                days=sorted(set(item.days_of_week))
                if not days:raise ValueError('Select at least one weekday')
                values.append(dict(schedule_type=kind,days_of_week=days))
            elif kind=='interval':values.append(dict(schedule_type=kind,workout_days=item.workout_days,rest_days=item.rest_days))
            elif kind!='manual':raise ValueError('Unsupported schedule type')
        options['schedules']=values
    row=db.get(PlanOptionsTable,plan.id)
    if row is None:row=PlanOptionsTable(plan_id=plan.id,payload='{}');db.add(row)
    row.payload=json.dumps(options)
    db.flush()

def scheduled_today(db,plan,target_date):
    for item in get_options(db,plan)['schedules']:
        if item['schedule_type']=='weekly' and target_date.weekday() in item['days_of_week']:return True
        if item['schedule_type']=='interval':
            created=plan.created_at
            if created.tzinfo is None:created=created.replace(tzinfo=timezone.utc)
            elapsed=(target_date-created.astimezone(LOCAL).date()).days
            period=item['workout_days']+item['rest_days']
            if elapsed>=0 and elapsed%period<item['workout_days']:return True
    return False
