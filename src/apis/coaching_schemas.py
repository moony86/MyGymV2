from typing import Literal
from pydantic import BaseModel,Field,ConfigDict,model_validator
Equipment=Literal['machine','cable','dumbbell','barbell','smith_machine','bodyweight','band','kettlebell','bench']
class Preferences(BaseModel):
    model_config=ConfigDict(extra='forbid')
    location:Literal['gym','home']
    equipment:list[Equipment]=Field(min_length=1,max_length=9)
    recent_training:Literal['new','returning','regular']
    recent_sessions:int=Field(ge=0,le=28)
    technique_confidence:Literal['learning','familiar']
    has_restrictions:bool=False
    avoid_movements:list[str]=Field(default_factory=list,max_length=30)
    disliked_exercise_ids:list[str]=Field(default_factory=list,max_length=50)
    preferred_days:list[int]=Field(default_factory=list,max_length=7)
    research_opt_in:bool=False
    @model_validator(mode='after')
    def coherent(self):
        if any(day<0 or day>6 for day in self.preferred_days):raise ValueError('Weekday must be 0..6')
        if len(set(self.preferred_days))!=len(self.preferred_days):raise ValueError('Repeated weekday')
        self.equipment=sorted(set(self.equipment));self.avoid_movements=sorted(set(self.avoid_movements));self.disliked_exercise_ids=sorted(set(self.disliked_exercise_ids))
        if self.recent_training=='new' and self.recent_sessions>0:raise ValueError('New trainee cannot report recent sessions')
        return self
class ReviewInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    effort:Literal['easy','appropriate','hard','unsure']
    form_controlled:bool|None=None
    discomfort:bool=False
    outside_activity:bool|None=None
    incomplete_reason:Literal['none','time','equipment','load','discomfort','other']='none'
    @model_validator(mode='after')
    def coherent(self):
        if self.incomplete_reason=='discomfort' and not self.discomfort:raise ValueError('Discomfort answer conflicts with reason')
        return self
class FeedbackInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    stage:Literal['setup','workout','review']
    understood_next_step:bool
    needed_external_help:bool
    friction:Literal['none','instructions','load','logging','equipment','other']='none'
class ProposalInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    exercise_id:str
    token:str=Field(min_length=64,max_length=64)
    action:Literal['increase_reps']
