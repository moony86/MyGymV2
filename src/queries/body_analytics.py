"""Changes in entered measurements, without inferred fat loss or muscle gain."""
from collections import defaultdict
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from src.infrastructure.db.models import BodyMeasurementTable
from src.queries.analytics_queries import _monday,_now,LOCAL
FIELDS=('weight','waist','narrow_waist','chest','hips','left_arm','right_arm','left_thigh','right_thigh','neck','body_fat')

def body_report(db,profile_id,weeks=8):
    now=_now();start=_monday(now)-timedelta(weeks=weeks-1)
    # Measurement dates are local calendar dates, not UTC session timestamps.
    records=db.query(BodyMeasurementTable).filter(BodyMeasurementTable.profile_id==profile_id,BodyMeasurementTable.date>=datetime.combine(start.date(),datetime.min.time()),BodyMeasurementTable.date<datetime.combine(now.astimezone(LOCAL).date()+timedelta(days=1),datetime.min.time())).order_by(BodyMeasurementTable.date,BodyMeasurementTable.created_at,BodyMeasurementTable.id).all()
    days={};duplicates=0
    for row in records:
        day=row.date.date().isoformat()
        if day in days:duplicates+=1
        days[day]=row
    records=list(days.values());fields={}
    for name in FIELDS:
        points=[]
        for row in records:
            value=getattr(row,name)
            if value is None:continue
            value=Decimal(str(value))
            if not value.is_finite() or value<0 or (name!='body_fat' and value==0) or (name=='body_fat' and value>100):continue
            points.append(dict(date=row.date.date().isoformat(),value=float(value)))
        if not points:continue
        first,last=points[0],points[-1]
        change=float(Decimal(str(last['value']))-Decimal(str(first['value']))) if len(points)>1 else None
        fields[name]=dict(unit='%' if name=='body_fat' else 'kg' if name=='weight' else 'cm',points=points,latest=last,baseline=first if len(points)>1 else None,change=change,change_unit='percentage_points' if name=='body_fat' else 'kg' if name=='weight' else 'cm',span_days=(datetime.fromisoformat(last['date'])-datetime.fromisoformat(first['date'])).days,observations=len(points))
    return dict(period_weeks=weeks,period_start=start.date().isoformat(),period_end=now.astimezone(LOCAL).date().isoformat(),recorded_days=len(records),legacy_duplicate_days=duplicates,fields=fields,method='Latest entry per local calendar day; per-field first/last entered values within selected period. Body-fat change uses percentage points. No inferred body composition, growth or causal attribution.')
