"""One counting method for plan occurrences and program cycles.
Direct and indirect set exposures stay separate; neither predicts adaptation.
"""
from collections import Counter,defaultdict
from src.apis.deps import get_knowledge_provider
from src.infrastructure.db.models import WorkoutPlanTable,PlanExerciseTable,ExerciseTable

class ProgramNotFoundError(ValueError):pass

class EvaluatorService:
    def __init__(self,db):self.db=db;self.provider=get_knowledge_provider()

    def evaluate_program(self,program_group_id,profile):
        plans=self.db.query(WorkoutPlanTable).filter_by(program_group_id=program_group_id,profile_id=profile.id,enabled=True).order_by(WorkoutPlanTable.day_index).all()
        if not plans:raise ProgramNotFoundError('Program not found')
        report=self.evaluate_plans(plans,profile)
        report['program_group_id']=program_group_id
        return report

    def evaluate_plans(self,plans,profile):
        direct=Counter();indirect=Counter();groups=Counter();group_indirect=Counter()
        frequency=defaultdict(set);movements=Counter();unresolved=[];total=0
        rows=self.db.query(PlanExerciseTable,ExerciseTable).outerjoin(ExerciseTable,ExerciseTable.id==PlanExerciseTable.exercise_id).filter(PlanExerciseTable.plan_id.in_([p.id for p in plans])).all()
        for pe,row in rows:
            sets=pe.target_sets or 0;total+=sets
            try:
                if row is None or not row.knowledge_variant_id:raise ValueError('Unlinked')
                variant=self.provider.variant(row.knowledge_variant_id)
                exercise=self.provider.exercise(variant.exercise)
            except Exception:
                unresolved.append(row.name if row else pe.exercise_id);continue
            primary=set(exercise.primary_muscles or [])
            secondary=set(exercise.secondary_muscles or [])-primary
            primary_groups=set();secondary_groups=set()
            for muscle in primary:
                direct[muscle]+=sets;frequency[muscle].add(pe.plan_id)
                record=self.provider.muscle(muscle)
                if record and record.group:primary_groups.add(record.group)
            for muscle in secondary:
                indirect[muscle]+=sets
                record=self.provider.muscle(muscle)
                if record and record.group:secondary_groups.add(record.group)
            for group in primary_groups:groups[group]+=sets
            for group in secondary_groups-primary_groups:group_indirect[group]+=sets
            movements[exercise.movement_pattern]+=sets
        def entry(identity,direct_count,indirect_count,exposures=None):
            return dict(id=identity,direct_sets=direct_count,indirect_sets=indirect_count,weekly_sets=direct_count,status='descriptive',sessions_with_direct_work=exposures)
        muscle_ids=sorted(set(direct)|set(indirect))
        muscle_report=[entry(m,direct[m],indirect[m],len(frequency[m])) for m in muscle_ids]
        major=['group.chest','group.back','group.shoulders','group.legs','group.arms','group.core']
        return dict(method_version='2026-10-27.2',scope='program_cycle' if len(plans)>1 else 'plan_occurrence',program_group_id=None,plan_id=plans[0].id if len(plans)==1 else None,plan_name=plans[0].name if len(plans)==1 else None,days_count=len(plans),goal=profile.primary_goal,overall_status='DESCRIPTIVE',planned_sets_total=total,major_muscles=[entry(g,groups[g],group_indirect[g]) for g in major],optional_muscles=[],muscles=muscle_report,movement_sets=dict(movements),unresolved_exercises=unresolved,weekly_assumption_confirmed=False,method='Each plan once per cycle. Direct sets and indirect exposures are separate. Each group counted once per exercise set, each primary muscle counted independently. No fixed secondary fraction or pass/fail thresholds.')
