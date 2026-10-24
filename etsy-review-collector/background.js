function parseListing(value){const u=new URL(value);const m=u.pathname.match(/^\/(?:[a-z-]+\/)?listing\/(\d+)(?:\/|$)/);if(u.protocol!=='https:'||!['etsy.com','www.etsy.com'].includes(u.hostname)||u.username||u.password||u.port||!m)throw Error('Hãy nhập link sản phẩm Etsy dạng /listing/…');return {id:m[1],url:'https://www.etsy.com/listing/'+m[1]};}
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
function collectEtsyDiagnostic(){
 const norm=s=>String(s||'').replace(/\s+/g,' ').trim();
 const visible=e=>e.getClientRects().length>0&&getComputedStyle(e).visibility!=='hidden';
 function html(e){
  const clone=e.cloneNode(true);
  clone.querySelectorAll('script,style,noscript,iframe,input,textarea,#vinazon-collector-panel').forEach(n=>n.remove());
  for(const n of [clone,...clone.querySelectorAll('*')])for(const a of [...n.attributes])if(!/^(id|class|role|aria-[\w-]+|href|type|disabled|tabindex|value|data-(?:page|review[\w-]*|transaction-id|test[\w-]*|wt-overlay))$/.test(a.name))n.removeAttribute(a.name);
  return clone.outerHTML.slice(0,180000);
 }
 const heading=[...document.querySelectorAll('h1,h2,h3,h4,h5,div,span,p')].filter(e=>visible(e)&&e.textContent.length<160&&/^Reviews for this item(?:\s*\(|\s*$)/i.test(norm(e.innerText))&&!Array.from(e.children).some(c=>/^Reviews for this item(?:\s*\(|\s*$)/i.test(norm(c.innerText)))).slice(0,4);
 const containers=[];
 for(const h of heading){let e=h;for(let depth=0;e&&depth<5&&e!==document.body&&e!==document.documentElement;depth++,e=e.parentElement)containers.push({depth,tag:e.tagName,id:e.id,html:html(e)});}
 const arrows=[...document.querySelectorAll('svg path[d]')].filter(p=>p.getAttribute('d').startsWith('M14.587 5.285')).slice(0,20).map(p=>{let e=p;for(let i=0;i<4&&e.parentElement;i++)e=e.parentElement;return {visible:visible(e),html:html(e)};});
 return {version:chrome.runtime.getManifest().version,path:location.pathname,headingCount:heading.length,containers,arrows};
}
chrome.runtime.onMessage.addListener((message,sender,reply)=>{(async()=>{
 if(message.type==='diagnostic'){
  const [tab]=await chrome.tabs.query({active:true,currentWindow:true});parseListing(tab?.url||'');
  const [result]=await chrome.scripting.executeScript({target:{tabId:tab.id},func:collectEtsyDiagnostic});
  if(!result?.result)throw Error('Chưa đọc được trang. Giữ tab sản phẩm Etsy đang mở rồi thử lại.');
  return {ok:true,diagnostic:result.result};
 }
 if(message.type==='start'){
  const listing=parseListing(message.url),target=message.target;
  if(!Number.isInteger(target)||target<1||target>500)throw Error('Chọn từ 1 đến 500 đánh giá.');
  const [active]=await chrome.tabs.query({active:true,currentWindow:true});let tab;
  try{if(parseListing(active?.url||'').id===listing.id)tab=active;}catch{}
  if(!tab)tab=await chrome.tabs.create({url:listing.url});
  for(let i=0;i<60;i++){const t=await chrome.tabs.get(tab.id);if(t.status==='complete')break;await delay(500);}
  const [state]=await chrome.scripting.executeScript({target:{tabId:tab.id},func:()=>({loaded:!!globalThis.__vinazonCollector,version:globalThis.__vinazonCollector?.version})});
  if(state.result.loaded&&state.result.version!=='1.0.3')throw Error('Tab Etsy còn chạy mã tiện ích cũ. Nhấn F5 trên tab Etsy rồi mở tiện ích lại. Bản mới phải hiển thị 1.0.3.');
  await chrome.scripting.executeScript({target:{tabId:tab.id},files:['collector.js']});
  const result=await chrome.tabs.sendMessage(tab.id,{type:'collect',target,listing});
  return result;
 }
 if(message.type==='import'){
  if(!sender.tab||parseListing(sender.tab.url).id!==message.listing.id)throw Error('Chỉ chuyển dữ liệu từ tab sản phẩm Etsy tương ứng.');
  const response=await fetch('http://127.0.0.1:5000/product/web-import',{method:'POST',headers:{'Content-Type':'application/json','X-Vinazon-Collector':'1'},body:JSON.stringify({source_url:message.listing.url,reviews:message.reviews})});
  const data=await response.json();if(!response.ok||!data.success)throw Error(data.error||'Ứng dụng chưa nhận được dữ liệu.');
  await chrome.tabs.create({url:'http://127.0.0.1:5000/product?web_import='+encodeURIComponent(data.id)});
  return {ok:true,count:data.count};
 }
 throw Error('Yêu cầu không hợp lệ.');
})().then(reply).catch(e=>reply({ok:false,error:e.message.includes('Failed to fetch')?'Hãy chạy app_enhanced.py trước, rồi bấm chuyển lại.':e.message}));return true;});
