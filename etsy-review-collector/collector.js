(()=>{
 'use strict';
 if(globalThis.__vinazonCollector)return;
 const sleep=ms=>new Promise(r=>setTimeout(r,ms));
 const norm=s=>String(s||'').replace(/\s+/g,' ').trim();
 const visible=e=>!!e&&e.getClientRects().length>0&&getComputedStyle(e).visibility!=='hidden'&&!e.closest('[aria-hidden="true"],[inert]');
 const itemLabel=/view all reviews for this item|reviews for this item|item reviews|đánh giá (?:cho|về) (?:mặt hàng|sản phẩm) này/i;
 const allShop=/reviews for this shop|shop reviews|đánh giá (?:cho|về) cửa hàng/i;
 let job=null,host=null,ui=null,cachedPane=null;
 function build(){
  host=document.createElement('div');host.id='vinazon-collector-panel';host.style.cssText='position:fixed;right:18px;bottom:18px;z-index:2147483647;width:min(380px,calc(100vw - 30px));';
  const sh=host.attachShadow({mode:'open'});
  sh.innerHTML=`<style>*{box-sizing:border-box}section{font:14px/1.55 system-ui;color:#1d2940;background:#fff;border:1px solid #dbe1ee;border-radius:16px;box-shadow:0 12px 55px #0003;padding:20px}h2{font-size:18px;margin:0 0 12px}strong{font-size:24px;color:#5447ce}p{margin:8px 0;color:#55647b}button{border:1px solid #d6daeb;background:#f3f2fd;color:#4035a9;border-radius:8px;padding:9px 12px;cursor:pointer;margin:5px 4px 0 0;font:inherit}button.primary{background:#5447ce;color:#fff}button:disabled{opacity:.4;cursor:default}progress{width:100%;height:10px}small{color:#7a8498}#message{max-height:130px;overflow:auto}#sample{font-size:12px;max-height:70px;overflow:auto;border-left:3px solid #d9d5f6;padding-left:9px}</style><section><h2>Đánh giá sản phẩm Etsy</h2><strong id="count">0</strong><span id="goal"></span><progress id="progress"></progress><p id="message" role="status"></p><p id="sample"></p><div><button id="resume" hidden>Tiếp tục</button><button id="stop">Dừng</button><button id="csv" disabled>Tải CSV</button><button id="send" class="primary" disabled>Chuyển sang phân tích</button></div><p><small id="detail"></small></p></section>`;
  document.documentElement.append(host);ui=Object.fromEntries(['count','goal','progress','message','sample','resume','stop','csv','send','detail'].map(id=>[id,sh.getElementById(id)]));
  const version=document.createElement('small');version.textContent='Bản 1.0.3';sh.querySelector('h2').append(' · ',version);
  const diagnostics=document.createElement('button');diagnostics.textContent='Lưu thông tin lỗi';diagnostics.title='Lưu cấu trúc công khai của hộp đánh giá để kiểm tra khi Etsy đổi giao diện';sh.querySelector('section').append(diagnostics);diagnostics.onclick=()=>{
   const root=scope();let remaining=1600;
   function tree(e){if(--remaining<0)return null;return {tag:e.tagName,attrs:Object.fromEntries([...e.attributes].filter(a=>/^(id|class|role|aria-label|aria-selected|aria-current|data-review.*|data-transaction-id)$/.test(a.name)).map(a=>[a.name,a.value])),text:[...e.childNodes].filter(n=>n.nodeType===3).map(n=>n.textContent).join('').slice(0,1500),children:[...e.children].filter(c=>!['SCRIPT','STYLE','NOSCRIPT','IFRAME'].includes(c.tagName)).map(tree).filter(Boolean)};}
   const payload={version:'1.0.3',listing:job?.listing.id,scope:root===document?'not-found':tree(root),marked:bodyNodes(root).length,detected:job?read(root).length:0};
   const text=JSON.stringify(payload,null,2);
   let box=sh.getElementById('debugOutput');if(!box){box=document.createElement('textarea');box.id='debugOutput';box.readOnly=true;box.style.cssText='width:100%;height:100px;margin-top:10px;font:11px monospace;';sh.querySelector('section').append(box);}box.value=text;box.focus();box.select();ui.message.textContent='Thông tin lỗi đã hiện bên dưới. Nếu không có file tải xuống, bấm vào ô này, nhấn Ctrl+A rồi Ctrl+C để sao chép gửi lại.';
   const url=URL.createObjectURL(new Blob([text],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='etsy-collector-debug.json';document.documentElement.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),10000);
  };
  ui.stop.onclick=()=>{if(job){job.stop=true;ui.message.textContent='Đang dừng sau thao tác hiện tại…';}};
  ui.resume.onclick=()=>{if(job&&!job.running){job.stop=false;run();}};
  ui.csv.onclick=download;
  ui.send.onclick=async()=>{ui.send.disabled=true;try{const r=await chrome.runtime.sendMessage({type:'import',listing:job.listing,reviews:job.rows});if(!r.ok)throw Error(r.error);ui.message.textContent=`Đã chuyển ${r.count} đánh giá. Xem trước dữ liệu trong tab ứng dụng vừa mở.`;}catch(e){ui.message.textContent=e.message;}finally{ui.send.disabled=!job.rows.length;}};
 }
 function update(message){ui.count.textContent=job.rows.length;ui.goal.textContent=' / '+job.target+' đánh giá';ui.progress.max=job.target;ui.progress.value=job.rows.length;ui.message.textContent=message;ui.detail.textContent=`Sản phẩm ${job.listing.id} · Đã đọc ${job.pages} trang · ${job.rows.length<job.target?'Chưa đủ mục tiêu':'Đã đủ mục tiêu'}`;ui.csv.disabled=ui.send.disabled=!job.rows.length;ui.sample.textContent=job.rows.at(-1)?.feedback_text||'';}
 function challenge(){return !!document.querySelector('iframe[src*="captcha"], iframe[src*="datadome"], #captcha-container')||/verify you are human|confirm you are human|unusual traffic|slide.*verify|access to this page has been denied/i.test(document.body.innerText.slice(0,18000));}
 function buttons(root=document){return [...root.querySelectorAll('button,a,[role="tab"],[role="button"]')].filter(visible);}
 function label(e){return norm((e.innerText||e.textContent||'')+' '+(e.getAttribute('aria-label')||'')+' '+(e.getAttribute('title')||''));}
 function itemPane(){
  if(cachedPane?.isConnected&&visible(cachedPane))return cachedPane;
  // Find the smallest common container of the item heading, review cards and
  // pagination. Outer overlays may also contain the unchanged listing preview.
  const matches=e=>visible(e)&&e.textContent.length<180&&/^Reviews for this item(?:\s*\(|\s*$)/i.test(norm(e.innerText))&&norm(e.innerText).length<120&&!Array.from(e.children).some(c=>/^Reviews for this item(?:\s*\(|\s*$)/i.test(norm(c.innerText)));
  let headings=[...document.querySelectorAll('h1,h2,h3,h4,h5,[role="heading"]')].filter(matches);
  if(!headings.length)headings=[...document.querySelectorAll('strong,p,div,span')].filter(matches);
  const withinModal=headings.filter(h=>h.closest('[role="dialog"],dialog[open],.wt-overlay--is-open'));
  if(withinModal.length)headings=withinModal;
  for(const h of headings){
   for(let e=h.parentElement;e&&e!==document.body&&e!==document.documentElement;e=e.parentElement){
    if(!visible(e))continue;
    const controls=buttons(e),numbers=controls.filter(b=>/^\d+$/.test(norm(b.innerText)));
    const hasCards=bodyNodes(e).length>0||(norm(e.innerText).match(datePattern)||[]).length>=2;
    if(hasCards&&(numbers.length>=2||controls.some(b=>/next/i.test(label(b)))||e.querySelector('svg path[d^="M14.587 5.285"]'))){cachedPane=e;return e;}
   }
  }
  return null;
 }
 function dialog(){const pane=itemPane();if(pane)return pane;return [...document.querySelectorAll('[role="dialog"],dialog[open],.wt-overlay--is-open')].filter(e=>visible(e)&&(/review|đánh giá/i.test(e.innerText))).sort((a,b)=>a.querySelectorAll('*').length-b.querySelectorAll('*').length)[0];}
 function scope(){const modal=dialog();if(modal)return modal;return document.querySelector('#reviews')||document.querySelector('[data-reviews-section]')||document.querySelector('#reviews-section')||document;}
 function mountPanel(){const root=scope();const modal=root.closest?.('[role="dialog"],dialog[open],.wt-overlay--is-open')||root;if(modal!==document&&modal!==document.body&&host.parentElement!==modal)modal.append(host);}
 function activeShop(root){return [...root.querySelectorAll('[role="tab"][aria-selected="true"], [aria-current="page"]')].some(e=>allShop.test(label(e)));}
 const datePattern=/(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},?\s+\d{4}\b/gi;
 function dates(e){return norm(e.innerText).match(datePattern)||[];}
 function semanticReviews(root){
  // Etsy's newer item-review modal has plain text blocks, without review-preview IDs.
  // Identify one review by its date and exclude customer/variant/rating metadata.
  if(root===document||!itemLabel.test(root.innerText)||activeShop(root))return [];
  const anchors=[...root.querySelectorAll('time,span,p,div')].filter(e=>visible(e)&&dates(e).length===1&&norm(e.innerText).length<100&&!Array.from(e.children).some(c=>dates(c).length));
  const cards=new Set();
  for(const anchor of anchors){let card=anchor;while(card.parentElement&&card.parentElement!==root&&dates(card.parentElement).length===1)card=card.parentElement;if(card!==anchor)cards.add(card);}
  return [...cards].map(card=>{
   const date=dates(card)[0];const full=card.innerText;const dateAt=full.indexOf(date);if(dateAt<0)return null;
   const after=full.slice(dateAt+date.length);
   const lines=after.split(/\n+/).map(norm).filter(Boolean).filter(s=>!/^Choose\b[^:]*:|^(?:Selected )?(?:Size|Color|Colour|Background|Style|Material|Personalization|Variation)[^:]*:|^Item details\b|^Purchased item\b|^This item$|^Recommends$|^Doesn.t recommend$|^Helpful\b|^Report\b|^Translate\b|^See in original language\b|^Read more$|^Show more$|^\d+(?:\.\d+)?\s*(?:out of 5|stars?|star rating)|^[★☆\s\d|]+$/i.test(s));
   const text=norm(lines.join(' '));if(text.length<2)return null;
   return {card,text,date};
  }).filter(Boolean);
 }
 function bodyNodes(root){return [...root.querySelectorAll('[id^="review-preview-toggle-"], [data-review-text], .review-text, [itemprop="reviewBody"]')].filter(e=>visible(e)&&norm(e.textContent).length>0);}
 function read(root){
  const rows=[];
  const marked=bodyNodes(root);
  const entries=marked.length?marked.map(node=>({node})):semanticReviews(root);
  for(const entry of entries){
   const node=entry.node;
   const card=entry.card||node.closest('[data-review-id], [data-transaction-id], [data-review-region], .review-card, [itemprop="review"]')||node.closest('li')||node.parentElement?.parentElement;
   if(!card)continue;
   // If the card identifies a listing, it must match this product.
   const links=[...card.querySelectorAll('a[href*="/listing/"]')].map(a=>a.href.match(/\/listing\/(\d+)/)?.[1]).filter(Boolean);
   if(links.length&&!links.includes(job.listing.id))continue;
   const text=entry.text||norm(node.textContent);if(text.length<2)continue;
   const id=card.getAttribute('data-review-id')||card.getAttribute('data-transaction-id')||(node?.id?.startsWith('review-preview-toggle-')?node.id.replace('review-preview-toggle-',''):'');
   const date=entry.date||norm(card.querySelector('time')?.getAttribute('datetime')||card.querySelector('time')?.textContent||card.querySelector('[data-review-date]')?.textContent);
   const ratingNode=card.querySelector('[aria-label*="out of 5"], [aria-label*="5 stars"], [name="rating"], [itemprop="ratingValue"]');
   const rating=(ratingNode?.getAttribute('aria-label')||ratingNode?.getAttribute('value')||ratingNode?.getAttribute('content')||ratingNode?.textContent||'').match(/[1-5](?:\.\d)?/)?.[0]||'';
   const key=id?'id:'+id:'text:'+text+'|'+date;
   rows.push({key,review_id:id,feedback_text:text,rating,review_date:date,source_url:job.listing.url,listing_id:job.listing.id,source_page:job.pages+1});
  }
  return rows.filter((r,i,a)=>a.findIndex(x=>x.key===r.key)===i);
 }
 function signature(root){return read(root).map(r=>r.key).sort().join('\n');}
 async function waitFor(test,timeout=18000){const end=Date.now()+timeout;while(Date.now()<end){if(job.stop)return false;if(challenge())throw Error('Etsy yêu cầu xác minh. Tự hoàn tất xác minh trên trang rồi bấm Tiếp tục.');if(test())return true;await sleep(350);}return false;}
 async function selectItem(){
  let root=scope();
  if(itemPane()&&!activeShop(root)){job.confirmed=true;mountPanel();return;}
  if(dialog()&&!activeShop(root)&&[...root.querySelectorAll('h1,h2,h3,h4,[role="heading"]')].some(e=>itemLabel.test(norm(e.innerText)))){job.confirmed=true;return;}
  const tab=buttons(root).find(e=>itemLabel.test(label(e))&&e.getAttribute('role')==='tab');
  if(tab&&tab.getAttribute('aria-selected')!=='true'){tab.click();await sleep(1800);}
  if(tab&&tab.getAttribute('aria-selected')==='true'){job.confirmed=true;return;}
  const open=buttons().find(e=>/view all reviews for this item|xem tất cả.*đánh giá.*(?:sản phẩm|mặt hàng)/i.test(label(e)));
  if(open){open.scrollIntoView({block:'center'});open.click();if(!await waitFor(()=>!!dialog()||!!buttons(scope()).find(e=>itemLabel.test(label(e))&&e.getAttribute('aria-selected')==='true')))throw Error('Đã bấm mở đánh giá nhưng chưa thấy danh sách. Hãy mở “View all reviews for this item” rồi bấm Tiếp tục.');job.confirmed=true;await sleep(1200);}
  root=scope();
  if(activeShop(root))throw Error('Đang ở đánh giá toàn cửa hàng. Hãy chọn “Reviews for this item”, rồi bấm Tiếp tục.');
  if(!job.confirmed){const active=buttons(root).find(e=>itemLabel.test(label(e))&&e.getAttribute('aria-selected')==='true');if(active)job.confirmed=true;}
  if(!job.confirmed)throw Error('Chưa xác nhận được đánh giá riêng sản phẩm. Hãy mở “View all reviews for this item”, chọn “Reviews for this item” nếu có, rồi bấm Tiếp tục.');
 }
 function nextButton(root){
  const candidates=buttons(root).filter(e=>!e.disabled&&e.getAttribute('aria-disabled')!=='true'&&!e.classList.contains('disabled'));
  // Observed on the user's real Etsy item-review pagination. The icon has no text,
  // and its clickable wrapper need not be the final child of the pagination row.
  const arrowPath='M14.587 5.285A.5.5 0 0 0 13.88 5.285';
  for(const path of root.querySelectorAll('svg path[d]')){
   if(!path.getAttribute('d').trim().startsWith(arrowPath))continue;
   const control=path.closest('button,a,[role="button"]');
   if(control&&root.contains(control)&&candidates.includes(control)&&!control.closest('[aria-disabled="true"],fieldset[disabled]'))return control;
  }
  const explicit=candidates.find(e=>/^(next|next page|next reviews|trang tiếp|tiếp theo|next page of reviews)(\s|$)/i.test(label(e))||e.getAttribute('rel')==='next'||e.getAttribute('data-page')==='next');if(explicit)return explicit;
  const numeric=buttons(root).filter(e=>/^\d+$/.test(norm(e.innerText)));
  const current=numeric.find(e=>e.getAttribute('aria-current')==='page'||e.getAttribute('aria-current')==='true'||e.getAttribute('aria-pressed')==='true'||e.getAttribute('aria-selected')==='true');
  if(current){const next=numeric.find(e=>Number(norm(e.innerText))===Number(norm(current.innerText))+1&&candidates.includes(e));if(next)return next;}
  if(numeric.length>=2){let nav=numeric[0].parentElement;while(nav&&nav!==root&&!nav.contains(numeric.at(-1)))nav=nav.parentElement;if(nav&&nav!==root){const choices=buttons(nav),last=choices.at(-1);if(candidates.includes(last)&&!/\d/.test(norm(last.innerText))&&(/^[→›»]$/.test(norm(last.innerText))||last.querySelector('svg'))&&last!==choices[0])return last;}}
  return null;
 }
 async function run(){
  if(job.running)return;job.running=true;ui.resume.hidden=true;ui.stop.disabled=false;
  try{
   update('Đang mở đánh giá của sản phẩm…');
   if(challenge())throw Error('Etsy yêu cầu xác minh. Tự hoàn tất rồi bấm Tiếp tục.');
   await selectItem();
   mountPanel();
   if(!await waitFor(()=>read(scope()).length))throw Error('Không đọc được nội dung đánh giá. Hãy kiểm tra trang đã tải xong và bấm Tiếp tục.');
   while(!job.stop&&job.rows.length<job.target&&job.pages<100){
    const root=scope();mountPanel();if(root===document)throw Error('Không xác định được vùng đánh giá. Hãy mở hộp đánh giá của sản phẩm rồi bấm Tiếp tục.');
    if(activeShop(root))throw Error('Đã chuyển sang đánh giá cửa hàng. Hãy chọn lại đánh giá sản phẩm.');
    for(const b of buttons(root).filter(e=>/^(read more|show more|đọc thêm|xem thêm)$/i.test(label(e))))b.click();
    await sleep(250);
    const sig=signature(root);if(!sig)throw Error('Trang đánh giá chưa có nội dung đọc được.');
    for(const row of read(root)){if(job.seen.has(row.key))continue;job.seen.add(row.key);const {key,...data}=row;job.rows.push(data);if(job.rows.length===job.target)break;}
    if(!job.pageSignatures.has(sig)){job.pages++;job.pageSignatures.add(sig);}
    update('Đã đọc đánh giá. Đang kiểm tra trang tiếp theo…');
    if(job.rows.length>=job.target)break;
    const next=nextButton(root);if(!next){update(`Dừng ở ${job.rows.length} đánh giá: không thấy nút trang tiếp theo. Có thể đã hết đánh giá hoặc giao diện Etsy khác. Bạn có thể chuyển trang thủ công rồi bấm Tiếp tục.`);return;}
    update(`Đã lấy ${job.rows.length} đánh giá. Đang chuyển sang trang kế tiếp…`);
    await sleep(1800);if(job.stop)break;next.scrollIntoView({block:'center'});next.click();
    if(!await waitFor(()=>{const s=signature(scope());return s&&s!==sig;}))throw Error('Trang tiếp theo chưa tải hoặc không thay đổi. Hãy kiểm tra rồi bấm Tiếp tục.');
    await sleep(700);
    const nextSig=signature(scope());if(job.pageSignatures.has(nextSig))throw Error('Trang bị lặp. Đã dừng để không đếm trùng; hãy chuyển trang thủ công rồi bấm Tiếp tục.');
   }
   update(job.rows.length>=job.target?`Đã lấy đủ ${job.rows.length} đánh giá của sản phẩm. Bạn có thể tải CSV hoặc chuyển sang phân tích.`:`Đã dừng với ${job.rows.length} đánh giá. Có thể tiếp tục từ trang hiện tại.`);
  }catch(e){update(e.message);}finally{job.running=false;ui.stop.disabled=true;ui.resume.hidden=job.rows.length>=job.target;}
 }
 function download(){const columns=['feedback_text','review_id','rating','review_date','source_url','listing_id','source_page'];const cell=v=>'"'+String(v??'').replace(/^[=+@-]/,"'$&").replace(/"/g,'""')+'"';const csv='\uFEFF'+[columns.join(','),...job.rows.map(r=>columns.map(k=>cell(r[k])).join(','))].join('\r\n');const url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download=`etsy-${job.listing.id}-${job.rows.length}-reviews.csv`;a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);}
 globalThis.__vinazonCollector={version:'1.0.3',read,signature};
 chrome.runtime.onMessage.addListener((m,s,reply)=>{if(m.type!=='collect')return;if(job?.running){reply({ok:true});return;}if(!host)build();if(!job||job.listing.id!==m.listing.id)job={listing:m.listing,target:m.target,rows:[],seen:new Set(),pageSignatures:new Set(),pages:0,stop:false,confirmed:false,running:false};else{job.target=m.target;job.stop=false;}reply({ok:true});run();});
})();
