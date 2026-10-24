import sqlite3
import os
from datetime import datetime
from config import Config

class DatabaseManager:
    def __init__(self):
        self.db_path = Config.DATABASE_PATH
        self.init_database()
    
    def get_connection(self):
        """Get database connection with row factory"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def init_database(self):
        """Initialize database tables"""
        conn = self.get_connection()
        try:
            # Create feedback table
            conn.execute('''
                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_name TEXT,
                    email TEXT,
                    feedback_text TEXT NOT NULL,
                    rating INTEGER,
                    sentiment_score REAL,
                    sentiment_label TEXT,
                    positive_score REAL,
                    negative_score REAL,
                    neutral_score REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    processed_at TIMESTAMP
                )
            ''')
            
            # Create insights table
            conn.execute('''
                CREATE TABLE IF NOT EXISTS insights (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    insight_type TEXT NOT NULL,
                    insight_text TEXT NOT NULL,
                    confidence_score REAL,
                    feedback_count INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create responses table
            conn.execute('''
                CREATE TABLE IF NOT EXISTS responses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    feedback_id INTEGER,
                    response_text TEXT NOT NULL,
                    response_type TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (feedback_id) REFERENCES feedback (id)
                )
            ''')

            # Create PHI audit log table
            conn.execute('''
                CREATE TABLE IF NOT EXISTS phi_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    feedback_id INTEGER,
                    detected_phi TEXT,
                    action_taken TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (feedback_id) REFERENCES feedback (id)
                )
            ''')
            
            conn.commit()
        finally:
            conn.close()
    def insert_phi_audit(self, feedback_id, detected_phi, action_taken):
        """Insert PHI audit log entry"""
        conn = self.get_connection()
        try:
            conn.execute('''
                INSERT INTO phi_audit (feedback_id, detected_phi, action_taken)
                VALUES (?, ?, ?)
            ''', (feedback_id, detected_phi, action_taken))
            conn.commit()
        finally:
            conn.close()
    
    def insert_feedback(self, customer_name, email, feedback_text, rating=None):
        """Insert new feedback record"""
        conn = self.get_connection()
        try:
            cursor = conn.execute('''
                INSERT INTO feedback (customer_name, email, feedback_text, rating)
                VALUES (?, ?, ?, ?)
            ''', (customer_name, email, feedback_text, rating))
            feedback_id = cursor.lastrowid
            conn.commit()
            return feedback_id
        finally:
            conn.close()
    
    def update_feedback_sentiment(self, feedback_id, sentiment_score, sentiment_label, 
                                 positive_score, negative_score, neutral_score):
        """Update feedback with sentiment analysis results"""
        conn = self.get_connection()
        try:
            conn.execute('''
                UPDATE feedback 
                SET sentiment_score = ?, sentiment_label = ?, positive_score = ?, 
                    negative_score = ?, neutral_score = ?, processed_at = ?
                WHERE id = ?
            ''', (sentiment_score, sentiment_label, positive_score, negative_score, 
                  neutral_score, datetime.now(), feedback_id))
            conn.commit()
        finally:
            conn.close()
    
    def get_all_feedback(self):
        """Get all feedback records"""
        conn = self.get_connection()
        try:
            cursor = conn.execute('''
                SELECT * FROM feedback ORDER BY created_at DESC
            ''')
            return cursor.fetchall()
        finally:
            conn.close()
    
    def get_sentiment_summary(self):
        """Get sentiment distribution summary"""
        conn = self.get_connection()
        try:
            cursor = conn.execute('''
                SELECT 
                    sentiment_label,
                    COUNT(*) as count,
                    AVG(sentiment_score) as avg_score,
                    AVG(positive_score) as avg_positive,
                    AVG(negative_score) as avg_negative,
                    AVG(neutral_score) as avg_neutral
                FROM feedback 
                WHERE processed_at IS NOT NULL
                GROUP BY sentiment_label
            ''')
            return cursor.fetchall()
        finally:
            conn.close()
    
    def insert_insight(self, insight_type, insight_text, confidence_score, feedback_count):
        """Insert generated insight"""
        conn = self.get_connection()
        try:
            cursor = conn.execute('''
                INSERT INTO insights (insight_type, insight_text, confidence_score, feedback_count)
                VALUES (?, ?, ?, ?)
            ''', (insight_type, insight_text, confidence_score, feedback_count))
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()
    
    def get_latest_insights(self, limit=10):
        """Get latest insights"""
        conn = self.get_connection()
        try:
            cursor = conn.execute('''
                SELECT * FROM insights 
                ORDER BY created_at DESC 
                LIMIT ?
            ''', (limit,))
            return cursor.fetchall()
        finally:
            conn.close()
    
    def insert_response(self, feedback_id, response_text, response_type):
        """Insert generated response"""
        conn = self.get_connection()
        try:
            cursor = conn.execute('''
                INSERT INTO responses (feedback_id, response_text, response_type)
                VALUES (?, ?, ?)
            ''', (feedback_id, response_text, response_type))
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()
    
    def get_feedback_stats(self):
        """Get overall feedback statistics"""
        conn = self.get_connection()
        try:
            stats = {}
            
            # Total feedback count
            cursor = conn.execute('SELECT COUNT(*) as total FROM feedback')
            stats['total_feedback'] = cursor.fetchone()['total']
            
            # Processed feedback count
            cursor = conn.execute('SELECT COUNT(*) as processed FROM feedback WHERE processed_at IS NOT NULL')
            stats['processed_feedback'] = cursor.fetchone()['processed']
            
            # Average rating
            cursor = conn.execute('SELECT AVG(rating) as avg_rating FROM feedback WHERE rating IS NOT NULL')
            result = cursor.fetchone()
            stats['avg_rating'] = round(result['avg_rating'], 2) if result['avg_rating'] else 0
            
            # Recent feedback (last 7 days)
            cursor = conn.execute('''
                SELECT COUNT(*) as recent 
                FROM feedback 
                WHERE created_at >= datetime('now', '-7 days')
            ''')
            stats['recent_feedback'] = cursor.fetchone()['recent']
            
            return stats
        finally:
            conn.close()

# Initialize database manager
db_manager = DatabaseManager()
