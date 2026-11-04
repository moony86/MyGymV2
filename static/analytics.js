function renderBody(data){
 const names={weight:'الوزن',waist:'الخصر',narrow_waist:'الخصر الضيق',chest:'الصدر',hips:'الأوراك',left_arm:'الذراع الأيسر',right_arm:'الذراع الأيمن',left_thigh:'الفخذ الأيسر',right_thigh:'الفخذ الأيمن',neck:'العنق',body_fat:'نسبة الدهون المُدخلة'},unit={kg:'كجم',cm:'سم','%':'%'};
 const cards=Object.entries(data.fields).map(([key,item])=>{
 const change=item.change===null?'لا توجد مقارنة':(item.change>0?'+':'')+n(item.change)+' '+(item.change_unit==='percentage_points'?'نقطة مئوية':unit[item.unit]);
 return '<article class="measurement"><strong>'+esc(names[key]||key)+'</strong><p>آخر قيمة: <b>'+n(item.latest.value)+' '+unit[item.unit]+'</b> · '+esc(item.latest.date)+'</p><p class="muted">'+(item.baseline?'أول قيمة: '+n(item.baseline.value)+' '+unit[item.unit]+' · '+esc(item.baseline.date):'تحتاج قياسًا آخر للمقارنة.')+'</p><p><b>'+esc(change)+'</b> · '+n(item.span_days)+' أيام</p><small>'+n(item.observations)+' قياسات في الفترة</small></article>';
 });
 $('body-metrics').className='measurement-grid';
 $('body-metrics').innerHTML=cards.length?cards.join(''):'<p class="muted">لا توجد قياسات مسجلة في الفترة المختارة. أضف قياسًا من الملف الشخصي.</p>';
 $('body-note').textContent='المقارنة بين أول وآخر إدخال متاح لكل قياس في الفترة المختارة؛ قد تختلف تواريخ القياسات. الزيادة والنقصان لا يحملان حكمًا تلقائيًا بالتحسن، ولا يثبتان نمو العضلات أو خسارة الدهون.'+(data.legacy_duplicate_days?' توجد أيام قديمة مكررة؛ عُرض أحدث إدخال لكل يوم.':'');
}
const $=id=>document.getElementById(id),n=v=>v===null||v===undefined?'—':Number(v).toLocaleString('ar-SA',{maximumFractionDigits:2}),esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const date=v=>new Date(v).toLocaleDateString('ar-SA',{timeZone:'Asia/Riyadh',year:'numeric',month:'short',day:'numeric'});
const muscleNames={chest:'صدر',back:'ظهر',shoulders:'أكتاف',triceps:'ترايسبس',biceps:'بايسبس',quads:'أمامية الفخذ',hamstrings:'خلفية الفخذ',glutes:'ألوية',calves:'سمانة',abs:'بطن',legs:'أرجل',unmapped:'غير مصنّف'};
let loadId=0,detailId=0;
function table(headers,rows){return '<table><thead><tr>'+headers.map(v=>'<th>'+esc(v)+'</th>').join('')+'</tr></thead><tbody>'+rows.map(r=>'<tr>'+r.map(v=>'<td>'+v+'</td>').join('')+'</tr>').join('')+'</tbody></table>';}
function stat(value,label){return '<div class="stat"><strong>'+n(value)+'</strong><span>'+esc(label)+'</span></div>';}
async function api(path){const response=await fetch('/api/analytics/'+path,{cache:'no-store'});if(!response.ok)throw Error('تعذر تحميل البيانات. أعد المحاولة أو تحقق من تسجيل الدخول.');return response.json();}
function insights(items,q){
 const labels={
 no_data:['لا توجد مجموعات مكتملة في الفترة','ابدأ التسجيل؛ عدم وجود بيانات لا يعني أن كل شيء مثالي.'],
 limited_data:['السجل ما زال قصيرًا',n(q.sessions_count)+' جلسة خلال '+n(q.observed_span_days)+' يومًا. لا نستنتج منه إصابة أو نمو عضلي أو جمودًا.'],
 effort_coverage:['دقة المجهود تعتمد على ما تسجّله','اترك المجهود غير المعروف فارغًا. RIR صفر يعني أنك سجّلت عدم وجود تكرارات متبقية، وليس قيمة مفقودة.'],
 partial_week:['لا يتوفر أسبوع مكتمل للمقارنة','نعرض مجموعات هذا الأسبوع كما هي، دون تقسيمها على أسابيع سبقت بداية التسجيل.'],
 weekly_change:['تغير الحجم المسجّل بين أسبوعين مكتملين','راجع أعداد الجلسات والمجموعات في الجدول. تغير الحجم المسجّل لا يثبت تغير القوة أو نمو العضلة.'],
 descriptive:['قراءة وصفية للسجل','قارن التمرين نفسه والجهاز نفسه مع أسلوب أداء متقارب.']
 };
 $('insights').innerHTML=items.map(item=>{const text=labels[item.code]||labels.descriptive;return '<div class="observation"><strong>'+esc(text[0])+'</strong><p>'+esc(text[1])+'</p></div>';}).join('');
}
function render(data){
 const q=data.quality,m=data.muscle_balance,e=data.effort;
 $('quality').innerHTML='<strong>'+(q.interpretation==='limited'?'بيانات محدودة — الأرقام المسجّلة متاحة، والاستنتاجات محدودة.':'هذه النتائج تصف سجلك، ولا تشخّص الاستشفاء أو الإصابة.')+'</strong><p>'+date(q.period_start)+' ← '+date(q.period_end)+' · بتوقيت الرياض</p><p>'+n(q.recorded_days)+' أيام تسجيل · '+n(q.completed_observed_weeks)+' أسابيع مكتملة منذ بدء التسجيل · الأسبوع الحالي غير مكتمل.</p>'+(q.excluded_invalid_sets_all_history?'<p>استُبعدت '+n(q.excluded_invalid_sets_all_history)+' مجموعات قديمة غير صالحة حسابيًا.</p>':'');
 $('stats').innerHTML=stat(q.sessions_count,'جلسات بمجموعات عمل في الفترة')+stat(q.total_sets,'مجموعات عمل مسجّلة')+stat(q.total_reps,'تكرارات مسجّلة')+stat(q.external_load_volume_kg,'كجم × تكرار من الحمل المُدخل');
 insights(data.insights,q);
 const maximum=Math.max(1,...m.muscles.map(x=>x.total_sets));
 $('muscles').innerHTML=m.muscles.length?m.muscles.map(x=>'<div class="row"><strong>'+esc(muscleNames[x.muscle]||x.muscle)+'</strong><span>'+n(x.total_sets)+' مجموعات في الفترة</span></div><div class="track"><span style="width:'+(x.total_sets/maximum*100)+'%"></span></div><p class="muted">هذا الأسبوع: '+n(x.current_week_sets)+' · متوسط الأسابيع المكتملة: '+(x.weekly_sets===null?'غير متاح':n(x.weekly_sets))+'</p>').join(''):'<p class="muted">لا مجموعات مسجّلة.</p>';
 $('effort').innerHTML='<div class="numbers">'+stat(e.avg_rpe,'متوسط RPE المسجّل')+stat(e.avg_rir,'متوسط RIR المسجّل')+'</div><p class="muted">تغطية RPE: '+n(e.coverage.with_rpe_pct)+'% · تغطية RIR: '+n(e.coverage.with_rir_pct)+'%</p><p class="muted">قد تتضمن السجلات القديمة قيم مجهود افتراضية. لا نستطيع تمييزها عن الإدخال الصريح بأثر رجعي.</p>'+e.rir_distribution.map(x=>'<div class="row"><span>RIR '+n(x.rir)+'</span><span>'+n(x.count)+' مجموعات</span></div>').join('');
 $('weeks').innerHTML=table(['بداية الأسبوع','حالة التسجيل','جلسات','مجموعات','كجم × تكرار'],data.trends.map(w=>[esc(w.week),'<span class="tag">'+(w.partial?'الأسبوع الحالي — غير مكتمل':!w.observed?'قبل أول تسجيل':w.complete_observed?'أسبوع مكتمل':'بداية تسجيل جزئية')+'</span>',n(w.observed?w.sessions:null),n(w.observed?w.sets:null),n(w.observed?w.volume:null)]));
 const p=data.plateaus;
 $('plateaus').innerHTML='<p class="muted">تمارين قابلة للفحص: '+n(p.assessed_exercises)+' · تحتاج سجلات أكثر: '+n(p.insufficient_exercises)+'</p>'+(p.plateaus.length?table(['التمرين','جلسات','التغير التقديري'],p.plateaus.map(x=>[esc(x.name),n(x.sessions_count),n(x.improvement_pct)+'%'])):'<p>'+(p.assessed_exercises?'لم تُرصد حالة ثبات وفق قاعدة العرض، وهذا لا يثبت استمرار التحسن.':'لا توجد بيانات كافية لفحص ثبات الأداء.')+'</p>');
 $('method').textContent='نسخة الحساب: '+q.method_version+' · تُستبعد الإحماءات والجلسات غير المكتملة.';
}
async function load(){
 const id=++loadId;++detailId;$('status').className='';$('status').textContent='جاري قراءة السجل…';
 try{const [data,exercises,body]=await Promise.all([api('overview?weeks='+$('period').value),api('exercises'),api('body?weeks='+$('period').value)]);if(id!==loadId)return;render(data);renderBody(body);const selected=$('exercise').value;$('exercise').replaceChildren(new Option('اختر تمرينًا…',''));for(const ex of exercises)$('exercise').add(new Option(ex.name+' · '+ex.sets_count+' مجموعات',ex.id));if(exercises.some(x=>x.id===selected)){$('exercise').value=selected;await detail();}$('status').textContent='تم تحديث الأرقام من سجلك.';}
 catch(error){if(id!==loadId)return;$('status').className='error';$('status').textContent=error.message;}
}
async function detail(){
 const id=++detailId,exercise=$('exercise').value;if(!exercise){$('detail').innerHTML='<p class="muted">اختر تمرينًا من سجلك.</p>';return;}
 $('detail').textContent='جاري قراءة تفاصيل التمرين…';
 try{const d=await api('exercise/'+encodeURIComponent(exercise)+'?days=30&limit=100&weeks='+$('period').value);if(id!==detailId)return;const prs=d.prs;
 $('detail').innerHTML='<div class="numbers">'+stat(prs.max_weight?.value??null,'أعلى حمل مسجّل لهذا التمرين')+stat(prs.best_e1rm?.value??null,'أفضل 1RM تقديري — ليس اختبارًا فعليًا')+'</div><p class="muted">المجموعات الفعلية أدناه هي المرجع. لا تقارن الحمل بين جهازين مختلفين.</p>'+table(['التاريخ','المجموعات: كجم × تكرار','الحجم','1RM تقديري'],d.sessions.slice().reverse().map(s=>[esc(date(s.date)),s.sets.map(x=>n(x.weight)+' × '+n(x.reps)).join('<br>'),n(s.volume),n(s.e1rm)]));}
 catch(error){if(id===detailId)$('detail').textContent=error.message;}
}
$('period').addEventListener('change',load);$('exercise').addEventListener('change',detail);load();