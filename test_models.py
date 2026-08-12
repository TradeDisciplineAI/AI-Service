import os
import google.generativeai as genai
from dotenv import load_dotenv

# Load your new key
load_dotenv()
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

print("Checking Google's servers for your available models...\n")

try:
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            print(f"✅ Found working model name: {m.name}")
except Exception as e:
    print(f"❌ Error connecting to Google: {e}")