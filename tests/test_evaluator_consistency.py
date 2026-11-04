from types import SimpleNamespace
import uuid
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from src.infrastructure.db.models import Base,ProfileTable,ExerciseTable,WorkoutPlanTable,PlanExerciseTable
from src.services.evaluator_service import EvaluatorService

@pytest.fixture
def context():
    engine=create_engine('sqlite:///:memory:');Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(ProfileTable(id='qa',name='QA'));db.flush()
        plans=[]
        for i,variant in enumerate(['variant.barbell_rdl','variant.machine_chest_press']):
            # Find actual RDL variant ID from the library, rather than assume catalogue names.
            service=EvaluatorService(db)
            if i==0:
                from src.apis.deps import get_knowledge_queries
                variant=get_knowledge_queries().get_variants_for_exercise('exercise.hip_hinge')[0].id
            row=ExerciseTable(id=str(uuid.uuid4()),name='QA '+str(i),knowledge_variant_id=variant,is_active=True)
            plan=WorkoutPlanTable(id=str(uuid.uuid4()),profile_id='qa',name='Day '+str(i),program_group_id='program',day_index=i+1,enabled=True)
            db.add_all([row,plan]);db.flush()
            db.add(PlanExerciseTable(plan_id=plan.id,exercise_id=row.id,order_index=0,target_sets=3,target_reps=8));plans.append(plan)
        db.commit();yield db,plans,SimpleNamespace(id='qa',primary_goal='HYPERTROPHY')
    engine.dispose()

def test_primary_muscles_do_not_disappear_when_sharing_a_group(context):
    db,plans,p=context;report=EvaluatorService(db).evaluate_plans([plans[0]],p)
    muscles={m['id']:m for m in report['muscles']}
    assert muscles['muscle.glutes']['direct_sets']==3
    assert muscles['muscle.hamstrings']['direct_sets']==3
    assert next(g for g in report['major_muscles'] if g['id']=='group.legs')['direct_sets']==3
    assert report['planned_sets_total']==3

def test_single_and_program_paths_use_identical_counting(context):
    db,plans,p=context;service=EvaluatorService(db)
    report=service.evaluate_program('program',p)
    separate=[service.evaluate_plans([plan],p) for plan in plans]
    for m in report['muscles']:
        assert m['direct_sets']==sum(next((x['direct_sets'] for x in r['muscles'] if x['id']==m['id']),0) for r in separate)
        assert m['indirect_sets']==sum(next((x['indirect_sets'] for x in r['muscles'] if x['id']==m['id']),0) for r in separate)
    triceps=next(x for x in report['muscles'] if x['id']=='muscle.triceps')
    assert triceps['direct_sets']==0 and triceps['indirect_sets']==3
    assert report['weekly_assumption_confirmed'] is False
