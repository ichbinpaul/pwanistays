/* Progressive enhancement: all trip ideas and enquiry links work without JS. */
document.addEventListener('DOMContentLoaded',()=>{
 const controls=document.querySelector('.trip-filters');
 const cards=Array.from(document.querySelectorAll('.trip-card'));
 const count=document.querySelector('.trip-count');
 if(!controls||!cards.length)return;
 controls.hidden=false;
 controls.addEventListener('click',event=>{
  const button=event.target.closest('button[data-filter]');if(!button)return;
  const filter=button.dataset.filter;
  controls.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));
  let visible=0;cards.forEach(card=>{card.hidden=filter!=='all'&&!card.dataset.categories.split(' ').includes(filter);if(!card.hidden)visible++});
  count.textContent=visible+' trip idea'+(visible===1?'':'s')+' to explore';
 });
});
