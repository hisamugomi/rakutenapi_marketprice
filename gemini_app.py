import google.generativeai as genai
import os
import sys

# 環境変数からAPIキーを取得
api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    print("Error: GEMINI_API_KEY environment variable is not set.")
    sys.exit(1)

genai.configure(api_key=api_key)
model = genai.GenerativeModel("gemini-2.0-flash")

print("--- Gemini Sandbox Ready (Isolated) ---")
print("Type 'exit' or 'quit' to stop.")

while True:
    try:
        user_input = input("\n> ")
        if user_input.lower() in ['exit', 'quit']:
            break
        
        response = model.generate_content(user_input)
        print("\nGemini:", response.text)
        
    except EOFError:
        break
    except Exception as e:
        print(f"An error occurred: {e}")