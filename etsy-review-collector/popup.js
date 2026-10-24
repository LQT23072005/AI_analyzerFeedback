const url=document.getElementById('url'),target=document.getElementById('target'),status=document.getElementById('status'),start=document.getElementById('start');
document.querySelector('h1').textContent='Lấy đánh giá Etsy · '+chrome.runtime.getManifest().version;
chrome.tabs.query({active:true,currentWindow:true}).then(([t])=>{if(/^https:\/\/(www\.)?etsy\.com\/(?:[a-z-]+\/)?listing\/\d+/.test(t?.url||''))url.value=t.url;});
start.onclick=async()=>{start.disabled=true;status.textContent='Đang mở trang và khởi động…';try{const r=await chrome.runtime.sendMessage({type:'start',url:url.value,target:Number(target.value)});if(!r.ok)throw Error(r.error);status.textContent='Đã bắt đầu. Xem bảng tiến độ ở góc phải trang Etsy.';}catch(e){status.textContent=e.message;}finally{start.disabled=false;}};
document.getElementById('diagnostic').onclick=async()=>{
 const button=document.getElementById('diagnostic');button.disabled=true;status.textContent='Đang đọc hộp đánh giá và nút phân trang…';
 try{const r=await chrome.runtime.sendMessage({type:'diagnostic'});if(!r.ok)throw Error(r.error);document.getElementById('diagnosticText').value=JSON.stringify(r.diagnostic,null,2);document.getElementById('diagnosticPanel').hidden=false;status.textContent='Đã lấy thông tin. Bấm Tải file thông tin lỗi rồi gửi file vào cuộc trò chuyện.';}
 catch(error){status.textContent='Không lấy được thông tin: '+error.message;}finally{button.disabled=false;}
};
document.getElementById('saveDiagnostic').onclick=()=>{const text=document.getElementById('diagnosticText').value;const a=document.createElement('a');a.href='data:application/json;charset=utf-8,'+encodeURIComponent(text);a.download='etsy-page-debug.json';document.body.append(a);a.click();a.remove();status.textContent='Đã yêu cầu tải etsy-page-debug.json. Kiểm tra Ctrl+J; nếu không có, sao chép nội dung trong ô để gửi lại.';};
