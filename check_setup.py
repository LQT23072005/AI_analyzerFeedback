"""
Setup Verification Script
Run this to check if everything is configured correctly
"""

import sys
import os
from pathlib import Path

def check_python_version():
    """Check Python version"""
    version = sys.version_info
    if version.major >= 3 and version.minor >= 8:
        print("✅ Python version: {}.{}.{} (OK)".format(version.major, version.minor, version.micro))
        return True
    else:
        print("❌ Python version: {}.{}.{} (Need 3.8+)".format(version.major, version.minor, version.micro))
        return False

def check_env_file():
    """Check if .env file exists and has API key"""
    if not os.path.exists('.env'):
        print("❌ .env file not found")
        print("   → Copy .env.example to .env and add your GROQ_API_KEY")
        return False
    
    with open('.env', 'r') as f:
        content = f.read()
        if 'GROQ_API_KEY' in content and 'your_groq_api_key_here' not in content:
            # Check if there's an actual key
            for line in content.split('\n'):
                if line.startswith('GROQ_API_KEY=') and len(line.split('=')[1].strip()) > 10:
                    print("✅ .env file configured with API key")
                    return True
            print("⚠️  .env file exists but GROQ_API_KEY seems empty")
            return False
        else:
            print("⚠️  .env file exists but GROQ_API_KEY not configured")
            print("   → Add your Groq API key to .env file")
            return False

def check_dependencies():
    """Check if required packages are installed"""
    required_packages = [
        'flask',
        'groq',
        'pandas',
        'matplotlib',
        'wordcloud',
        'langdetect',
        'googletrans',
        'nltk',
        'reportlab'
    ]
    
    missing = []
    for package in required_packages:
        try:
            __import__(package)
            print(f"✅ {package} installed")
        except ImportError:
            print(f"❌ {package} NOT installed")
            missing.append(package)
    
    if missing:
        print("\n⚠️  Missing packages detected!")
        print("   → Run: pip install -r requirements.txt")
        return False
    return True

def check_directories():
    """Check if required directories exist"""
    dirs = ['templates', 'uploads']
    all_exist = True
    
    for dir_name in dirs:
        if os.path.exists(dir_name):
            print(f"✅ {dir_name}/ directory exists")
        else:
            print(f"⚠️  {dir_name}/ directory missing (will be auto-created)")
    
    return True

def check_templates():
    """Check if template files exist"""
    required_templates = [
        'base_enhanced.html',
        'index_enhanced.html',
        'analyze_enhanced.html',
        'dashboard_enhanced.html',
        'login_enhanced.html',
        'register_enhanced.html',
        'admin_dashboard.html'
    ]
    
    missing = []
    for template in required_templates:
        template_path = os.path.join('templates', template)
        if os.path.exists(template_path):
            print(f"✅ {template}")
        else:
            print(f"❌ {template} NOT found")
            missing.append(template)
    
    if missing:
        print("\n⚠️  Missing template files!")
        return False
    return True

def main():
    print("=" * 60)
    print("🔍 AI Feedback Analyzer - Setup Check")
    print("=" * 60)
    print()
    
    checks = []
    
    print("📋 Checking Python Version...")
    checks.append(check_python_version())
    print()
    
    print("📋 Checking Environment Configuration...")
    checks.append(check_env_file())
    print()
    
    print("📋 Checking Dependencies...")
    checks.append(check_dependencies())
    print()
    
    print("📋 Checking Directories...")
    checks.append(check_directories())
    print()
    
    print("📋 Checking Template Files...")
    checks.append(check_templates())
    print()
    
    print("=" * 60)
    if all(checks):
        print("✅ All checks passed! You're ready to run the application.")
        print()
        print("🚀 Start the app with:")
        print("   python app_enhanced.py")
        print()
        print("   Then visit: http://localhost:5000")
    else:
        print("⚠️  Some checks failed. Please fix the issues above.")
        print()
        print("📚 See QUICKSTART.md for setup instructions")
    print("=" * 60)

if __name__ == '__main__':
    main()
