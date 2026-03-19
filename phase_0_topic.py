import os
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

# Initialize the Gemini client 
client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

def generate_trending_topic() -> str:
    """
    Acts as a YouTube Shorts strategist to brainstorm a highly lucrative, 
    viral business case study topic for the day.
    """
    print("🧠 [PHASE 0] Researching the most lucrative business topic of the day...")
    
    prompt = """
    You are an elite YouTube Shorts strategist prioritizing algorithmic virality and highly lucrative business content.
    Your goal is to brainstorm the SINGLE most intriguing, viral, and true business or entrepreneurship case study topic for today.
    
    Focus on areas that perform exceptionally well in short-form content:
    - Secret billion-dollar monopolies
    - Massive corporate failures or lawsuits
    - Genius psychological marketing tricks
    - How famous companies ACTUALLY make their money (like McDonald's and real estate)
    
    Provide ONLY the topic in 12 words or less. Do not include quotes, markdown formatting, or any extra text. Make it incredibly punchy.
    """
    
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=1.0, 
        ),
    )
    
    topic = response.text.strip().strip('"').strip("'")
    return topic

if __name__ == "__main__":
    topic = generate_trending_topic()
    print(f"\n🔥 Discovered Viral Topic: {topic}")
