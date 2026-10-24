"""Authenticated SQLite browser/editor; backups and optimistic row updates."""
import copy
import hashlib
import json
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from flask import Blueprint, current_app, jsonify, redirect, render_template, request, session, url_for
from flask_login import current_user

bp=Blueprint('database_admin',__name__)
DATABASES={'reports':('Báo cáo sản phẩm','product_reports.db'),'legacy':('Tài khoản và dữ liệu cũ','feedback_analyzer.db')}

def db_path(key):
    if key not in DATABASES:raise ValueError('Database không hợp lệ.')
    path=Path(current_app.config['DATABASE_ADMIN_PROJECT'])/DATABASES[key][1]
    if not path.is_file():raise ValueError('Chưa tìm thấy file database.')
    return path

def connect(key,write=False):
    path=db_path(key)
    conn=sqlite3.connect(path.as_uri()+('?mode=rw' if write else '?mode=ro'),uri=True,timeout=10)
    conn.row_factory=sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    return conn

def table_info(conn,name):
    if not conn.execute("SELECT 1 FROM sqlite_schema WHERE type='table' AND name=? AND name NOT LIKE 'sqlite_%'",(name,)).fetchone():raise ValueError('Bảng không hợp lệ.')
    return [dict(r) for r in conn.execute('PRAGMA table_info('+ident(name)+')')]

def ident(name):return '"'+name.replace('"','""')+'"'
def version(row):return hashlib.sha256(json.dumps(dict(row),sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()

def backup(key):
    path=db_path(key);folder=path.parent/'database_backups';folder.mkdir(exist_ok=True)
    destination=folder/(path.stem+'_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.db')
    source=connect(key)
    try:
        target=sqlite3.connect(str(destination))
        try:source.backup(target)
        finally:target.close()
    finally:source.close()
    return destination.name

def report_shape(report):
    result=copy.deepcopy(report)
    for k in ('filename','context','manual_updated_at','manual_updated_by'):result.pop(k,None)
    for g in result.get('groups',[]):
        for e in g.get('evidence',[]):e.pop('topic',None)
        for a in g.get('actions',[]):
            a.pop('action',None);a.pop('measurement',None)
            for e in a.get('evidence',[]):e.pop('topic',None)
    return result

def edited_report(old_text,new_text):
    try:old=json.loads(old_text);new=json.loads(new_text)
    except (ValueError,TypeError):raise ValueError('payload phải là JSON hợp lệ.') from None
    if not isinstance(new,dict):raise ValueError('payload phải là một đối tượng JSON.')
    if report_shape(old)!=report_shape(new):raise ValueError('Trong báo cáo chỉ được sửa filename, context, topic, action và measurement. Đánh giá gốc, trạng thái, trích dẫn và số liệu được giữ để tránh sai báo cáo.')
    if not isinstance(new.get('filename'),str) or not new['filename'].strip() or len(new['filename'])>255:raise ValueError('Tên file cần từ 1 đến 255 ký tự.')
    if not isinstance(new.get('context'),str) or len(new['context'])>2000:raise ValueError('Bối cảnh tối đa 2.000 ký tự.')
    for group in new.get('groups',[]):
        for e in group.get('evidence',[]):
            if not isinstance(e.get('topic'),str) or not e['topic'].strip():raise ValueError('Phát hiện không được để trống.')
        for action in group.get('actions',[]):
            for field in ('action','measurement'):
                if not isinstance(action.get(field),str) or not action[field].strip():raise ValueError('Đề xuất và cách kiểm chứng không được để trống.')
            for e in action.get('evidence',[]):
                if not isinstance(e.get('topic'),str) or not e['topic'].strip():raise ValueError('Phát hiện liên kết không được để trống.')
    new['manual_updated_at']=datetime.now(timezone.utc).isoformat()
    new['manual_updated_by']=str(current_user.get_id())
    return old,new

@bp.before_request
def authorize():
    if not current_user.is_authenticated:
        if request.path.startswith('/database/api/'):return jsonify(error='Hãy đăng nhập tài khoản admin.'),401
        return redirect(url_for('login',next='/database'))
    if getattr(current_user,'role',None)!='admin':return jsonify(error='Chỉ tài khoản admin được quản lý database.'),403
    if request.method in ('POST','DELETE','PUT','PATCH'):
        expected=session.get('database_csrf','')
        if not expected or not secrets.compare_digest(request.headers.get('X-Database-Token',''),expected):return jsonify(error='Phiên thao tác đã hết hạn. Tải lại trang database.'),403
        if not request.is_json:return jsonify(error='Yêu cầu phải ở dạng JSON.'),400

@bp.errorhandler(ValueError)
def invalid(exc):return jsonify(error=str(exc)),400
@bp.errorhandler(sqlite3.IntegrityError)
def constraint(exc):return jsonify(error='Không lưu được do trùng dữ liệu, thiếu trường bắt buộc hoặc còn bản ghi liên quan. Kiểm tra các giá trị và quan hệ bảng.'),409
@bp.errorhandler(sqlite3.OperationalError)
def busy(exc):return jsonify(error='Không truy cập được database lúc này. Kiểm tra ứng dụng khác đang giữ file hoặc thử lại sau.'),409

@bp.route('/database')
def home():
    session['database_csrf']=secrets.token_urlsafe(32)
    return render_template('database_admin.html',databases={k:v[0] for k,v in DATABASES.items()},token=session['database_csrf'],theme='light')

@bp.route('/database/api/tables')
def tables():
    conn=connect(request.args.get('db','reports'))
    try:names=[r[0] for r in conn.execute("SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    finally:conn.close()
    return jsonify(tables=names)

@bp.route('/database/api/rows')
def rows():
    key=request.args.get('db','reports');name=request.args.get('table','product_reports');page=max(1,int(request.args.get('page','1')))
    conn=connect(key)
    try:
        info=table_info(conn,name);total=conn.execute('SELECT COUNT(*) FROM '+ident(name)).fetchone()[0]
        page=min(page,max(1,(total+24)//25));pk=[c['name'] for c in info if c['pk']]
        data=conn.execute('SELECT * FROM '+ident(name)+' ORDER BY '+(ident(pk[0]) if len(pk)==1 else 'rowid')+' DESC LIMIT 25 OFFSET ?',((page-1)*25,)).fetchall()
        result=[]
        for row in data:
            item=dict(row);etag=version(row)
            if name=='user':item.pop('password_hash',None)
            summary={}
            if name=='product_reports':
                try:
                    p=json.loads(item['payload']);summary={k:p.get(k) for k in ('filename','status','processed','manual_updated_at')};summary['reviews']=len(p.get('reviews',[]))
                except (ValueError,TypeError):pass
            result.append({'values':item,'version':etag,'summary':summary})
    finally:conn.close()
    for c in info:c['readonly']=bool(c['pk']) or c['name']=='password_hash' or name=='product_reports' and c['name']!='payload'
    return jsonify(columns=info,rows=result,total=total,page=page,pages=max(1,(total+24)//25),primary_key=pk[0] if len(pk)==1 else None)

@bp.route('/database/api/row',methods=['POST','DELETE'])
def mutate():
    body=request.get_json()
    if not isinstance(body,dict):raise ValueError('Dữ liệu không hợp lệ.')
    key=body.get('db');name=body.get('table');row_id=body.get('id');deleting=request.method=='DELETE'
    if deleting and body.get('confirm')!='delete':raise ValueError('Cần xác nhận xóa bản ghi.')
    # Back up before the write transaction; the backup connection is always closed.
    backup_name=backup(key)
    conn=connect(key,write=True)
    try:
        conn.execute('BEGIN IMMEDIATE');info=table_info(conn,name);primary=[c['name'] for c in info if c['pk']]
        if len(primary)!=1:raise ValueError('Bảng này chưa hỗ trợ sửa/xóa từng bản ghi.')
        pk=primary[0];row=conn.execute('SELECT * FROM '+ident(name)+' WHERE '+ident(pk)+'=?',(row_id,)).fetchone()
        if row is None:return jsonify(error='Bản ghi đã bị xóa hoặc không tồn tại.'),404
        if body.get('version')!=version(row):return jsonify(error='Bản ghi vừa thay đổi. Tải lại bảng rồi sửa để tránh ghi đè dữ liệu mới.'),409
        if name=='user' and str(row[pk])==str(current_user.get_id()) and deleting:raise ValueError('Không thể xóa tài khoản admin đang đăng nhập.')
        if name=='product_reports' and json.loads(row['payload']).get('status')=='running':return jsonify(error='Báo cáo đang phân tích. Đợi hoàn tất rồi sửa/xóa.'),409
        if deleting:
            conn.execute('DELETE FROM '+ident(name)+' WHERE '+ident(pk)+'=?',(row_id,))
        else:
            values=body.get('values')
            if not isinstance(values,dict) or not values:raise ValueError('Chưa có trường cần cập nhật.')
            allowed={c['name'] for c in info if not c['pk'] and c['name']!='password_hash'}
            if name=='product_reports':allowed={'payload'}
            if not set(values)<=allowed:raise ValueError('Có trường không được phép chỉnh sửa.')
            if any(isinstance(v,(dict,list)) for v in values.values()):raise ValueError('Ô dữ liệu phải là văn bản, số hoặc NULL; JSON nhập dưới dạng văn bản.')
            if name=='user' and 'role' in values and values['role'] not in ('user','admin'):raise ValueError('Vai trò chỉ nhận user hoặc admin.')
            if name=='user' and str(row[pk])==str(current_user.get_id()) and values.get('role',row['role'])!='admin':raise ValueError('Không thể tự bỏ quyền admin của tài khoản đang đăng nhập.')
            if name=='product_reports':
                old,new=edited_report(row['payload'],values['payload']);values['payload']=json.dumps(new,ensure_ascii=False)
                if old.get('context')!=new.get('context'):values['fingerprint']=None
            assignments=', '.join(ident(k)+'=?' for k in values)
            conn.execute('UPDATE '+ident(name)+' SET '+assignments+' WHERE '+ident(pk)+'=?',tuple(values.values())+(row_id,))
        conn.commit()
        return jsonify(success=True,backup=backup_name,message='Đã xóa bản ghi.' if deleting else 'Đã lưu thay đổi. Thay đổi thủ công không gọi AI lại.')
    finally:conn.close()

def install(app,project):
    app.config['DATABASE_ADMIN_PROJECT']=str(Path(project).resolve())
    app.register_blueprint(bp)
