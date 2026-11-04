(()=>{
const labels={'group.chest':'الصدر','group.back':'الظهر','group.shoulders':'الأكتاف','group.legs':'الأرجل مجتمعة','group.arms':'الذراعان','group.core':'الجذع','muscle.quads':'أمامية الفخذ','muscle.hamstrings':'خلفية الفخذ','muscle.glutes':'الألوية','muscle.calves':'السمانة','muscle.abs':'البطن','muscle.biceps':'البايسبس','muscle.triceps':'الترايسبس','muscle.lats':'الظهر العريض','muscle.upper_back':'أعلى الظهر','muscle.front_delts':'الكتف الأمامي','muscle.side_delts':'الكتف الجانبي','muscle.rear_delts':'الكتف الخلفي','muscle.chest.middle':'الصدر الأوسط','muscle.chest.upper':'أعلى الصدر'};
const name=id=>labels[id]||(typeof muscleLabel==='function'?muscleLabel(id):id);
const num=value=>Number(value).toLocaleString('ar-SA',{maximumFractionDigits:2});
function modal(titleText){const body=document.getElementById('eval-modal-body');body.replaceChildren();document.getElementById('eval-modal-title').textContent=titleText;return body;}
function add(body,tag,text,cls=''){const el=document.createElement(tag);el.textContent=text;el.className=cls;body.appendChild(el);return el;}
function close(body){const button=add(body,'button','إغلاق','btn-secondary');button.onclick=()=>closeModal('eval-modal');button.style.width='100%';}
window.renderEvaluation=data=>{
 const body=modal('توزيع '+(data.plan_name||'البرنامج'));
 add(body,'p',data.scope==='program_cycle'?'تنفيذ كل يوم من البرنامج مرة واحدة في دورة؛ لم نفترض أن الدورة تساوي أسبوعًا.':'تنفيذ هذه الخطة مرة واحدة، وليس حجمًا أسبوعيًا مؤكدًا.','text-muted');
 add(body,'p','مجموعات التمرين المخططة: '+num(data.planned_sets_total)+'. المشاركة الثانوية تُعرض منفصلة، ولا تُحوّل إلى نصف أو ربع مجموعة.','text-muted');
 add(body,'h3','المجموعات المباشرة حسب العضلة');
 for(const item of data.muscles||[]){
  const row=add(body,'div','','eval-row');add(row,'span',name(item.id));add(row,'strong',num(item.direct_sets)+' مباشرة · '+num(item.indirect_sets)+' مشاركة ثانوية');
  add(body,'small',num(item.sessions_with_direct_work)+' أيام بها عمل مباشر في الدورة','text-muted');
 }
 add(body,'p','قد تستهدف المجموعة عدة عضلات؛ لذلك لا تجمع صفوف العضلات للحصول على مجموع مجموعات التمرين. عدد المجموعات وحده لا يقيس جودة التكنيك أو شدة التحفيز أو نمو العضلة.','text-muted');
 if(data.unresolved_exercises?.length)add(body,'p','تعذر تصنيف: '+data.unresolved_exercises.join('، '),'text-muted');
 close(body);
};
let busy=false;
window.generatePlan=async()=>{
 if(busy)return;
 try{
  const choices=await fetch('/api/coaching/preferences').then(r=>r.json());if(!choices.preferences){location.href='/coach#setup';return;}
  const profile=await fetch('/api/profile').then(r=>r.ok?r.json():null);
  if(!profile){showSnackbar('أكمل بياناتك الشخصية أولًا.','error');return;}
  if(!confirm('إنشاء برنامج مبدئي لـ '+profile.training_days_per_week+' أيام، بوقت تخطيط لا يتجاوز '+Math.min(90,profile.session_duration_minutes)+' دقيقة للحصة؟\nستحتاج مراجعة التمارين واختيار أوزان مناسبة.'))return;
  busy=true;const trigger=document.querySelector('button[onclick="generatePlan()"]');if(trigger)trigger.disabled=true;
  try{
   const result=await apiRequest('/generate',{method:'POST'});await loadPlans();
   const data=result.generation,body=modal('مراجعة البرنامج المُنشأ');
   add(body,'p','أُنشئت '+num(result.plans.length)+' خطط مبدئية. '+(data.schedule_assigned?'حُفظت الجدولة حسب الأيام التي اخترتها.':'لم تُحدد أيام الأسبوع؛ اضبط الجدولة بما يناسبك.'),'text-muted');
   for(const day of data.days)add(body,'p','اليوم '+num(day.day)+': '+num(day.working_sets)+' مجموعة · '+num(day.estimated_minutes)+' دقيقة تقديرية من '+num(day.time_budget_minutes)+' متاحة.');
   add(body,'p','الوقت تقدير تخطيطي: 7 دقائق إعداد، ودقيقتان لكل تمرين، و45 ثانية للمجموعة، مع الراحة بين المجموعات. لا يشمل ازدحام الأجهزة ولا يضمن وقتًا فعليًا.','text-muted');
   if(data.warnings.some(x=>x.startsWith('day ')))add(body,'p','بعض الحركات لم تتوفر أو اختُصرت لمراعاة الوقت. راجع توزيع العضلات لكل يوم قبل الاعتماد عليه.','text-muted');
   if(data.warnings.includes('beginner_high_frequency_review_recovery'))add(body,'p','اخترت أيامًا كثيرة لمبتدئ؛ راجع توزيع الراحة وقدرتك على الالتزام قبل اعتماد البرنامج.','text-muted');
   if(data.warnings.includes('odd_upper_lower_cycle_is_asymmetric'))add(body,'p','عدد الأيام فردي في تقسيم علوي/سفلي، لذا عدد الحصص العلوية والسفلية غير متساوٍ في هذه الدورة. راجع ترتيب الدورة التالية.','text-muted');
   add(body,'p','هذا اقتراح بداية وفق المستوى والهدف والوقت والمكتبة المتاحة. لا يعرف إصاباتك أو مهارتك أو الأجهزة الموجودة عندك، ولا يضمن برنامجًا احترافيًا شخصيًا.','text-muted');
   close(body);document.getElementById('eval-modal').classList.add('active');document.getElementById('eval-modal').style.display='flex';
  }finally{busy=false;if(trigger)trigger.disabled=false;}
 }catch(error){showSnackbar('تعذر إنشاء برنامج مناسب. تحقق من عدد الأيام وبيانات الملف وتوفر التمارين.','error');console.error(error);}
};
})();