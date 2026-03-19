import os
import json
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

# Initialize the Gemini client 
# (Requires GOOGLE_API_KEY environment variable to be set)
client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

def generate_shorts_script(topic: str) -> dict:
    """
    Generates a highly-engaging 60-second YouTube Shorts script.
    Enforces a strict JSON response.
    """
    prompt = f"""
    You are an expert YouTube Shorts scriptwriter in the Business & Entrepreneurship niche. 
    Write a highly engaging, fast-paced 60-second case study about: "{topic}".
    
    Rules:
    1. Hook: Start with a contrarian, mind-blowing, or secretive business fact (under 3 seconds).
    2. Body: Explain the business model, the massive failure, or the genius strategy in 3 punchy bullet points. Use exact numbers or dollar amounts if possible.
    3. Call to Action: End by telling them to subscribe for more business breakdowns.
    4. Length: Strictly under 140 words to ensure a fast-paced voiceover.
    """
    
    # We define the expected JSON schema to guarantee the output structure
    response_schema = {
        "type": "OBJECT",
        "properties": {
            "title": {"type": "STRING", "description": "A catchy title for the video"},
            "hook": {"type": "STRING", "description": "The opening sentence"},
            "body_paragraphs": {
                "type": "ARRAY", 
                "items": {"type": "STRING"},
                "description": "3 punchy bullet points"
            },
            "call_to_action": {"type": "STRING", "description": "The ending sentence"},
            "pexels_search_keywords": {
                "type": "ARRAY", 
                "items": {"type": "STRING"},
                "description": "Keywords for finding b-roll footage"
            }
        },
        "required": ["title", "hook", "body_paragraphs", "call_to_action", "pexels_search_keywords"]
    }
    
    # Call the Gemini 2.5 Flash model
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=response_schema,
            temperature=0.7,
        ),
    )
    
    # Parse and return the JSON string into a Python dictionary
    return json.loads(response.text)

# --- Testing the Module ---
if __name__ == "__main__":
    # A classic, high-performing business case study topic:
    trending_topic = "How McDonald's actually makes its money from real estate, not selling burgers."
    
    print(f"Generating script for: {trending_topic}\n")
    
    try:
        final_script = generate_shorts_script(trending_topic)
        print(json.dumps(final_script, indent=4))
    except Exception as e:
        print(f"Error generating script: {e}")
        print("Make sure you have set the GOOGLE_API_KEY environment variable and installed google-genai.")
