import os
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

# Initialize the Gemini client 
client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

def get_used_topics() -> list:
    if not os.path.exists("used_topics.txt"):
        return []
    with open("used_topics.txt", "r") as f:
        return [line.strip() for line in f.readlines() if line.strip()]

def save_used_topic(topic: str):
    with open("used_topics.txt", "a") as f:
        f.write(topic + "\n")

def generate_trending_topic() -> str:
    """
    Acts as a YouTube Shorts strategist to brainstorm a highly lucrative, 
    viral business case study topic for the day.
    """
    print("🧠 [PHASE 0] Researching the most lucrative business topic of the day...")
    
    used_topics = get_used_topics()
    avoid_clause = ""
    if used_topics:
        recent_used = used_topics[-50:]
        avoid_clause = f"\n    CRITICAL: You MUST NOT pick any of these previously used topics, nor anything remotely similar:\n" + "\n".join([f"    - {t}" for t in recent_used]) + "\n"

    prompt = f"""
    You are an elite YouTube Shorts strategist prioritizing algorithmic virality and highly lucrative business content.
    Your goal is to brainstorm the SINGLE most intriguing, viral, and true business or entrepreneurship case study topic for today.
    
    Focus on areas that perform exceptionally well in short-form content:
    - Secret billion-dollar monopolies
    - Massive corporate failures or lawsuits
    - Genius psychological marketing tricks
    - How famous companies ACTUALLY make their money (like McDonald's and real estate)
    {avoid_clause}
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
    save_used_topic(topic)
    return topic

if __name__ == "__main__":
    topic = generate_trending_topic()
    print(f"\n🔥 Discovered Viral Topic: {topic}")
