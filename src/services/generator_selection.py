"""Deterministic starting prescriptions, not individualized coaching guarantees."""
VERSION='2026-10-27.2'

def prescription(profile,exercise):
    compound=exercise.category=='compound'
    level=profile.experience_level.upper()
    sets=2 if level=='BEGINNER' or not compound else 3
    if level=='ADVANCED' and not compound:sets=3
    if profile.primary_goal=='STRENGTH':return sets,(5 if compound else 10),(180 if compound else 90)
    return sets,(8 if compound and profile.primary_goal=='HYPERTROPHY' else 10 if compound else 12),(120 if compound else 90)

def minutes(items,profile):
    # Transparent planning allowance: 7 min preparation, 2 min setup per exercise,
    # 45 sec per set and rest only BETWEEN sets. Actual duration is not measured.
    return round(7+sum(2+sets*.75+(sets-1)*prescription(profile,exercise)[2]/60 for exercise,variant,row,sets,reps in items),2)

def select_day(service,profile,template,day):
    rules=service.provider.generator_rules
    level=profile.experience_level.lower()
    config=rules['variant_selection'].get(level,{})
    avoid=set(config.get('avoid',[]));prefer=config.get('prefer',[])
    slots=template.rotation_pattern
    kind=slots[(day-1)%len(slots)].get('type','full_body') if slots else 'full_body'
    full=kind.startswith('full_body')
    pull=['horizontal_pull','vertical_pull'] if day%2 else ['vertical_pull','horizontal_pull']
    if full:
        posterior=['knee_flexion','hip_hinge'] if level=='beginner' else ['hip_hinge','knee_flexion']
        priorities=[['horizontal_push','incline_push'],['squat','knee_extension'],pull,posterior,['vertical_push','lateral_raise'],(['core_flexion','calf_extension'] if day%2 else ['calf_extension','core_flexion'])]
    elif kind=='upper':
        priorities=[['horizontal_push','incline_push'],pull,['vertical_push','lateral_raise'],list(reversed(pull)),['biceps_curl'],['triceps_extension']]
    elif kind=='push':
        priorities=[['horizontal_push'],['vertical_push'],['incline_push'],['lateral_raise'],['triceps_extension']]
    elif kind=='pull':
        priorities=[['vertical_pull'],['horizontal_pull'],['rear_delt'],['biceps_curl']]
    elif kind in ['lower','legs']:
        priorities=[['squat'],['knee_flexion'],['hip_hinge'],['calf_extension'],['core_flexion'],['knee_extension']]
    else:raise ValueError('Unsupported template rotation slot: '+kind)
    choices=getattr(service,'coaching_preferences',None)
    allowed_equipment={'equipment.'+item for item in choices['equipment']} if choices else None
    avoid_movements=set(choices.get('avoid_movements',[])) if choices else set()
    disliked=set(choices.get('disliked_exercise_ids',[])) if choices else set()
    candidates=[]
    for exercise in service.provider.exercises():
        if exercise.movement_pattern in avoid_movements:continue
        if level=='beginner' and getattr(exercise,'beginner_friendly',None) is False:continue
        for variant in service._rank_variants(exercise.id,avoid,prefer):
            if variant.equipment in avoid or (allowed_equipment is not None and variant.equipment not in allowed_equipment):continue
            if level=='beginner' and getattr(variant,'difficulty',None) in ['intermediate','advanced']:continue
            row=service._get_linked_exercise_row(variant.id)
            if row is not None and row.id not in disliked:
                candidates.append((exercise,variant,row));break
    maximum=min(8,int(rules.get('exercise_limits',{}).get('maximum',6)))
    selected=[];used=set();patterns=set()
    budget=min(90,int(profile.session_duration_minutes))
    if full and budget<25:
        core=priorities[:4];offset=((day-1)*2)%4
        priorities=core[offset:]+core[:offset]+priorities[4:]
    for options in priorities:
        if len(selected)>=maximum:break
        matches=[]
        for pattern in options:
            matches=[x for x in candidates if x[0].movement_pattern=='movement.'+pattern and x[2].id not in used and x[0].movement_pattern not in patterns]
            if matches:break
        if not matches:
            service.warnings.append('day '+str(day)+': unavailable movement '+('/'.join(options)))
            continue
        exercise,variant,row=sorted(matches,key=lambda x:(x[0].category!='compound',x[0].id,x[2].id))[0]
        sets,reps,rest=prescription(profile,exercise)
        if budget<20:sets=1
        while sets>1 and minutes(selected+[(exercise,variant,row,sets,reps)],profile)>budget:sets-=1
        if minutes(selected+[(exercise,variant,row,sets,reps)],profile)>budget:
            service.warnings.append('day '+str(day)+': time budget omitted '+exercise.id);continue
        selected.append((exercise,variant,row,sets,reps));used.add(row.id);patterns.add(exercise.movement_pattern)
    if not selected:raise ValueError('No usable exercises fit the available catalogue and session time')
    if len(selected)<4:service.warnings.append('day '+str(day)+': short session or limited catalogue; review movement coverage')
    return selected
