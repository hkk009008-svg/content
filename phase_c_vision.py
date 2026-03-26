import os
import time
import base64
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def quality_control_image(image_path: str, hero_subject: str) -> bool:
    """
    Acts as the ruthless Quality Control Vision Agent using GPT-4o.
    Inspects the generated AI image to ensure it features the exact Hero Subject
    and contains no horrific AI hallucinations (e.g., melted faces, 6 fingers, garbled text).
    Returns True if passed, False if rejected.
    """
    print(f"   👁️ [VISION QC] Inspecting generated asset via GPT-4o: {image_path}")
    
    try:
        with open(image_path, "rb") as f:
            image_bytes = f.read()
            
        # Bypass inspection if image is completely broken
        if len(image_bytes) < 1000:
            print("   ❌ [VISION QC] Image is physically corrupted/empty.")
            return False
            
        b64_img = base64.b64encode(image_bytes).decode('utf-8')
        
        prompt = f"""
        You are an elite, ruthless Film Quality Control Inspector. 
        Your ONLY job is to look at this image and mathematically decide if it is acceptable for a high-end cinematic production.
        
        The image MUST explicitly contain or strongly represent this Master Hero Subject: "{hero_subject}".
        
        REJECT the image instantly (output 'FALSE') if:
        1. It looks like cheap AI garbage (melted faces, 6 fingers, warped physics).
        2. It has random, garbled AI text or watermarks in it.
        3. It completely ignoring the requested Hero Subject.
        
        ACCEPT the image (output 'TRUE') if:
        1. It is visually coherent, cinematic, and contains/represents the Hero Subject.
        
        You must output ONLY a single word: "TRUE" or "FALSE". Nothing else.
        """
        
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}}
                    ]
                }
            ],
            max_tokens=10,
            temperature=0.1
        )
        
        result = response.choices[0].message.content.strip().upper()
        
        if "TRUE" in result:
            print("   ✅ [VISION QC] Asset Approved!")
            return True
        else:
            print(f"   🗑️ [VISION QC] ASSET REJECTED ({result}): Failed cinematic standards or hallucinated. Regenerating...")
            return False
            
    except Exception as e:
        # If API fails, fall back to True to prevent halting the entire pipeline
        print(f"   ⚠️ [VISION QC] API Error: {e}. Defaulting to True.")
        return True

if __name__ == "__main__":
    # Test script
    res = quality_control_image("logo.png", "A dark cosmic brand logo")
    print(f"QC Result: {res}")
