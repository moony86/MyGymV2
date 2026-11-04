(()=>{
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const originalFetch=fetchActiveSession,originalSelect=selectPlanExercise,originalChange=handleExerciseChange,originalExtra=handleExtraExerciseChange;
const snapshots=new Map();let guideRequest=0;
function box(){let root=document.getElementById('coaching-guide');if(!root){root=document.createElement('section');root.id='coaching-guide';root.className='coaching-card compact-guide';document.getElementById('dynamic-sets-section').before(root);}return root;}
window.fetchActiveSession=async()=>{const data=await originalFetch();const id=data?.session?.id;if(id&&!snapshots.has(id)){const request=fetch('/api/coaching/sessions/'+encodeURIComponent(id)+'/begin',{method:'POST'}).then(response=>{if(!response.ok)throw Error('snapshot');}).catch(()=>{snapshots.delete(id);box().textContent='تعذر تثبيت أهداف البداية؛ لن نقترح زيادة بناءً عليها.';});snapshots.set(id,request);await request;}else if(id){await snapshots.get(id);}return data;};
const tips={
'movement.horizontal_push':'ثبّت جسمك ونفّذ الدفع والعودة بتحكم دون ارتداد.',
'movement.incline_push':'اضبط المقعد المائل وثبّت جسمك، واستخدم مدى متحكمًا ومريحًا.',
'movement.horizontal_pull':'ثبّت الجذع واسحب بتحكم دون تأرجح الجسم.',
'movement.vertical_pull':'اضبط الدعامات ونفّذ السحب والعودة بتحكم دون اندفاع.',
'movement.vertical_push':'ثبّت جسمك وارفع بتحكم دون تعويض الحمل باندفاع الجذع.',
'movement.squat':'ثبّت القدمين واضبط الجهاز واستخدم مدى يمكنك التحكم به.',
'movement.knee_flexion':'اضبط محور الجهاز والوسادة، واثنِ الركبة وأعد الحمل بتحكم.',
'movement.knee_extension':'اضبط محور الجهاز والوسادة، ومد الركبة وأعد الحمل دون ركل.',
'movement.hip_hinge':'تعلّم انثناء الورك والتحكم بالجذع قبل زيادة الحمل.',
'movement.core_flexion':'استخدم حركة جذع متحكمًا بها دون شد الرقبة.',
'movement.calf_extension':'ثبّت القدم والدعامة وتحرك بتحكم دون قفز أو ارتداد.'};
function credit(item){return '<a href="'+esc(item.source_page)+'" target="_blank" rel="noopener">'+esc(item.author||'المصدر')+'</a> · <a href="'+esc(item.license_url)+'" target="_blank" rel="noopener">'+esc(item.license)+'</a>';}
async function guide(){
 const exercise=currentExerciseId;if(!exercise)return;const id=++guideRequest,root=box();root.textContent='…';
 try{
  const response=await fetch('/api/coaching/exercise/'+encodeURIComponent(exercise),{cache:'no-store'});if(!response.ok)throw Error('guide');const data=await response.json();if(id!==guideRequest)return;
  const last=data.last,images=data.images||[],video=data.media,hasMedia=images.length||video;
  root.innerHTML=(last?'<div class="last-load"><span>آخر مرة: <strong>'+esc(last.weight)+' كجم × '+esc(last.reps)+'</strong></span>'+(last.stale?'<small>سجل قديم؛ أعد تقييم الحمل.</small>':'<button type="button" id="copy-last-load" class="secondary">نسخ الحمل</button>')+'</div>':'')+
   (hasMedia?'<details class="exercise-media"><summary>شاهد الحركة <span>'+(images.length?images.length+' صور':'')+(images.length&&video?' · ':'')+(video?'فيديو':'')+'</span></summary><div id="guide-media"></div></details>':'')+
   '<details class="exercise-help"><summary>كيف أنفّذ وأسجّل التمرين؟</summary><p>'+esc(tips[data.movement]||'اضبط الجهاز ومسار الحركة، واطلب شرحًا عمليًا إذا كانت الحركة جديدة عليك.')+'</p><p>جرّب حملًا خفيفًا متحكمًا به قبل مجموعات العمل. سجّل الوزن والعدات الفعلية؛ المجهود اختياري.</p><label>كيف بدت تجربة الحركة؟<select id="trial-effort"><option value="">اختر…</option><option value="easy">سهلة ومتحكم بها</option><option value="appropriate">مناسبة ومتحكم بها</option><option value="hard">صعبة أو فقدت التحكم</option><option value="unsure">لا أعرف</option><option value="discomfort">ألم أو انزعاج غير معتاد</option></select></label><p id="trial-result" role="status"></p><small>الحمل السابق مرجع من سجلك، ولا يثبت ملاءمته اليوم. الدليل لا يراقب تنفيذك.</small><p><a href="/static/exercise-library.html">مكتبة الحركات</a> · <a href="/coach#setup">المعدات والتخصيص</a></p></details>';
  const copy=root.querySelector('#copy-last-load');if(copy)copy.onclick=()=>{const input=document.querySelector('#dynamic-sets-body .set-weight:not(:disabled)');if(input){input.value=last.weight;input.dispatchEvent(new Event('input',{bubbles:true}));}};
  const select=root.querySelector('#trial-effort');select.onchange=()=>{const messages={easy:'ابدأ بمجموعاتك المطلوبة وسجّل ما تنفذه.',appropriate:'سجّل مجموعاتك كما نفذتها.',hard:'لا تزد الحمل. راجع الإعداد والتنفيذ مع مدرب إذا فقدت التحكم.',unsure:'اطلب شرحًا عمليًا قبل محاولة الزيادة.',discomfort:'أوقف الحركة التي تثير الألم وراجع ملاءمتها مع مختص.'};root.querySelector('#trial-result').textContent=messages[select.value]||'';};
  if(hasMedia){const target=root.querySelector('#guide-media');target.innerHTML=(images.length?'<div class="exercise-images">'+images.map((item,index)=>'<figure><a href="'+esc(item.local_url)+'" target="_blank" rel="noopener"><img loading="lazy" src="'+esc(item.local_url)+'" alt="'+esc(item.title)+' — صورة '+(index+1)+'"></a><figcaption>'+credit(item)+'</figcaption></figure>').join('')+'</div>':'')+(video?'<video controls playsinline preload="none" src="'+esc(video.local_url)+'"></video><small>'+credit(video)+' · '+(video.changes?.startsWith('Converted')?'نسخة مضغوطة بلا صوت':'دون تعديل')+'</small>':'')+'<p class="media-note">مثال لنوع الحركة؛ قد يختلف تصميم جهازك. <a href="/static/media-attribution.html">المصادر والرخص</a></p>';}
 }catch(error){if(id===guideRequest)root.innerHTML='<details><summary>دليل الحركة غير متاح الآن</summary><p>أعد اختيار التمرين للمحاولة. تسجيل المجموعات متاح.</p></details>';}
}
window.selectPlanExercise=async index=>{await originalSelect(index);await guide();};
window.handleExerciseChange=()=>{originalChange();guide();};
window.handleExtraExerciseChange=()=>{originalExtra();guide();};
document.addEventListener('DOMContentLoaded',async()=>{try{await fetchActiveSession();if(currentExerciseId)await guide();}catch(error){box().textContent='تعذر تحميل دليل الحركة.';}});
})();
