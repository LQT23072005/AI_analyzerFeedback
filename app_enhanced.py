from flask import Flask, render_template, request, jsonify, send_file, session, make_response
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from models import db, User
from config import Config
from database import DatabaseManager
import json
import os
import io
import base64
from datetime import datetime, timedelta
from collections import Counter
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns
from wordcloud import WordCloud
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from langdetect import detect
from googletrans import Translator
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
import re
from groq import Groq
import zipfile
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill

# Initialize NLTK
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')
try:
    nltk.data.find('corpora/stopwords')
except LookupError:
    nltk.download('stopwords')

app = Flask(__name__)
app.config['SECRET_KEY'] = Config.SECRET_KEY
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + Config.DATABASE_PATH
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

from product_improvement import install as install_product_reports
install_product_reports(app)
from web_review_import import install as install_web_reviews
install_web_reviews(app)
from database_admin import install as install_database_admin
install_database_admin(app, os.path.dirname(os.path.abspath(__file__)))

@app.before_request
def product_first_navigation():
    if request.method == 'GET' and request.path in ('/', '/dashboard', '/bulk_upload', '/analyze'):
        from flask import redirect
        return redirect('/product')

with app.app_context():
    db_manager = DatabaseManager()

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# ==================== AGENTIC AI WORKFLOW WITH PHI-LIKE PATTERN ====================

class FeedbackAnalysisAgent:
    """
    Phi-inspired Agentic AI Workflow for Customer Feedback Analysis
    This agent orchestrates multiple AI tasks: sentiment analysis, keyword extraction,
    emotion detection, response generation, and multilingual support.
    """
    
    def __init__(self, api_key=None):
        self.translator = Translator()
        # Initialize Groq client for free Llama models
        self.groq_api_key = api_key or os.getenv('GROQ_API_KEY')
        if self.groq_api_key:
            self.groq_client = Groq(api_key=self.groq_api_key)
            self.model_name = "openai/gpt-oss-120b"  
        else:
            self.groq_client = None
            print("Warning: GROQ_API_KEY not found. Using fallback analysis.")
        
    def detect_language(self, text):
        """Detect language of the feedback"""
        try:
            lang = detect(text)
            return lang
        except:
            return 'en'
    
    def translate_to_english(self, text, source_lang):
        """Translate feedback to English for analysis"""
        if source_lang == 'en':
            return text
        try:
            translation = self.translator.translate(text, src=source_lang, dest='en')
            return translation.text
        except:
            return text
    
    def analyze_sentiment_with_llm(self, text):
        """
        Use Groq LLM for advanced sentiment analysis
        Returns: dict with sentiment_label, sentiment_score, and breakdown
        """
        if not self.groq_client:
            # Fallback to simple analysis
            return {
                'sentiment_label': 'Neutral',
                'sentiment_score': 0.0,
                'positive_score': 0.33,
                'negative_score': 0.33,
                'neutral_score': 0.34
            }
        
        try:
            prompt = f"""Analyze the sentiment of this customer feedback. Respond ONLY with valid JSON.

Feedback: "{text}"

Provide your analysis in this exact JSON format:
{{
    "sentiment_label": "Positive" or "Negative" or "Neutral",
    "sentiment_score": a number between -1.0 and 1.0,
    "positive_score": probability 0-1,
    "negative_score": probability 0-1,
    "neutral_score": probability 0-1,
    "reasoning": "brief explanation"
}}"""

            response = self.groq_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=self.model_name,
                temperature=0.3,
                max_tokens=2048,
                response_format={"type": "json_object"}
            )
            
            result_text = response.choices[0].message.content.strip()
            # Extract JSON from response
            json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                return result
            else:
                raise ValueError("No JSON found in response")
                
        except Exception as e:
            print(f"LLM sentiment analysis error: {e}")
            return {
                'sentiment_label': 'Neutral',
                'sentiment_score': 0.0,
                'positive_score': 0.33,
                'negative_score': 0.33,
                'neutral_score': 0.34
            }
    
    def extract_keywords(self, text, top_n=10):
        """Extract top keywords from feedback"""
        try:
            # Tokenize and clean
            tokens = word_tokenize(text.lower())
            # Remove stopwords and non-alphabetic tokens
            stop_words = set(stopwords.words('english'))
            keywords = [word for word in tokens if word.isalpha() and word not in stop_words and len(word) > 3]
            # Get most common
            keyword_freq = Counter(keywords)
            return keyword_freq.most_common(top_n)
        except:
            return []
    
    def detect_emotion(self, text):
        """
        Detect emotions in feedback using LLM
        Returns: primary emotion and confidence
        """
        if not self.groq_client:
            return {'emotion': 'Neutral', 'confidence': 0.5}
        
        try:
            prompt = f"""Detect the primary emotion in this customer feedback. Choose from: Happy, Angry, Frustrated, Satisfied, Disappointed, Excited, Confused, Worried.

Feedback: "{text}"

Respond with valid JSON only:
{{
    "emotion": "the primary emotion",
    "confidence": a number 0-1,
    "secondary_emotions": ["list", "of", "other emotions"]
}}"""

            response = self.groq_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=self.model_name,
                temperature=0.3,
                max_tokens=2048,
                response_format={"type": "json_object"}
            )
            
            result_text = response.choices[0].message.content.strip()
            json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            else:
                raise ValueError("No JSON in response")
                
        except Exception as e:
            print(f"Emotion detection error: {e}")
            return {'emotion': 'Neutral', 'confidence': 0.5, 'secondary_emotions': []}
    
    def generate_business_insights(self, feedback_list):
        """Generate actionable business insights from multiple feedbacks"""
        if not self.groq_client or not feedback_list:
            return "No insights available. Please ensure API key is configured and feedback data exists."
        
        try:
            # Combine feedback texts
            combined_feedback = "\n".join([f"- {fb[:200]}" for fb in feedback_list[:15]])
            
            prompt = f"""You are a business analyst. Analyze these customer feedbacks and provide actionable insights.

Customer Feedbacks:
{combined_feedback}

Provide your analysis in the following JSON format:
{{
    "key_themes": ["theme1", "theme2", "theme3"],
    "recommendations": ["action1", "action2", "action3"],
    "priority_areas": ["priority1", "priority2"],
    "positive_highlights": ["highlight1", "highlight2"],
    "summary": "brief overall summary"
}}"""

            response = self.groq_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=self.model_name,
                temperature=0.5,
                max_tokens=800
            )
            
            result_text = response.choices[0].message.content.strip()
            json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            else:
                return {"summary": result_text}
                
        except Exception as e:
            print(f"Insights generation error: {e}")
            return {"summary": "Error generating insights. Please check API configuration."}
    
    def generate_response(self, sentiment, feedback_text):
        """Generate personalized customer response"""
        if not self.groq_client:
            templates = {
                'Positive': "Thank you for your wonderful feedback! We're thrilled to hear about your positive experience.",
                'Negative': "We sincerely apologize for your experience. We take your feedback seriously and will work to improve.",
                'Neutral': "Thank you for sharing your thoughts. We appreciate your feedback and will consider your suggestions."
            }
            return templates.get(sentiment, templates['Neutral'])
        
        try:
            prompt = f"""Generate a professional, empathetic customer service response to this {sentiment.lower()} feedback.

Customer Feedback: "{feedback_text}"

Requirements:
- Be professional and empathetic
- Address specific concerns mentioned
- Keep it concise (2-3 sentences)
- Provide next steps if appropriate

Response:"""

            response = self.groq_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=self.model_name,
                temperature=0.7,
                max_tokens=200
            )
            
            return response.choices[0].message.content.strip()
                
        except Exception as e:
            print(f"Response generation error: {e}")
            return "Thank you for your feedback. We value your input and will review it carefully."
    
    def comprehensive_analysis(self, feedback_text):
        """
        Perform comprehensive analysis on feedback
        This is the main orchestrator method (Phi-like agent workflow)
        """
        # Step 1: Language detection and translation
        detected_lang = self.detect_language(feedback_text)
        english_text = self.translate_to_english(feedback_text, detected_lang)
        
        # Step 2: Sentiment analysis
        sentiment_result = self.analyze_sentiment_with_llm(english_text)
        
        # Step 3: Keyword extraction
        keywords = self.extract_keywords(english_text)
        
        # Step 4: Emotion detection
        emotion_result = self.detect_emotion(english_text)
        
        # Step 5: Generate response
        response = self.generate_response(sentiment_result['sentiment_label'], english_text)
        
        return {
            'original_language': detected_lang,
            'english_text': english_text if detected_lang != 'en' else None,
            'sentiment': sentiment_result,
            'keywords': keywords,
            'emotion': emotion_result,
            'suggested_response': response
        }

# Initialize the agent
feedback_agent = FeedbackAnalysisAgent()

# ==================== HELPER FUNCTIONS ====================

def generate_wordcloud(feedback_texts):
    """Generate word cloud from feedback texts"""
    try:
        text = " ".join(feedback_texts)
        wordcloud = WordCloud(width=800, height=400, background_color='white',
                            colormap='viridis', max_words=50).generate(text)
        
        # Save to bytes
        img = io.BytesIO()
        plt.figure(figsize=(10, 5))
        plt.imshow(wordcloud, interpolation='bilinear')
        plt.axis('off')
        plt.tight_layout(pad=0)
        plt.savefig(img, format='png', bbox_inches='tight')
        plt.close()
        img.seek(0)
        
        # Convert to base64 for embedding in HTML
        img_base64 = base64.b64encode(img.getvalue()).decode()
        return f"data:image/png;base64,{img_base64}"
    except:
        return None

def export_to_csv(feedback_data):
    """Export feedback data to CSV"""
    df = pd.DataFrame([
        {
            'ID': fb['id'],
            'Customer': fb['customer_name'],
            'Email': fb['email'],
            'Feedback': fb['feedback_text'],
            'Rating': fb['rating'],
            'Sentiment': fb['sentiment_label'],
            'Sentiment Score': fb['sentiment_score'],
            'Date': fb['created_at']
        }
        for fb in feedback_data
    ])
    
    output = io.BytesIO()
    df.to_csv(output, index=False)
    output.seek(0)
    return output

def export_to_pdf(feedback_data, insights):
    """Export comprehensive feedback report to PDF with proper formatting"""
    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
    elements = []
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#6366f1'),
        spaceAfter=30,
        alignment=TA_CENTER
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.HexColor('#4338ca'),
        spaceAfter=12
    )
    
    # Title
    title = Paragraph("<b>Customer Feedback Analysis Report</b>", title_style)
    elements.append(title)
    elements.append(Spacer(1, 12))
    
    # Date
    date_text = Paragraph(f"<b>Generated:</b> {datetime.now().strftime('%B %d, %Y at %H:%M')}", styles['Normal'])
    elements.append(date_text)
    elements.append(Spacer(1, 20))
    
    # Summary statistics
    total = len(feedback_data)
    positive = sum(1 for fb in feedback_data if fb.get('sentiment_label') == 'Positive')
    negative = sum(1 for fb in feedback_data if fb.get('sentiment_label') == 'Negative')
    neutral = sum(1 for fb in feedback_data if fb.get('sentiment_label') == 'Neutral')
    
    avg_rating = sum(fb.get('rating', 0) for fb in feedback_data if fb.get('rating')) / max(sum(1 for fb in feedback_data if fb.get('rating')), 1)
    
    elements.append(Paragraph("<b>Executive Summary</b>", heading_style))
    
    summary_data = [
        ['Metric', 'Value', 'Percentage'],
        ['Total Feedbacks', str(total), '100%'],
        ['Positive', str(positive), f"{(positive/max(total,1)*100):.1f}%"],
        ['Negative', str(negative), f"{(negative/max(total,1)*100):.1f}%"],
        ['Neutral', str(neutral), f"{(neutral/max(total,1)*100):.1f}%"],
        ['Average Rating', f"{avg_rating:.2f}/5.0", '']
    ]
    
    summary_table = Table(summary_data, colWidths=[2.5*inch, 1.5*inch, 1.5*inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#6366f1')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f3f4f6')])
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 20))
    
    # Insights
    if insights and isinstance(insights, dict):
        elements.append(Paragraph("<b>AI-Generated Business Insights</b>", heading_style))
        elements.append(Spacer(1, 6))
        
        if 'key_themes' in insights and insights['key_themes']:
            elements.append(Paragraph("<b>Key Themes:</b>", styles['Normal']))
            for theme in insights['key_themes']:
                elements.append(Paragraph(f"• {theme}", styles['Normal']))
            elements.append(Spacer(1, 10))
        
        if 'recommendations' in insights and insights['recommendations']:
            elements.append(Paragraph("<b>Recommendations:</b>", styles['Normal']))
            for rec in insights['recommendations']:
                elements.append(Paragraph(f"• {rec}", styles['Normal']))
            elements.append(Spacer(1, 10))
        
        if 'priority_areas' in insights and insights['priority_areas']:
            elements.append(Paragraph("<b>Priority Areas:</b>", styles['Normal']))
            for priority in insights['priority_areas']:
                elements.append(Paragraph(f"• {priority}", styles['Normal']))
            elements.append(Spacer(1, 10))
        
        if 'summary' in insights:
            elements.append(Spacer(1, 10))
            elements.append(Paragraph("<b>Summary:</b>", styles['Normal']))
            elements.append(Paragraph(insights['summary'], styles['Normal']))
    
    elements.append(PageBreak())
    
    # Recent feedbacks detail
    elements.append(Paragraph("<b>Recent Feedback Details</b>", heading_style))
    elements.append(Spacer(1, 10))
    
    for i, fb in enumerate(feedback_data[:10], 1):
        fb_text = fb.get('feedback_text', '')[:200] + ('...' if len(fb.get('feedback_text', '')) > 200 else '')
        sentiment = fb.get('sentiment_label', 'N/A')
        customer = fb.get('customer_name', 'Anonymous')
        
        elements.append(Paragraph(f"<b>Feedback #{i} - {customer}</b>", styles['Normal']))
        elements.append(Paragraph(f"Sentiment: {sentiment} | Date: {fb.get('created_at', 'N/A')[:10]}", styles['Normal']))
        elements.append(Paragraph(f"{fb_text}", styles['Normal']))
        elements.append(Spacer(1, 10))
    
    try:
        doc.build(elements)
        output.seek(0)
        return output
    except Exception as e:
        print(f"PDF generation error: {e}")
        # Return a simple error PDF
        output = io.BytesIO()
        doc = SimpleDocTemplate(output, pagesize=letter)
        error_elements = [
            Paragraph("Error Generating PDF", styles['Title']),
            Spacer(1, 20),
            Paragraph(f"An error occurred: {str(e)}", styles['Normal'])
        ]
        doc.build(error_elements)
        output.seek(0)
        return output

# ==================== ROUTES ====================

@app.route('/')
def index():
    """Home page with overview statistics"""
    stats = db_manager.get_feedback_stats()
    recent_feedback = db_manager.get_all_feedback()[:5]
    
    # Get theme preference
    theme = session.get('theme', 'light')
    
    return render_template('index_enhanced.html', stats=stats, 
                         recent_feedback=recent_feedback, theme=theme)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        if User.query.filter((User.username == username) | (User.email == email)).first():
            return jsonify({'success': False, 'message': 'Username or email already exists'})
        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Registration successful'})
    return render_template('register_enhanced.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            return jsonify({'success': True, 'message': 'Login successful'})
        else:
            return jsonify({'success': False, 'message': 'Invalid credentials'})
    return render_template('login_enhanced.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return jsonify({'success': True, 'message': 'Logged out successfully'})

@app.route('/analyze', methods=['GET', 'POST'])
def analyze_feedback():
    """Main feedback analysis page with all features"""
    theme = session.get('theme', 'light')
    
    if request.method == 'POST':
        data = request.json
        feedback_text = data.get('feedback_text', '')
        customer_name = data.get('customer_name', '')
        email = data.get('email', '')
        rating = data.get('rating')
        
        if not feedback_text:
            return jsonify({'success': False, 'error': 'Feedback text is required'})
        
        # Perform comprehensive analysis using agent
        analysis = feedback_agent.comprehensive_analysis(feedback_text)
        
        # Store in database
        feedback_id = db_manager.insert_feedback(customer_name, email, feedback_text, rating)
        
        # Update with analysis results
        sentiment = analysis['sentiment']
        db_manager.update_feedback_sentiment(
            feedback_id,
            sentiment['sentiment_score'],
            sentiment['sentiment_label'],
            sentiment.get('positive_score', 0),
            sentiment.get('negative_score', 0),
            sentiment.get('neutral_score', 0)
        )
        
        # Store response
        db_manager.insert_response(feedback_id, analysis['suggested_response'], 'AI Generated')
        
        return jsonify({
            'success': True,
            'analysis': analysis,
            'feedback_id': feedback_id
        })
    
    return render_template('analyze_enhanced.html', theme=theme)

@app.route('/dashboard')
def dashboard():
    """Enhanced analytics dashboard"""
    theme = session.get('theme', 'light')
    
    # Get all feedback
    all_feedback = db_manager.get_all_feedback()
    
    # Get sentiment summary
    sentiment_summary = db_manager.get_sentiment_summary()
    
    # Generate word cloud
    feedback_texts = [fb['feedback_text'] for fb in all_feedback if fb['feedback_text']]
    wordcloud_img = generate_wordcloud(feedback_texts) if feedback_texts else None
    
    # Extract all keywords
    all_keywords = []
    for text in feedback_texts[:50]:  # Top 50 feedbacks
        keywords = feedback_agent.extract_keywords(text, top_n=5)
        all_keywords.extend([kw[0] for kw in keywords])
    
    keyword_freq = Counter(all_keywords).most_common(10)
    
    # Generate insights
    insights = feedback_agent.generate_business_insights(feedback_texts[:20])
    
    # Prepare chart data
    chart_data = {
        'sentiment_labels': [row['sentiment_label'] for row in sentiment_summary],
        'sentiment_counts': [row['count'] for row in sentiment_summary],
        'keywords': keyword_freq
    }
    
    # Emotion distribution (mock data for now - would need to analyze all feedback)
    emotion_data = {
        'Happy': 0,
        'Satisfied': 0,
        'Neutral': 0,
        'Frustrated': 0,
        'Angry': 0
    }
    
    stats = db_manager.get_feedback_stats()
    
    return render_template('dashboard_enhanced.html',
                         stats=stats,
                         feedback=all_feedback[:20],
                         sentiment_summary=sentiment_summary,
                         insights=insights,
                         chart_data=json.dumps(chart_data),
                         wordcloud_img=wordcloud_img,
                         keyword_freq=keyword_freq,
                         emotion_data=emotion_data,
                         theme=theme)

@app.route('/admin')
@login_required
def admin_dashboard():
    """Admin dashboard with comprehensive analytics"""
    theme = session.get('theme', 'light')
    
    if current_user.role != 'admin':
        return jsonify({'error': 'Access denied'}), 403
    
    stats = db_manager.get_feedback_stats()
    all_feedback = db_manager.get_all_feedback()
    sentiment_summary = db_manager.get_sentiment_summary()
    
    # Trend analysis (last 7 days)
    trends = []
    for i in range(7):
        date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
        count = sum(1 for fb in all_feedback if fb['created_at'].startswith(date))
        trends.append({'date': date, 'count': count})
    
    trends.reverse()
    
    return render_template('admin_dashboard.html',
                         stats=stats,
                         sentiment_summary=sentiment_summary,
                         trends=trends,
                         total_users=User.query.count(),
                         theme=theme)

@app.route('/export/<format>')
def export_data(format):
    """Export feedback data in CSV or PDF format"""
    all_feedback = db_manager.get_all_feedback()
    
    if format == 'csv':
        output = export_to_csv(all_feedback)
        return send_file(output, mimetype='text/csv',
                        as_attachment=True,
                        download_name=f'feedback_report_{datetime.now().strftime("%Y%m%d")}.csv')
    
    elif format == 'pdf':
        feedback_texts = [fb['feedback_text'] for fb in all_feedback if fb['feedback_text']]
        insights = feedback_agent.generate_business_insights(feedback_texts[:20])
        output = export_to_pdf(all_feedback, insights)
        return send_file(output, mimetype='application/pdf',
                        as_attachment=True,
                        download_name=f'feedback_report_{datetime.now().strftime("%Y%m%d")}.pdf')
    
    return jsonify({'error': 'Invalid format'}), 400

@app.route('/toggle_theme', methods=['POST'])
def toggle_theme():
    """Toggle dark/light theme"""
    current_theme = session.get('theme', 'light')
    new_theme = 'dark' if current_theme == 'light' else 'light'
    session['theme'] = new_theme
    return jsonify({'success': True, 'theme': new_theme})

@app.route('/api/feedback/<int:feedback_id>/response')
def get_feedback_response(feedback_id):
    """Get AI-generated response for specific feedback"""
    conn = db_manager.get_connection()
    try:
        cursor = conn.execute('SELECT * FROM feedback WHERE id = ?', (feedback_id,))
        feedback = cursor.fetchone()
        
        if feedback:
            response = feedback_agent.generate_response(
                feedback['sentiment_label'],
                feedback['feedback_text']
            )
            return jsonify({'success': True, 'response': response})
        else:
            return jsonify({'success': False, 'error': 'Feedback not found'})
    finally:
        conn.close()

@app.route('/api/stats')
def api_stats():
    """API endpoint for real-time statistics"""
    stats = db_manager.get_feedback_stats()
    sentiment_summary = db_manager.get_sentiment_summary()
    
    return jsonify({
        'stats': dict(stats),
        'sentiment_distribution': [dict(row) for row in sentiment_summary]
    })

# ==================== NEW ADVANCED FEATURES ====================

@app.route('/bulk_upload', methods=['GET', 'POST'])
def bulk_upload():
    """Bulk upload and analyze feedback from CSV/Excel files"""
    theme = session.get('theme', 'light')
    
    if request.method == 'POST':
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file uploaded'})
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'})
        
        filename = secure_filename(file.filename)
        file_ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
        
        if file_ext not in ['csv', 'xlsx', 'xls', 'txt', 'json']:
            return jsonify({'success': False, 'error': 'Unsupported file format. Use CSV, Excel, TXT, or JSON'})
        
        try:
            # Read file based on format
            if file_ext == 'csv':
                df = pd.read_csv(file)
            elif file_ext in ['xlsx', 'xls']:
                df = pd.read_excel(file)
            elif file_ext == 'txt':
                # Assume each line is a feedback
                content = file.read().decode('utf-8')
                lines = [line.strip() for line in content.split('\n') if line.strip()]
                df = pd.DataFrame({
                    'feedback_text': lines,
                    'customer_name': [''] * len(lines),
                    'email': [''] * len(lines),
                    'rating': [None] * len(lines)
                })
            elif file_ext == 'json':
                df = pd.read_json(file)
            
            # Process feedbacks
            processed_count = 0
            errors = []
            results = []
            
            # Detect column names flexibly
            feedback_col = None
            for col in df.columns:
                col_lower = col.lower()
                if any(word in col_lower for word in ['feedback', 'comment', 'review', 'text', 'message']):
                    feedback_col = col
                    break
            
            if feedback_col is None and 'web_scraper_order' in df.columns:
                # Scraper field numbering varies between exports. Inspect content.
                candidates = [col for col in df.columns if re.fullmatch(r'data\d*', str(col))]
                def review_score(col):
                    values = df[col].dropna().astype(str).head(100)
                    lengths = [len(re.findall(r'[^\W\d_]+', value)) for value in values
                               if not re.fullmatch(r'[A-Za-z]+ \d{1,2}, \d{4}', value.strip())
                               and not re.match(r'https?://', value)]
                    return sum(lengths) / max(len(values), 1)
                if candidates:
                    best = max(candidates, key=review_score)
                    if review_score(best) >= 3:
                        feedback_col = best

            selected_column = request.form.get('feedback_column', '').strip()
            if selected_column:
                if selected_column not in df.columns:
                    return jsonify({'success': False, 'error': 'Selected column does not exist'}), 400
                feedback_col = selected_column

            if request.form.get('preview') == '1':
                return jsonify({'success': True, 'columns': list(df.columns),
                                'suggested_column': feedback_col,
                                'samples': {str(col): [str(v)[:180] for v in df[col].dropna().head(3)] for col in df.columns}})

            if feedback_col is None:
                return jsonify({'success': False, 'error': 'Please select the column containing customer reviews.'}), 400
            
            name_col = next((col for col in df.columns if 'name' in col.lower()), None)
            if name_col is None and 'web_scraper_order' in df.columns and 'title' in df.columns:
                name_col = 'title'
            email_col = next((col for col in df.columns if 'email' in col.lower() or 'mail' in col.lower()), None)
            rating_col = next((col for col in df.columns if 'rating' in col.lower() or 'score' in col.lower()), None)
            
            for idx, row in df.iterrows():
                try:
                    feedback_text = str(row.get(feedback_col, ''))
                    if not feedback_text or feedback_text == 'nan' or len(feedback_text.strip()) < 5:
                        continue
                    
                    customer_name = str(row[name_col]) if name_col and pd.notna(row[name_col]) else ''
                    email = str(row[email_col]) if email_col and pd.notna(row[email_col]) else ''
                    rating = row.get(rating_col) if rating_col and pd.notna(row.get(rating_col)) else None
                    
                    # Analyze with AI
                    analysis = feedback_agent.comprehensive_analysis(feedback_text)
                    
                    # Store in database
                    feedback_id = db_manager.insert_feedback(customer_name, email, feedback_text, rating)
                    
                    sentiment = analysis['sentiment']
                    db_manager.update_feedback_sentiment(
                        feedback_id,
                        sentiment['sentiment_score'],
                        sentiment['sentiment_label'],
                        sentiment.get('positive_score', 0),
                        sentiment.get('negative_score', 0),
                        sentiment.get('neutral_score', 0)
                    )
                    
                    # Store response
                    db_manager.insert_response(feedback_id, analysis['suggested_response'], 'AI Generated')
                    
                    results.append({
                        'row': idx + 1,
                        'sentiment': sentiment['sentiment_label'],
                        'emotion': analysis['emotion']['emotion']
                    })
                    
                    processed_count += 1
                    
                except Exception as e:
                    errors.append(f"Row {idx + 1}: {str(e)}")
            
            return jsonify({
                'success': True,
                'processed': processed_count,
                'errors': errors,
                'results': results[:10]  # Show first 10
            })
            
        except Exception as e:
            return jsonify({'success': False, 'error': f'Error processing file: {str(e)}'})
    
    return render_template('bulk_upload.html', theme=theme)

@app.route('/export/excel')
def export_excel():
    """Export feedback data to Excel with formatting"""
    all_feedback = db_manager.get_all_feedback()
    
    # Create Excel workbook
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Feedback Analysis"
    
    # Headers
    headers = ['ID', 'Customer', 'Email', 'Feedback', 'Rating', 'Sentiment', 'Score', 'Emotion', 'Date']
    ws.append(headers)
    
    # Style headers
    header_fill = PatternFill(start_color='6366f1', end_color='6366f1', fill_type='solid')
    header_font = Font(bold=True, color='FFFFFF')
    
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center')
    
    # Add data
    for fb in all_feedback:
        ws.append([
            fb['id'],
            fb['customer_name'] or 'Anonymous',
            fb['email'] or '',
            fb['feedback_text'][:500],  # Limit length
            fb['rating'] or '',
            fb['sentiment_label'] or '',
            round(fb['sentiment_score'], 2) if fb['sentiment_score'] else '',
            '',  # Emotion placeholder
            fb['created_at'][:10] if fb['created_at'] else ''
        ])
    
    # Adjust column widths
    ws.column_dimensions['A'].width = 8
    ws.column_dimensions['B'].width = 20
    ws.column_dimensions['C'].width = 25
    ws.column_dimensions['D'].width = 60
    ws.column_dimensions['E'].width = 10
    ws.column_dimensions['F'].width = 12
    ws.column_dimensions['G'].width = 10
    ws.column_dimensions['H'].width = 15
    ws.column_dimensions['I'].width = 12
    
    # Save to bytes
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'feedback_analysis_{datetime.now().strftime("%Y%m%d")}.xlsx'
    )

@app.route('/advanced_analytics')
def advanced_analytics():
    """Advanced analytics page with comparison and trends"""
    theme = session.get('theme', 'light')
    
    all_feedback = db_manager.get_all_feedback()
    
    # Time-based analysis
    df = pd.DataFrame([dict(fb) for fb in all_feedback])
    if not df.empty and 'created_at' in df.columns:
        df['date'] = pd.to_datetime(df['created_at']).dt.date
        
        # Daily sentiment trends
        daily_sentiment = df.groupby(['date', 'sentiment_label']).size().unstack(fill_value=0)
        
        # Weekly comparison
        df['week'] = pd.to_datetime(df['created_at']).dt.isocalendar().week
        weekly_stats = df.groupby('week').agg({
            'id': 'count',
            'sentiment_score': 'mean',
            'rating': 'mean'
        }).to_dict()
    else:
        daily_sentiment = {}
        weekly_stats = {}
    
    # Customer segmentation (by sentiment patterns)
    frequent_customers = {}
    if not df.empty:
        customer_feedback = df.groupby('email').agg({
            'sentiment_label': lambda x: x.mode()[0] if len(x) > 0 else 'Neutral',
            'id': 'count'
        }).to_dict()
        frequent_customers = customer_feedback
    
    # Keywords trending over time
    recent_feedback = all_feedback[:50]
    recent_keywords = []
    for fb in recent_feedback:
        keywords = feedback_agent.extract_keywords(fb['feedback_text'], top_n=5)
        recent_keywords.extend([kw[0] for kw in keywords])
    
    trending_keywords = Counter(recent_keywords).most_common(15)
    
    return render_template('advanced_analytics.html',
                         theme=theme,
                         trending_keywords=trending_keywords,
                         weekly_stats=weekly_stats)

@app.route('/compare_periods')
def compare_periods():
    """Compare feedback between different time periods"""
    theme = session.get('theme', 'light')
    
    # Get date ranges
    start_date1 = request.args.get('start1', (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d'))
    end_date1 = request.args.get('end1', (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d'))
    start_date2 = request.args.get('start2', (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d'))
    end_date2 = request.args.get('end2', datetime.now().strftime('%Y-%m-%d'))
    
    all_feedback = db_manager.get_all_feedback()
    df = pd.DataFrame([dict(fb) for fb in all_feedback])
    
    if not df.empty:
        df['date'] = pd.to_datetime(df['created_at'])
        
        # Period 1
        period1 = df[(df['date'] >= start_date1) & (df['date'] <= end_date1)]
        period1_stats = {
            'count': len(period1),
            'avg_sentiment': period1['sentiment_score'].mean() if not period1.empty else 0,
            'positive': len(period1[period1['sentiment_label'] == 'Positive']),
            'negative': len(period1[period1['sentiment_label'] == 'Negative'])
        }
        
        # Period 2
        period2 = df[(df['date'] >= start_date2) & (df['date'] <= end_date2)]
        period2_stats = {
            'count': len(period2),
            'avg_sentiment': period2['sentiment_score'].mean() if not period2.empty else 0,
            'positive': len(period2[period2['sentiment_label'] == 'Positive']),
            'negative': len(period2[period2['sentiment_label'] == 'Negative'])
        }
        
        # Calculate changes
        changes = {
            'count_change': ((period2_stats['count'] - period1_stats['count']) / max(period1_stats['count'], 1)) * 100,
            'sentiment_change': period2_stats['avg_sentiment'] - period1_stats['avg_sentiment'],
            'positive_change': period2_stats['positive'] - period1_stats['positive'],
            'negative_change': period2_stats['negative'] - period1_stats['negative']
        }
    else:
        period1_stats = period2_stats = changes = {}
    
    return render_template('compare_periods.html',
                         theme=theme,
                         period1=period1_stats,
                         period2=period2_stats,
                         changes=changes)

@app.route('/search_feedback')
def search_feedback():
    """Advanced search with filters"""
    theme = session.get('theme', 'light')
    
    query = request.args.get('q', '')
    sentiment = request.args.get('sentiment', '')
    date_from = request.args.get('from', '')
    date_to = request.args.get('to', '')
    min_rating = request.args.get('min_rating', '')
    
    all_feedback = db_manager.get_all_feedback()
    results = []
    
    for fb in all_feedback:
        # Text search
        if query and query.lower() not in fb['feedback_text'].lower():
            continue
        
        # Sentiment filter
        if sentiment and fb['sentiment_label'] != sentiment:
            continue
        
        # Date filters
        if date_from and fb['created_at'] < date_from:
            continue
        if date_to and fb['created_at'] > date_to:
            continue
        
        # Rating filter
        if min_rating and (not fb['rating'] or fb['rating'] < int(min_rating)):
            continue
        
        results.append(fb)
    
    return jsonify({
        'success': True,
        'count': len(results),
        'results': results[:50]  # Limit to 50 results
    })

@app.route('/sentiment_heatmap')
def sentiment_heatmap():
    """Generate sentiment heatmap by day and hour"""
    all_feedback = db_manager.get_all_feedback()
    df = pd.DataFrame([dict(fb) for fb in all_feedback])
    
    if df.empty:
        return jsonify({'success': False, 'error': 'No data available'})
    
    df['datetime'] = pd.to_datetime(df['created_at'])
    df['day'] = df['datetime'].dt.day_name()
    df['hour'] = df['datetime'].dt.hour
    
    # Create heatmap data
    heatmap_data = df.groupby(['day', 'hour'])['sentiment_score'].mean().unstack(fill_value=0)
    
    # Convert to format for frontend
    heatmap_json = {
        'days': heatmap_data.index.tolist(),
        'hours': heatmap_data.columns.tolist(),
        'values': heatmap_data.values.tolist()
    }
    
    return jsonify({'success': True, 'data': heatmap_json})

@app.route('/customer_journey/<email>')
def customer_journey(email):
    """Track customer feedback journey over time"""
    conn = db_manager.get_connection()
    try:
        cursor = conn.execute('''
            SELECT * FROM feedback 
            WHERE email = ? 
            ORDER BY created_at ASC
        ''', (email,))
        feedbacks = [dict(row) for row in cursor.fetchall()]
        
        if not feedbacks:
            return jsonify({'success': False, 'error': 'No feedback found for this customer'})
        
        # Calculate journey metrics
        journey = {
            'total_feedback': len(feedbacks),
            'first_feedback': feedbacks[0]['created_at'],
            'latest_feedback': feedbacks[-1]['created_at'],
            'sentiment_trend': [fb['sentiment_label'] for fb in feedbacks],
            'avg_sentiment': sum(fb['sentiment_score'] or 0 for fb in feedbacks) / len(feedbacks),
            'feedbacks': feedbacks
        }
        
        return jsonify({'success': True, 'journey': journey})
    finally:
        conn.close()

@app.route('/auto_categorize')
def auto_categorize():
    """Automatically categorize feedback into topics"""
    all_feedback = db_manager.get_all_feedback()
    
    # Extract keywords from all feedback
    all_keywords = []
    for fb in all_feedback[:100]:  # Analyze top 100
        keywords = feedback_agent.extract_keywords(fb['feedback_text'], top_n=3)
        all_keywords.extend([kw[0] for kw in keywords])
    
    # Find common categories
    keyword_freq = Counter(all_keywords)
    categories = keyword_freq.most_common(10)
    
    # Categorize each feedback
    categorized = {}
    for category, _ in categories:
        categorized[category] = []
        for fb in all_feedback[:50]:
            if category.lower() in fb['feedback_text'].lower():
                categorized[category].append({
                    'id': fb['id'],
                    'text': fb['feedback_text'][:100],
                    'sentiment': fb['sentiment_label']
                })
    
    return jsonify({
        'success': True,
        'categories': categories,
        'categorized': categorized
    })

@app.route('/priority_feedbacks')
def priority_feedbacks():
    """Get high-priority feedbacks that need immediate attention"""
    all_feedback = db_manager.get_all_feedback()
    
    # Priority scoring: negative + low rating + recent
    priority_list = []
    
    for fb in all_feedback:
        priority_score = 0
        
        # Negative sentiment = high priority
        if fb['sentiment_label'] == 'Negative':
            priority_score += 50
        
        # Low rating = high priority
        if fb['rating'] and fb['rating'] <= 2:
            priority_score += 30
        
        # Recent = higher priority
        if fb['created_at']:
            days_ago = (datetime.now() - datetime.fromisoformat(fb['created_at'])).days
            if days_ago <= 1:
                priority_score += 20
            elif days_ago <= 3:
                priority_score += 10
        
        if priority_score >= 30:  # Threshold
            priority_list.append({
                **dict(fb),
                'priority_score': priority_score
            })
    
    # Sort by priority
    priority_list.sort(key=lambda x: x['priority_score'], reverse=True)
    
    return jsonify({
        'success': True,
        'high_priority_count': len(priority_list),
        'feedbacks': priority_list[:20]
    })

if __name__ == '__main__':
    # Create necessary directories
    os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
    
    # Create admin user if not exists
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(username='admin').first():
            admin = User(username='admin', email='admin@feedback.com', role='admin')
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            print("Admin user created: username='admin', password='admin123'")
    
    app.run(debug=True, port=5000)
