import google.generativeai as genai
import os
from dotenv import load_dotenv

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"), transport="rest")

for model in genai.list_models():
    if "embed" in model.name.lower():
        print(model.name, model.supported_generation_methods)