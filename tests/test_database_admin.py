import copy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from flask import Flask
from flask_login import LoginManager,UserMixin
import database_admin as m

ROOT=Path(__file__).resolve().parents[1]/'templates'
class Person(UserMixin):
    def __init__(self,ident='1',role='admin'):self.id=ident;self.role=role

class AdminTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.project=Path(self.tmp.name)
        self.report={'id':'r1','filename':'reviews.csv','context':'test','created_at':'2026-10-23','status':'complete','processed':1,'total_rows':1,'skipped':{},'reviews':[{'id':1,'text':'A beautiful product.'}],'groups':[{'kind':'strength','category':'Thiết kế','severity':'low','count':1,'share':100,'priority':'Theo dõi','evidence':[{'review_id':1,'quote':'beautiful','topic':'Thiết kế đẹp'}],'actions':[{'action':'Duy trì thiết kế','measurement':'Theo dõi phản hồi'}]}]}
        with sqlite3.connect(str(self.project/'product_reports.db')) as c:
            c.execute('CREATE TABLE product_reports(id TEXT PRIMARY KEY,fingerprint TEXT UNIQUE,payload TEXT NOT NULL)');c.execute('INSERT INTO product_reports VALUES(?,?,?)',('r1','fp',json.dumps(self.report)))
        with sqlite3.connect(str(self.project/'feedback_analyzer.db')) as c:
            c.executescript("CREATE TABLE feedback(id INTEGER PRIMARY KEY,feedback_text TEXT NOT NULL);INSERT INTO feedback VALUES(1,'Original');CREATE TABLE responses(id INTEGER PRIMARY KEY,feedback_id INTEGER REFERENCES feedback(id));INSERT INTO responses VALUES(1,1);CREATE TABLE user(id INTEGER PRIMARY KEY,username TEXT,role TEXT,password_hash TEXT);INSERT INTO user VALUES(1,'admin','admin','SECRET_HASH');")
        self.app=Flask(__name__,template_folder=str(ROOT));self.app.secret_key='test'
        self.app.add_url_rule('/login','login',lambda:'login')
        self.login=LoginManager(self.app);self.login.user_loader(lambda ident:Person(ident,'user' if ident=='2' else 'admin'))
        m.install(self.app,self.project);self.client=self.app.test_client()
        with self.client.session_transaction() as s:s['_user_id']='1';s['_fresh']=True;s['database_csrf']='token'
        self.headers={'X-Database-Token':'token'}
    def tearDown(self):self.tmp.cleanup()
    def row(self,db='reports',table='product_reports'):
        result=self.client.get('/database/api/rows',query_string={'db':db,'table':table});self.assertEqual(result.status_code,200);return result.json['rows'][0]
    def post(self,row,values,db='reports',table='product_reports',method='POST',confirm=None):
        return self.client.open('/database/api/row',method=method,json={'db':db,'table':table,'id':row['values']['id'],'version':row['version'],'values':values,'confirm':confirm},headers=self.headers)
    def test_report_edit_preserves_sources_and_creates_backup(self):
        row=self.row();changed=copy.deepcopy(self.report);changed['filename']='Tên mới.csv';changed['groups'][0]['actions'][0]['action']='Kiểm tra thiết kế'
        result=self.post(row,{'payload':json.dumps(changed)});self.assertEqual(result.status_code,200)
        updated=json.loads(self.row()['values']['payload']);self.assertEqual(updated['filename'],'Tên mới.csv');self.assertEqual(updated['reviews'],self.report['reviews']);self.assertIn('manual_updated_at',updated)
        backup=self.project/'database_backups'/result.json['backup'];self.assertTrue(backup.is_file())
        with sqlite3.connect(str(backup)) as c:self.assertEqual(json.loads(c.execute('select payload from product_reports').fetchone()[0])['filename'],'reviews.csv')
    def test_delete_requires_confirmation_and_can_be_recovered_from_backup(self):
        row=self.row();self.assertEqual(self.post(row,{},method='DELETE').status_code,400)
        result=self.post(row,{},method='DELETE',confirm='delete');self.assertEqual(result.status_code,200)
        self.assertEqual(self.client.get('/database/api/rows').json['total'],0)
        with sqlite3.connect(str(self.project/'database_backups'/result.json['backup'])) as c:self.assertEqual(c.execute('select count(*) from product_reports').fetchone()[0],1)
    def test_protected_evidence_and_stale_updates_rejected(self):
        row=self.row();changed=copy.deepcopy(self.report);changed['reviews'][0]['text']='Edited source'
        self.assertEqual(self.post(row,{'payload':json.dumps(changed)}).status_code,400)
        with sqlite3.connect(str(self.project/'product_reports.db')) as c:c.execute("UPDATE product_reports SET fingerprint='changed'")
        self.assertEqual(self.post(row,{'payload':json.dumps(self.report)}).status_code,409)
    def test_auth_csrf_and_password_handling(self):
        row=self.row();self.assertEqual(self.client.post('/database/api/row',json={}).status_code,403)
        data=self.client.get('/database/api/rows?db=legacy&table=user').json
        self.assertNotIn('SECRET_HASH',json.dumps(data));user=data['rows'][0]
        self.assertEqual(self.post(user,{},db='legacy',table='user',method='DELETE',confirm='delete').status_code,400)
        with self.client.session_transaction() as s:s['_user_id']='2'
        self.assertEqual(self.client.get('/database/api/tables').status_code,403)
        with self.client.session_transaction() as s:s.clear()
        self.assertEqual(self.client.get('/database/api/tables').status_code,401)
    def test_foreign_key_and_generic_edit(self):
        row=self.row('legacy','feedback');result=self.post(row,{'feedback_text':'Updated'},db='legacy',table='feedback');self.assertEqual(result.status_code,200)
        row=self.row('legacy','feedback');self.assertEqual(self.post(row,{},db='legacy',table='feedback',method='DELETE',confirm='delete').status_code,409)

if __name__=='__main__':unittest.main(verbosity=2)
