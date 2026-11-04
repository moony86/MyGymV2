document.addEventListener('DOMContentLoaded',async()=>{
 const main=document.querySelector('body > .container');if(!main)return;
 const card=document.createElement('section');card.className='coaching-card';card.innerHTML='<h2>خطوتي التالية</h2><p id="home-coaching-status">جاري قراءة تخصيصك وحصتك الحالية…</p><a href="/coach">التخصيص والمتابعة</a> · <a href="/static/exercise-library.html">مكتبة الحركات</a>';const header=main.querySelector('header');if(header)header.after(card);else main.prepend(card);
 let data=null;
 const button=document.getElementById('main-workout-btn');
 function destination(){if(!data||data.active_session)return null;if(!data.preferences_complete)return '/coach#setup';if(!data.next_plan)return '/coach#setup';if(data.next_plan_scheduled_today===false)return '/plans';return '/workout?plan_id='+encodeURIComponent(data.next_plan.id);}
 if(button)button.addEventListener('click',event=>{if(data?.active_session)return;event.preventDefault();event.stopImmediatePropagation();if(!data){card.querySelector('p').textContent='انتظر تأكيد حالة الحصة قبل البدء.';return;}location.href=destination();},true);
 try{
  const response=await fetch('/api/coaching/dashboard',{cache:'no-store'});if(!response.ok)throw Error('dashboard');data=await response.json();
  if(!data.preferences_complete)card.querySelector('p').textContent='حدد معداتك وخبرتك الفعلية قبل إنشاء برنامج جديد.';
  else card.querySelector('p').textContent='هذا الأسبوع: '+data.completed_sessions+' حصص · '+data.reviewed_sessions+' مراجعات.';
  if(button&&!data.active_session){const label=!data.preferences_complete?'خصّص برنامجي أولًا':!data.next_plan?'أنشئ برنامجي المبدئي':data.next_plan_scheduled_today===false?'راجع خططي وجدولتي':'ابدأ حصة برنامجي';const update=()=>{if(button.textContent!==label)button.textContent=label;};update();const observer=new MutationObserver(update);observer.observe(button,{childList:true,subtree:true,characterData:true});}
  if(!data.active_session){const free=document.createElement('button');free.type='button';free.className='secondary';free.textContent='تسجيل حصة حرة';free.onclick=async()=>{free.disabled=true;try{const response=await fetch('/api/workouts/start',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});if(!response.ok)throw Error('start');location.href='/workout';}catch(error){card.querySelector('p').textContent='تعذر بدء الحصة الحرة. تحقق من الاتصال وأعد المحاولة.';free.disabled=false;}};const more=document.createElement('details');const summary=document.createElement('summary');summary.textContent='خيارات أخرى';more.append(summary,free);card.appendChild(more);}
 }catch(error){card.querySelector('p').textContent='تعذر تأكيد حالة الحصة. أعد تحميل الصفحة قبل البدء.';}
});