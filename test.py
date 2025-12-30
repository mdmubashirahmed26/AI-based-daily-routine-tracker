import os

key = os.getenv('OPENAI_API_KEY')
if key:
    print(f"✅ API Key found: {key[:10]}...")
else:
    print("❌ API Key not found in environment")