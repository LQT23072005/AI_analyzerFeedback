"""Readable exports with explicit group/action/evidence relationships."""
import csv
import io
import re
import zipfile
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

KINDS = {'issue': 'Vấn đề cần cải thiện', 'request': 'Yêu cầu khách hàng', 'strength': 'Điểm mạnh cần duy trì'}
META = ['source_review_id', 'rating', 'review_date', 'source_url', 'listing_id', 'source_page', 'product_variant']

def line(value):
    return re.sub(r'\s+', ' ', str(value or '')).strip()

def safe_cell(value):
    if isinstance(value, str) and value.lstrip('\ufeff \t\r\n').startswith(('=', '+', '-', '@')):
        return "'" + value
    return value

def csv_bytes(headers, rows):
    stream = io.StringIO(newline='')
    writer = csv.writer(stream, lineterminator='\r\n')
    writer.writerow(headers)
    for row in rows:
        writer.writerow([safe_cell(line(v) if isinstance(v, str) else v) for v in row])
    return stream.getvalue().encode('utf-8-sig')

def view(report):
    reviews = {r['id']: r for r in report['reviews']}
    groups = sorted(report['groups'], key=lambda g: (
        {'issue': 0, 'request': 1, 'strength': 2}.get(g['kind'], 3),
        {'Cao': 0, 'Vừa': 1, 'Theo dõi': 2}.get(g['priority'], 3), -g['count'], g['category']))
    summary, actions, evidence = [], [], []
    for i, g in enumerate(groups, 1):
        gid = f'G{i:02}'
        findings = list(dict.fromkeys(e['topic'] for e in g['evidence']))
        priority = 'Duy trì' if g['kind'] == 'strength' else g['priority']
        group = {**g, 'code': gid, 'label': KINDS.get(g['kind'], g['kind']), 'priority': priority,
                 'findings': findings, 'actions': [], 'evidence': []}
        for e in g['evidence']:
            source = reviews.get(e['review_id'], {})
            record = {**e, 'group': gid, 'label': group['label'], 'category': g['category'],
                      'original': source.get('text', ''), **{key: source.get(key, '') for key in META}}
            evidence.append(record);group['evidence'].append(record)
        for item in g['actions']:
            linked = item.get('evidence', [])
            specific = bool(linked)
            record = {'code': f'A{len(actions)+1:03}', 'group': gid, 'label': group['label'],
                      'category': g['category'], 'priority': priority, 'action': item['action'],
                      'measurement': item['measurement'],
                      'finding': ' | '.join(dict.fromkeys(e['topic'] for e in linked)) if specific else ' | '.join(findings),
                      'review_ids': ', '.join(str(x) for x in sorted({e['review_id'] for e in linked})),
                      'evidence_scope': 'Trích dẫn riêng của hành động' if specific else f'Bằng chứng chung của nhóm {gid}',
                      'quotes': linked}
            group['actions'].append(record);actions.append(record)
        summary.append(group)
    try:
        created = datetime.fromisoformat(report.get('created_at', '').replace('Z', '+00:00')).astimezone(timezone(timedelta(hours=7))).strftime('%d/%m/%Y %H:%M (UTC+7)')
    except ValueError:
        created = report.get('created_at', '')
    links = list(dict.fromkeys(r.get('source_url') for r in reviews.values() if r.get('source_url')))
    return {'id': report['id'], 'filename': report.get('filename', ''), 'context': report.get('context', ''),
            'created': created, 'total': len(reviews), 'total_rows': report.get('total_rows', len(reviews)),
            'processed': report.get('processed', 0), 'skipped': report.get('skipped', {}),
            'manual_updated_at': report.get('manual_updated_at'),
            'summary': summary, 'actions': actions, 'evidence': evidence, 'reviews': list(reviews.values()),
            'issue_groups': sum(g['kind'] == 'issue' for g in groups),
            'request_groups': sum(g['kind'] == 'request' for g in groups),
            'strength_groups': sum(g['kind'] == 'strength' for g in groups),
            'has_metadata': any(r.get('rating') or r.get('review_date') or r.get('source_url') for r in reviews.values()),
            'has_legacy_links': any(not a['quotes'] for a in actions),
            'source_links': [u for u in links if urlsplit(u).scheme in ('http', 'https') and urlsplit(u).netloc]}

def files(report):
    d = view(report)
    metadata = [['Mã báo cáo', d['id']], ['File nguồn', d['filename']], ['Bối cảnh và mục tiêu', d['context']],
                ['Tạo lúc', d['created']], ['Tổng dòng đầu vào', d['total_rows']], ['Đánh giá hợp lệ', d['total']],
                ['Đánh giá đã phân tích', d['processed']], ['Nhóm vấn đề', d['issue_groups']],
                ['Nhóm yêu cầu', d['request_groups']], ['Nhóm điểm mạnh', d['strength_groups']],
                ['Cách đọc tỷ lệ', 'Số đánh giá duy nhất nhắc đến nhóm / số đánh giá hợp lệ. Một đánh giá có thể thuộc nhiều nhóm; không cộng các tỷ lệ.'],
                ['Hành động và chỉ tiêu', 'Đề xuất của AI cần doanh nghiệp duyệt; không phải kết quả cải tiến đã đo.'],
                ['Bằng chứng hành động cũ', 'Báo cáo cũ chỉ lưu bằng chứng cấp nhóm; không suy đoán trích dẫn riêng cho từng hành động.'],
                ['Ô thiếu dữ liệu', 'Để trống nếu nguồn không có hoặc báo cáo cũ chưa lưu. Không suy ra số sao từ lời khen.']]
    metadata.extend([['Số dòng bỏ qua: '+k, v] for k, v in d['skipped'].items()])
    overview = [[g['code'], g['label'], g['category'], g['priority'], g['count'], d['total'], g['share'],
                 ' | '.join(g['findings']), len(g['actions'])] for g in d['summary']]
    action_rows = [[a['code'], a['group'], a['label'], a['category'], a['priority'], a['finding'], a['action'],
                    a['measurement'], a['review_ids'], a['evidence_scope'], '', '', 'Chưa phân công'] for a in d['actions']]
    evidence_rows = [[e['group'], e['label'], e['category'], e['review_id'], e['topic'], e['quote'], e['original'],
                      e['rating'], e['review_date'], e['source_url'], e['source_review_id'], e['product_variant']] for e in d['evidence']]
    review_rows = [[r['id'], r['text'], r.get('rating',''), r.get('review_date',''), r.get('source_url',''),
                    r.get('listing_id',''), r.get('source_page',''), r.get('source_review_id',''), r.get('product_variant','')] for r in d['reviews']]
    return {
        '00_thong_tin_bao_cao.csv': csv_bytes(['Thông tin', 'Giá trị'], metadata),
        '01_tong_quan.csv': csv_bytes(['Mã nhóm','Loại phát hiện','Khía cạnh','Ưu tiên','Số đánh giá nhắc nhóm','Tổng đánh giá hợp lệ','Tỷ lệ nhắc nhóm (%)','Phát hiện chính','Số đề xuất'],overview),
        '02_ke_hoach_cai_thien.csv': csv_bytes(['Mã hành động','Mã nhóm','Loại phát hiện','Khía cạnh','Ưu tiên','Phát hiện liên quan','Hành động đề xuất','Cách kiểm chứng đề xuất','Dòng đánh giá liên quan','Phạm vi bằng chứng','Người phụ trách','Hạn thực hiện','Trạng thái'],action_rows),
        '03_bang_chung.csv': csv_bytes(['Mã nhóm','Loại phát hiện','Khía cạnh','Dòng đánh giá','Phát hiện','Trích dẫn nguyên văn','Toàn bộ lời đánh giá','Số sao từ nguồn','Ngày đánh giá từ nguồn','Link sản phẩm từ nguồn','Mã đánh giá từ nguồn','Biến thể sản phẩm'],evidence_rows),
        '04_danh_gia_goc.csv': csv_bytes(['Dòng đánh giá','Nội dung đầy đủ','Số sao từ nguồn','Ngày đánh giá từ nguồn','Link sản phẩm từ nguồn','Mã sản phẩm từ nguồn','Trang thu thập','Mã đánh giá từ nguồn','Biến thể sản phẩm'],review_rows)
    }

def package(report):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, content in files(report).items():z.writestr(name, content)
    return stream.getvalue()
