"""Local browser collector bridge. Import only; AI runs after user review."""
import csv
import io
import re
import threading
import time
import uuid
from urllib.parse import urlsplit
from flask import Blueprint, jsonify, request, send_file, render_template

bp = Blueprint('web_reviews', __name__)
_cache = {}
_lock = threading.Lock()

def parse_payload(data):
    if not isinstance(data, dict):
        raise ValueError('Dữ liệu gửi lên không hợp lệ.')
    url = urlsplit(str(data.get('source_url', '')))
    match = re.fullmatch(r'/(?:[a-z-]+/)?listing/(\d+)(?:/[^/]*)?/?', url.path)
    if url.scheme != 'https' or url.hostname not in ('www.etsy.com', 'etsy.com') or url.username or url.password or url.port or not match:
        raise ValueError('Nguồn phải là đường link sản phẩm Etsy.')
    listing_id = match.group(1)
    canonical = 'https://www.etsy.com/listing/' + listing_id
    values = data.get('reviews')
    if not isinstance(values, list) or not 1 <= len(values) <= 500:
        raise ValueError('Cần từ 1 đến 500 đánh giá để chuyển dữ liệu.')
    reviews, seen = [], set()
    for item in values:
        if not isinstance(item, dict) or str(item.get('listing_id')) != listing_id:
            raise ValueError('Có đánh giá không thuộc sản phẩm đang thu thập.')
        text = item.get('feedback_text')
        if not isinstance(text, str) or not text.strip() or len(text) > 12000:
            raise ValueError('Nội dung đánh giá trống hoặc vượt quá 12.000 ký tự.')
        review_id = str(item.get('review_id', ''))[:150]
        date = str(item.get('review_date', ''))[:100]
        key = ('id', review_id) if review_id else ('text', text.strip(), date)
        if key in seen:
            continue
        seen.add(key)
        rating = str(item.get('rating', ''))
        if rating and not re.fullmatch(r'[1-5](?:\.0)?', rating):
            rating = ''
        reviews.append({'feedback_text': text.strip(), 'review_id': review_id, 'rating': rating,
                        'review_date': date, 'listing_id': listing_id, 'source_url': canonical,
                        'source_page': str(item.get('source_page', ''))[:10]})
    return listing_id, reviews

@bp.after_request
def cors(response):
    # Only the explicitly installed Chromium extension may read the import response.
    origin = request.headers.get('Origin', '')
    if request.path == '/product/web-import' and re.fullmatch(r'chrome-extension://[a-p]{32}', origin):
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Vary'] = 'Origin'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, X-Vinazon-Collector'
        response.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
    return response

@bp.route('/product/web-import', methods=['POST', 'OPTIONS'])
def receive():
    if request.method == 'OPTIONS':
        return '', 204
    if request.headers.get('X-Vinazon-Collector') != '1' or not request.is_json:
        return jsonify(success=False, error='Hãy chuyển dữ liệu từ tiện ích Etsy.'), 400
    if request.content_length is None or request.content_length > 8 * 1024 * 1024:
        return jsonify(success=False, error='Dữ liệu vượt quá 8 MB.'), 413
    try:
        listing, rows = parse_payload(request.get_json())
        token = uuid.uuid4().hex
        with _lock:
            now = time.time()
            for key in list(_cache):
                if now - _cache[key]['created'] > 3600:
                    del _cache[key]
            while len(_cache) >= 10:
                del _cache[next(iter(_cache))]
            _cache[token] = {'listing': listing, 'rows': rows, 'created': now}
        return jsonify(success=True, id=token, count=len(rows))
    except (ValueError, TypeError):
        return jsonify(success=False, error='Dữ liệu đánh giá hoặc nguồn sản phẩm không hợp lệ. Hãy thu thập lại từ tab sản phẩm.'), 400

@bp.route('/product/web-import/<token>/file')
def imported_file(token):
    with _lock:
        item = _cache.get(token)
        if not item or time.time() - item['created'] > 3600:
            return jsonify(error='Dữ liệu tạm đã hết hạn hoặc ứng dụng đã khởi động lại. Bấm Chuyển sang phân tích một lần nữa.'), 404
    stream = io.StringIO()
    columns = ['feedback_text', 'review_id', 'rating', 'review_date', 'source_url', 'listing_id', 'source_page']
    writer = csv.DictWriter(stream, fieldnames=columns)
    writer.writeheader()
    # Raw review text is preserved for analysis; this endpoint is loaded into the app, not opened as a spreadsheet.
    writer.writerows(item['rows'])
    response = send_file(io.BytesIO(stream.getvalue().encode('utf-8-sig')), mimetype='text/csv', as_attachment=True,
                        download_name='etsy-' + item['listing'] + '-web.csv')
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Listing-Id'] = item['listing']
    return response

@bp.route('/product/collector')
def instructions():
    return render_template('etsy_collector_help.html', theme='light')

def install(app):
    app.register_blueprint(bp)
