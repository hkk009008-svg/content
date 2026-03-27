import json
import os
import urllib.request

try:
    import fal_client
    FAL_AVAILABLE = True
except ImportError:
    FAL_AVAILABLE = False

def auto_generate_roster():
    from dotenv import load_dotenv
    load_dotenv()
    
    print("==================================================")
    print("🎭 AUTONOMOUS VISION ROSTER SYNTHESIZER")
    print("==================================================")
    
    if not os.path.exists("characters.json"):
        print("❌ 'characters.json' not found! Cannot synthesize roster.")
        return

    os.makedirs("characters", exist_ok=True)
        
    with open("characters.json", "r") as f:
        char_db = json.load(f)
        
    if not FAL_AVAILABLE or not os.getenv("FAL_KEY"):
        print("❌ WARNING: 'fal_client' or 'FAL_KEY' missing in environment.")
        print("Please install requirements and set FAL_KEY to synthesize ultra-high-resolution faces.")
        return
        
    generated = 0
    for char_id, data in char_db.items():
        ref_path = data.get("reference_image")
        if not ref_path:
            continue
            
        if not os.path.exists(ref_path):
            print(f"\n🎬 [MISSING] Generating facial geometry for: '{data.get('name', char_id)}'")
            print(f"   ↳ Prompt: {data.get('description')}")
            
            # The FLUX-PRO ultra blueprint for perfectly mapped DeepFace geometry:
            prompt = f"Extreme high quality raw portrait photograph of {data.get('description')}. The subject is facing the camera directly forward. High contrast cinematic studio lighting, razor sharp 8k focus, photorealistic facial structure, entirely neutral simple dark background. Masterpiece."
            
            try:
                result = fal_client.subscribe(
                    "fal-ai/flux-pro/v1.1-ultra",
                    arguments={
                        "prompt": prompt,
                        "aspect_ratio": "16:9",
                        "output_format": "jpeg"
                    }
                )
                img_url = result['images'][0]['url']
                urllib.request.urlretrieve(img_url, ref_path)
                print(f"   ✅ Successfully mapped to disk: {ref_path}")
                generated += 1
            except Exception as e:
                print(f"   ⚠️ ERROR synthesizing {char_id}: {e}")
        else:
            print(f"✅ [LOCKED] Active reference found: {ref_path}")
            
    if generated > 0:
        print("\n🎉 ROSTER COMPLETE! The Vision Agent is now structurally locked.")
    else:
        print("\n✅ ROSTER COMPLETE! All character files were already fully populated.")

if __name__ == "__main__":
    auto_generate_roster()
