"""
NLTK Data Setup Script
Run this script once to download required NLTK data
"""

import nltk
import ssl

try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    pass
else:
    ssl._create_default_https_context = _create_unverified_https_context

print("Downloading NLTK data...")

try:
    nltk.download('punkt')
    print("Downloaded 'punkt'")
except:
    print("Failed to download 'punkt'")

try:
    nltk.download('stopwords')
    print("Downloaded 'stopwords'")
except:
    print("Failed to download 'stopwords'")

try:
    nltk.download('wordnet')
    print("Downloaded 'wordnet'")
except:
    print("Failed to download 'wordnet'")

print("\n NLTK setup complete!")
print("You can now run: python app_enhanced.py")
