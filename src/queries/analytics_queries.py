"""Auditable log analytics: observations do not diagnose injury or physiology."""
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from statistics import median
from zoneinfo import ZoneInfo
from sqlalchemy import select
from src.infrastructure.db.models import ExerciseTable, PerformedExerciseTable, SessionTable, SetTable
LOCAL=ZoneInfo('Asia/Riyadh')
METHOD_VERSION='2026-10-27.1'
WORK_TYPES=('working','dropset','failure','amrap')

def _now(): return datetime.now(timezone.utc)
def _time(db): return db.info.get('analytics_now') or _now()
def _aware(value):return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
def _iso(value):return _aware(value).isoformat().replace('+00:00','Z')
def _monday(value):
    value=value.astimezone(LOCAL)
    return (value-timedelta(days=value.weekday())).replace(hour=0,minute=0,second=0,microsecond=0)
def _calculate_e1rm(weight,reps):
    if weight is None or reps is None or not 1<=reps<=10 or Decimal(str(weight))<=0:return None
    weight=Decimal(str(weight))
    return float(weight if reps==1 else weight*(Decimal(1)+Decimal(reps)/Decimal(30)))
def _estimate(row):
    text=(row['name']+' '+(row['equipment'] or '')).lower()
    if any(word in text for word in ['assisted','assistance','bodyweight','band']):return None
    return _calculate_e1rm(row['weight'],row['reps'])
def _records(db,profile_id):
    cached=db.info.get('analytics_records',{}).get(profile_id)
    if cached is not None:return cached
    stmt=(select(SessionTable.id,SessionTable.started_at,ExerciseTable.id,ExerciseTable.name,ExerciseTable.primary_muscle,ExerciseTable.equipment,SetTable.id,SetTable.weight,SetTable.reps,SetTable.rpe,SetTable.rir)
        .select_from(SetTable).join(PerformedExerciseTable,SetTable.performed_exercise_id==PerformedExerciseTable.id)
        .join(SessionTable,PerformedExerciseTable.session_id==SessionTable.id).join(ExerciseTable,PerformedExerciseTable.exercise_id==ExerciseTable.id)
        .where(SessionTable.profile_id==profile_id,SessionTable.status=='COMPLETED',SetTable.set_type.in_(WORK_TYPES),PerformedExerciseTable.is_skipped.is_(False),PerformedExerciseTable.is_warmup.is_(False)).order_by(SessionTable.started_at,SetTable.id))
    rows=[];excluded=0;now=_time(db)
    for sid,date,eid,name,muscle,equipment,setid,weight,reps,rpe,rir in db.execute(stmt):
        date=_aware(date)
        if date>=now:continue
        if weight is None or not Decimal(str(weight)).is_finite() or weight<0 or reps is None or reps<=0:
            excluded+=1;continue
        rows.append(dict(session_id=sid,date=date,exercise_id=eid,name=name,muscle=(muscle or 'unmapped').strip().lower(),equipment=equipment,id=setid,weight=Decimal(str(weight)),reps=int(reps),rpe=float(rpe) if rpe is not None and 1<=rpe<=10 else None,rir=int(rir) if rir is not None and 0<=rir<=10 else None))
    return rows,excluded
def _window(db,profile_id,weeks):
    all_rows,excluded=_records(db,profile_id);now=_time(db);monday=_monday(now);start=monday-timedelta(weeks=weeks-1)
    rows=[r for r in all_rows if r['date']>=start]
    first=all_rows[0]['date'].astimezone(LOCAL).date() if all_rows else None
    complete=[]
    for offset in range(weeks):
        week=start+timedelta(weeks=offset)
        if week<monday and first is not None and first<=week.date():complete.append(week.date())
    return rows,dict(start=start,end=now,current=monday,first=first,complete=complete,excluded=excluded)
def _volume(rows):return float(sum((r['weight']*r['reps'] for r in rows),Decimal('0')))
def get_data_quality(db,profile_id,weeks=8):
    rows,meta=_window(db,profile_id,weeks);sessions=len({r['session_id'] for r in rows});dates={r['date'].astimezone(LOCAL).date() for r in rows};span=(max(dates)-min(dates)).days+1 if dates else 0
    return dict(method_version=METHOD_VERSION,timezone=str(LOCAL),period_start=meta['start'].isoformat(),period_end=meta['end'].isoformat(),current_week_partial=True,first_logged_date=str(meta['first']) if meta['first'] else None,recorded_days=len(dates),observed_span_days=span,sessions_count=sessions,total_sets=len(rows),total_reps=sum(r['reps'] for r in rows),external_load_volume_kg=round(_volume(rows),2),completed_observed_weeks=len(meta['complete']),excluded_invalid_sets_all_history=meta['excluded'],interpretation='limited' if sessions<4 or span<14 else 'descriptive')

def get_exercise_sessions(db,profile_id,exercise_id,limit=30):
    rows,_=_records(db,profile_id);groups=defaultdict(list)
    for r in rows:
        if r['exercise_id']==exercise_id:groups[r['session_id']].append(r)
    result=[]
    for sid,items in groups.items():
        estimates=[v for r in items if (v:=_estimate(r)) is not None]
        rpes=[r['rpe'] for r in items if r['rpe'] is not None];rirs=[r['rir'] for r in items if r['rir'] is not None]
        result.append(dict(session_id=sid,date=_iso(items[0]['date']),max_weight=float(max(r['weight'] for r in items)),e1rm=round(max(estimates),2) if estimates else None,volume=round(_volume(items),2),sets_count=len(items),avg_rpe=round(sum(rpes)/len(rpes),2) if rpes else None,avg_rir=round(sum(rirs)/len(rirs),2) if rirs else None,sets=[{k:float(r[k]) if k=='weight' else r[k] for k in ['weight','reps','rpe','rir']} for r in items]))
    return sorted(result,key=lambda r:r['date'])[-limit:]
def get_exercise_prs(db,profile_id,exercise_id):
    rows,_=_records(db,profile_id);rows=[r for r in rows if r['exercise_id']==exercise_id]
    if not rows:return dict(max_weight=None,best_e1rm=None,best_volume=None)
    heaviest=max(rows,key=lambda r:(r['weight'],r['reps']));estimates=[(v,r) for r in rows if (v:=_estimate(r)) is not None];best=max(estimates,key=lambda pair:pair[0]) if estimates else None
    volume=max(get_exercise_sessions(db,profile_id,exercise_id,limit=100000),key=lambda r:r['volume'])
    return dict(max_weight=dict(value=float(heaviest['weight']),reps=heaviest['reps'],date=_iso(heaviest['date'])),best_e1rm=dict(value=round(best[0],2),weight=float(best[1]['weight']),reps=best[1]['reps'],date=_iso(best[1]['date']),method='Epley; 1-10 reps; estimate only') if best else None,best_volume=dict(value=volume['volume'],date=volume['date']))
def get_exercise_trend(db,profile_id,exercise_id,days=30):
    rows,_=_records(db,profile_id);rows=[r for r in rows if r['exercise_id']==exercise_id];now=_time(db);boundary=now-timedelta(days=days)
    def stats(items):
        estimates=[v for r in items if (v:=_estimate(r)) is not None]
        return dict(e1rm=round(max(estimates),2) if estimates else None,volume=round(_volume(items),2),sets=len(items),sessions=len({r['session_id'] for r in items}))
    recent=stats([r for r in rows if boundary<=r['date']<now]);old=stats([r for r in rows if boundary-timedelta(days=days)<=r['date']<boundary])
    def pct(new,previous):return round((new-previous)/previous*100,2) if new is not None and previous is not None and previous>0 else None
    return dict(days=days,recent=recent,previous=old,change_pct={k:pct(recent[k],old[k]) for k in ['e1rm','volume','sets']})
def get_muscle_balance(db,profile_id,weeks=4):
    rows,meta=_window(db,profile_id,weeks);counts=Counter(r['muscle'] for r in rows)
    current=Counter(r['muscle'] for r in rows if r['date']>=meta['current'])
    completed=Counter(r['muscle'] for r in rows if _monday(r['date']).date() in meta['complete'])
    muscles=[dict(muscle=m,total_sets=n,current_week_sets=current[m],weekly_sets=round(completed[m]/len(meta['complete']),2) if meta['complete'] else None,status='recorded') for m,n in counts.most_common()]
    groups={'push':{'chest','shoulders','triceps'},'pull':{'back','biceps','lats','traps'},'legs':{'legs','quads','hamstrings','glutes','calves','adductors','hamstring','quadriceps'}}
    totals={key:sum(counts[m] for m in group) for key,group in groups.items()};total=sum(totals.values())
    return dict(period_weeks=weeks,muscles=muscles,completed_observed_weeks=len(meta['complete']),summary={**{k:dict(sets=v,pct=round(v/total*100,2) if total else 0) for k,v in totals.items()},'other_sets':len(rows)-total,'push_pull_ratio':round(totals['pull']/totals['push'],3) if totals['push'] else None},method='Primary-muscle labels only; secondary muscles are not counted; no injury or optimal-volume classification')
def get_effort_analysis(db,profile_id,weeks=8):
    rows,_=_window(db,profile_id,weeks);rirs=[r['rir'] for r in rows if r['rir'] is not None];rpes=[r['rpe'] for r in rows if r['rpe'] is not None];total=len(rows)
    return dict(period_weeks=weeks,total_sets=total,avg_rir=round(sum(rirs)/len(rirs),2) if rirs else None,avg_rpe=round(sum(rpes)/len(rpes),2) if rpes else None,coverage=dict(with_rir_pct=round(len(rirs)/total*100,2) if total else 0,with_rpe_pct=round(len(rpes)/total*100,2) if total else 0),rir_distribution=[dict(rir=value,count=count) for value,count in sorted(Counter(rirs).items())],rpe_distribution=[dict(rpe=value,count=count) for value,count in sorted(Counter(rpes).items())],warning=None,method='Self-reported values; averages do not establish failure, fatigue or injury risk')
def get_weekly_trends(db,profile_id,weeks=12):
    rows,meta=_window(db,profile_id,weeks);groups=defaultdict(list)
    for r in rows:groups[_monday(r['date']).date()].append(r)
    result=[]
    for offset in range(weeks):
        start=meta['start']+timedelta(weeks=offset);items=groups[start.date()];observed=meta['first'] is not None and meta['first']<=(start+timedelta(days=6)).date()
        result.append(dict(week=start.date().isoformat(),sessions=len({r['session_id'] for r in items}),sets=len(items),volume=round(_volume(items),2),partial=start==meta['current'],observed=observed,complete_observed=start.date() in meta['complete']))
    return result

def get_available_exercises(db,profile_id):
    rows,_=_records(db,profile_id);groups=defaultdict(list)
    for r in rows:groups[r['exercise_id']].append(r)
    return [dict(id=eid,name=items[0]['name'],muscle=items[0]['muscle'],sessions_count=len({r['session_id'] for r in items}),sets_count=len(items)) for eid,items in sorted(groups.items(),key=lambda pair:pair[1][0]['name'])]
def get_plateaus(db,profile_id,weeks=3,min_sessions=4):
    rows,_=_window(db,profile_id,weeks);ids={r['exercise_id'] for r in rows};result=[];assessed=0
    by_exercise=defaultdict(list)
    for row in rows:by_exercise[row['exercise_id']].append(row)
    for eid in ids:
        groups=defaultdict(list)
        for r in by_exercise[eid]:
            if _estimate(r) is not None:groups[r['session_id']].append(r)
        points=sorted([(items[0]['date'],max(_estimate(r) for r in items)) for items in groups.values()])
        if len(points)<max(min_sessions,4) or (points[-1][0]-points[0][0]).days<14:continue
        assessed+=1;split=len(points)//2;first=median(v for _,v in points[:split]);last=median(v for _,v in points[split:])
        if last<=first:
            name=next(r['name'] for r in rows if r['exercise_id']==eid)
            result.append(dict(exercise_id=eid,name=name,sessions_count=len(points),first_e1rm=round(first,2),max_e1rm=round(max(v for _,v in points),2),recent_e1rm=round(last,2),improvement_pct=round((last-first)/first*100,2) if first else None))
    return dict(period_weeks=weeks,plateaus=result,assessed_exercises=assessed,insufficient_exercises=len(ids)-assessed,method='Recorded estimated-load stability only. Minimum four sessions spanning fourteen days is an app display rule, not a validated plateau diagnosis.')
def get_actionable_insights(db,profile_id,weeks=8):
    quality=get_data_quality(db,profile_id,weeks);effort=get_effort_analysis(db,profile_id,weeks);items=[]
    def add(code,title,message,action):items.append(dict(code=code,priority='low',icon='i',title=title,message=message,action=action))
    if not quality['total_sets']:
        add('no_data','No working sets recorded','No completed working sets occur in this period.','Log completed sessions to build a history.');return items
    if quality['interpretation']=='limited':
        add('limited_data','Early recording history',f"{quality['sessions_count']} recorded sessions across {quality['observed_span_days']} days.",'These records do not establish injury risk, muscle growth or a training plateau.')
    if effort['coverage']['with_rpe_pct']<100 or effort['coverage']['with_rir_pct']<100:
        add('effort_coverage','Effort recording coverage',f"RPE {effort['coverage']['with_rpe_pct']}%; RIR {effort['coverage']['with_rir_pct']}%.",'Leave unknown effort blank; zero RIR is a real entry, not missing data.')
    if quality['completed_observed_weeks']==0:
        add('partial_week','Current week is incomplete','No complete observed calendar week is available.','Current-week counts are displayed without extrapolating a weekly target.')
    trends=[t for t in get_weekly_trends(db,profile_id,weeks) if t['complete_observed']]
    if len(trends)>=2:
        previous,current=trends[-2:]
        if previous['volume']>0:
            change=round((current['volume']-previous['volume'])/previous['volume']*100,2)
            add('weekly_change','Change in recorded external-load volume',f"{change:+.2f}% between the two most recent complete observed weeks.",'A change in logged workload is not a measured change in muscle growth or strength.')
    if not items:add('descriptive','Recorded observations','This report describes the logged sessions and recorded loads.','Compare the same exercise and equipment with comparable technique; missing records limit interpretation.')
    return items


def prepare_snapshot(db,profile_id):
    db.info['analytics_now']=_now()
    rows,excluded=_records(db,profile_id)
    db.info['analytics_records']={profile_id:(rows,excluded)}
