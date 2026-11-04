from datetime import datetime
from zoneinfo import ZoneInfo
import uuid
import pytest
from tests.test_api import client,db_session,clean_db

def person():
    identity=client.post('/api/profiles',json={'name':'Measurement QA '+uuid.uuid4().hex[:6]}).json()['id']
    return {'X-Profile-Id':identity}
def payload(**values):
    return dict(date=datetime.now(ZoneInfo('Asia/Riyadh')).date().isoformat(),type='weekly',weight='79.50',**values)

def test_same_day_duplicate_is_rejected_without_new_row(db_session):
    h=person();first=client.post('/api/profile/measurements',headers=h,json=payload())
    assert first.status_code==200,first.text
    second=client.post('/api/profile/measurements',headers=h,json=payload())
    assert second.status_code==400,second.text
    rows=client.get('/api/profile/measurements',headers=h).json()
    assert len(rows)==1 and rows[0]['weight']=='79.50'

@pytest.mark.parametrize('field,value',[('weight','-1'),('weight','1000'),('weight','79.555'),('waist','-1'),('body_fat','101'),('date','invalid')])
def test_invalid_measurement_is_not_saved(db_session,field,value):
    h=person();data=payload();data[field]=value
    assert client.post('/api/profile/measurements',headers=h,json=data).status_code==422
    assert client.get('/api/profile/measurements',headers=h).json()==[]

def test_measurement_delete_is_scoped(db_session):
    a=person();b=person();r=client.post('/api/profile/measurements',headers=a,json=payload())
    identity=r.json()['id']
    assert client.delete('/api/profile/measurements/'+identity,headers=b).status_code==404
    assert len(client.get('/api/profile/measurements',headers=a).json())==1
    assert client.delete('/api/profile/measurements/'+identity,headers=a).status_code==200
    assert client.get('/api/profile/measurements',headers=a).json()==[]
