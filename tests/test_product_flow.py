import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from flask import Flask
from werkzeug.datastructures import FileStorage
import product_improvement as p
import report_exports
import web_review_import as bridge

ROOT = Path(__file__).resolve().parents[1]


class ProductTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.previous_db = p.DB_PATH
        p.DB_PATH = Path(self.tmp.name) / 'reports.db'
        self.app = Flask(__name__, template_folder=str(ROOT / 'templates'))
        self.app.register_blueprint(p.bp)
        self.client = self.app.test_client()
        self.reviews = [{'id': 1, 'text': 'The box arrived broken.'}, {'id': 2, 'text': 'Beautiful engraving.'}]
        self.observation = dict(review_id=1, quote='box arrived broken', kind='issue', category='Đóng gói',
                                topic='Hộp bị hỏng', severity='medium', action='Thử lớp bảo vệ hộp',
                                measurement='So sánh tỷ lệ hỏng ở đợt giao thử')

    def tearDown(self):
        p.DB_PATH = self.previous_db
        self.tmp.cleanup()

    def test_input_cleaning_and_source_metadata(self):
        raw = b'feedback_text,rating\nThe box arrived broken.,2\nThe box arrived broken.,2\n,5\nhttps://example.com,3\n'
        df = p.read_file(FileStorage(stream=io.BytesIO(raw), filename='demo.csv'))
        reviews, skipped = p.clean_reviews(df, 'feedback_text')
        self.assertEqual(len(reviews), 1)
        self.assertEqual(reviews[0]['rating'], '2')
        self.assertEqual(skipped, {'duplicate': 1, 'empty': 1, 'invalid': 1})

    def test_validation_and_unique_counts(self):
        observations = p.validate_observations({'observations': [self.observation]}, self.reviews)
        group = p.aggregate(observations * 2, 2)[0]
        self.assertEqual(group['count'], 1)
        self.assertEqual(group['share'], 50)
        for data in [[], None, {'observations': [{**self.observation, 'quote': 'invented defect'}]}]:
            with self.assertRaises(ValueError):
                p.validate_observations(data, self.reviews)

    def test_worker_and_exports_use_temporary_database(self):
        report = dict(id='demo', reviews=self.reviews, status='running', processed=0, context='Demo', groups=[],
                      error=None, skipped={}, total_rows=2, filename='demo.csv', column='feedback_text', created_at='2026-01-01')
        p.save(report, 'test-fingerprint')
        with patch.dict(p.os.environ, {'GROQ_API_KEY': 'test-only'}), patch.object(p, 'Groq'), \
                patch.object(p, 'call_json', return_value={'observations': [self.observation]}):
            p.LOCK.acquire()
            p.worker('demo')
        saved = p.load('demo')
        self.assertEqual(saved['status'], 'complete')
        self.assertEqual(saved['processed'], 2)
        self.assertEqual(len(report_exports.files(saved)), 5)
        self.assertEqual(self.client.get('/product/reports/demo/export').status_code, 200)
        self.assertEqual(self.client.get('/product/reports/demo/export-report').status_code, 200)
        self.assertTrue(report_exports.package(saved).startswith(b'PK'))
        report.update(status='running', processed=0)
        p.save(report)
        with patch.dict(p.os.environ, {'GROQ_API_KEY': 'test-only'}), patch.object(p, 'Groq'), \
                patch.object(p, 'call_json', side_effect=ValueError('Simulated failure')):
            p.LOCK.acquire()
            p.worker('demo')
        self.assertEqual(p.load('demo')['status'], 'failed')
        self.assertEqual(self.client.get('/product/reports/demo/export').status_code, 400)

    def test_csv_formula_escaping(self):
        data = report_exports.csv_bytes(['Text'], [['=SUM(1,2)']]).decode('utf-8-sig')
        self.assertIn("'=SUM(1,2)", data)


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        bridge.install(self.app)
        self.client = self.app.test_client()

    def test_import_and_download(self):
        payload = {'source_url': 'https://www.etsy.com/listing/1234567890/demo',
                   'reviews': [{'feedback_text': 'The engraving is beautiful.', 'rating': 5, 'listing_id': '1234567890'}]}
        response = self.client.post('/product/web-import', json=payload, headers={'X-Vinazon-Collector': '1'})
        self.assertEqual(response.status_code, 200)
        csv = self.client.get('/product/web-import/' + response.json['id'] + '/file')
        self.assertEqual(csv.status_code, 200)
        self.assertIn(b'The engraving is beautiful.', csv.data)

    def test_external_url_is_rejected(self):
        response = self.client.post('/product/web-import', json={'source_url': 'http://127.0.0.1/admin', 'reviews': []},
                                    headers={'X-Vinazon-Collector': '1'})
        self.assertEqual(response.status_code, 400)


if __name__ == '__main__':
    unittest.main()
