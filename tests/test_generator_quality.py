from types import SimpleNamespace
from decimal import Decimal
import uuid
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from src.infrastructure.db.models import Base,ExerciseTable,ProfileTable,WorkoutPlanTable,PlanExerciseTable
from src.services.generator_service import GeneratorService
from src.services.generator_selection import minutes,prescription

@pytest.fixture
def generator():
    engine=create_engine('sqlite:///:memory:');Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(ProfileTable(id='qa',name='Generator QA'));db.flush()
        service=GeneratorService(db)
        for exercise in service.provider.exercises():
            for variant in service.queries.get_variants_for_exercise(exercise.id):
                db.add(ExerciseTable(id=str(uuid.uuid4()),name=variant.display_name,knowledge_variant_id=variant.id,is_active=True))
        db.commit();yield service
    engine.dispose()

def profile(level='BEGINNER',days=3,goal='GENERAL_FITNESS',duration=45):
    return SimpleNamespace(id='qa',experience_level=level,training_days_per_week=days,primary_goal=goal,session_duration_minutes=duration)

@pytest.mark.parametrize('level',['BEGINNER','INTERMEDIATE','ADVANCED'])
@pytest.mark.parametrize('days',[2,3,4,5,6])
@pytest.mark.parametrize('goal',['GENERAL_FITNESS','HYPERTROPHY','STRENGTH','FAT_LOSS'])
@pytest.mark.parametrize('duration',[15,45,90])
def test_generation_respects_profile_catalogue_and_time(generator,level,days,goal,duration):
    p=profile(level,days,goal,duration);plans=generator.generate_plan_for_profile(p)
    assert len(plans)==days and all(x.profile_id=='qa' for x in plans)
    for plan in plans:
        rows=generator.db.query(PlanExerciseTable).filter_by(plan_id=plan.id).all()
        assert rows and len(rows)<=6
        assert len({r.exercise_id for r in rows})==len(rows)
        cost=7+sum(2+r.target_sets*.75+(r.target_sets-1)*r.rest_seconds/60 for r in rows)
        assert cost<=duration
        if level=='BEGINNER':
            assert all(r.target_sets<=2 for r in rows)
            for r in rows:
                variant=generator.provider.variant(generator.db.get(ExerciseTable,r.exercise_id).knowledge_variant_id)
                assert variant.equipment!='equipment.barbell'
                assert getattr(variant,'difficulty',None) not in ['intermediate','advanced']

@pytest.mark.parametrize('days',[2,3,4])
def test_full_body_keeps_knee_posterior_and_both_pull_directions(generator,days):
    p=profile(days=days);template=generator.provider.template('template.full_body');week=set()
    for day in range(1,days+1):
        selected=generator._select_exercises_for_day(p,template,day)
        patterns={x[0].movement_pattern for x in selected};week|=patterns
        assert 'movement.squat' in patterns
        assert patterns & {'movement.knee_flexion','movement.hip_hinge'}
        assert 'movement.horizontal_push' in patterns
    assert {'movement.horizontal_pull','movement.vertical_pull'} <= week

def test_missing_catalogue_creates_no_empty_plans(generator):
    generator.db.query(ExerciseTable).delete();generator.db.commit()
    with pytest.raises(ValueError):generator.generate_plan_for_profile(profile())
    assert generator.db.query(WorkoutPlanTable).count()==0

def test_strength_has_lower_compound_reps_and_longer_rest(generator):
    ex=generator.provider.exercise('exercise.horizontal_press')
    _,strength_reps,strength_rest=prescription(profile(goal='STRENGTH'),ex)
    _,general_reps,general_rest=prescription(profile(),ex)
    assert strength_reps<general_reps and strength_rest>general_rest

def test_unsupported_days_and_unknown_manual_template_are_controlled(generator):
    from src.services.generator_service import NoSuitableTemplateError
    with pytest.raises(NoSuitableTemplateError):generator.generate_plan_for_profile(profile(days=7))
    with pytest.raises((ValueError,KeyError)):generator.generate_plan_for_profile(profile(),template_id='does-not-exist')
    assert generator.db.query(WorkoutPlanTable).count()==0

def test_short_full_body_rotates_limited_time_across_movement_families(generator):
    p=profile(days=2,duration=15);template=generator.provider.template('template.full_body')
    patterns={item[0].movement_pattern for day in [1,2] for item in generator._select_exercises_for_day(p,template,day)}
    assert 'movement.horizontal_push' in patterns and 'movement.squat' in patterns
    assert patterns & {'movement.vertical_pull','movement.horizontal_pull'}
    assert patterns & {'movement.hip_hinge','movement.knee_flexion'}

def test_saved_equipment_restrictions_and_weekdays_drive_generation(generator):
    from src.infrastructure.db.models import CoachingProfileTable
    from src.apis.coaching_schemas import Preferences
    from src.services.plan_options import get_options
    preferences=Preferences(location='gym',equipment=['machine','cable'],recent_training='new',recent_sessions=0,technique_confidence='learning',avoid_movements=['movement.vertical_push'],preferred_days=[0,2,4])
    generator.db.add(CoachingProfileTable(profile_id='qa',payload=preferences.model_dump_json()));generator.db.commit()
    plans=generator.generate_plan_for_profile(profile(level='ADVANCED'))
    for plan in plans:
        assert get_options(generator.db,plan)['schedules'][0]['days_of_week']==[[0],[2],[4]][plan.day_index-1]
        for row in generator.db.query(PlanExerciseTable).filter_by(plan_id=plan.id).all():
            ex=generator.db.get(ExerciseTable,row.exercise_id);variant=generator.provider.variant(ex.knowledge_variant_id)
            assert variant.equipment in ['equipment.machine','equipment.cable']
            assert generator.provider.exercise(variant.exercise).movement_pattern!='movement.vertical_push'
            assert row.target_sets<=2

def test_new_program_dashboard_starts_at_day_one(generator):
    from src.infrastructure.db.models import CoachingProfileTable
    from src.apis.coaching_schemas import Preferences
    from src.apis.routers.coaching import dashboard
    data=Preferences(location='gym',equipment=['machine','cable'],recent_training='new',recent_sessions=0,technique_confidence='learning')
    generator.db.add(CoachingProfileTable(profile_id='qa',payload=data.model_dump_json()));generator.db.commit()
    first=generator.generate_plan_for_profile(profile())
    second=generator.generate_plan_for_profile(profile())
    report=dashboard(db=generator.db,owner='qa')
    assert report['next_plan']['id']==second[0].id
    assert report['next_plan']['id']!=first[0].id
