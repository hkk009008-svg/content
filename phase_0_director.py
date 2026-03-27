import os
import json
from dotenv import load_dotenv
from openai import OpenAI
from tavily import TavilyClient
from firecrawl import FirecrawlApp

load_dotenv()

openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Initialize optional web tools if keys are present
tavily_client = None
if os.getenv("TAVILY_API_KEY"):
    try:
        tavily_client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
    except:
        pass

firecrawl_app = None
if os.getenv("FIRECRAWL_API_KEY"):
    try:
        firecrawl_app = FirecrawlApp(api_key=os.getenv("FIRECRAWL_API_KEY"))
    except:
        pass

def search_tavily(query: str) -> str:
    print(f"   🔍 [WEB] Searching Tavily for: {query}")
    if not tavily_client: return "Tavily API not configured."
    try:
        res = tavily_client.search(query=query, search_depth="advanced", max_results=3)
        results_str = ""
        for r in res.get("results", []):
            results_str += f"Title: {r['title']}\nContent: {r['content']}\n\n"
        return results_str
    except Exception as e:
        return f"Search failed: {e}"

def scrape_firecrawl(url: str) -> str:
    print(f"   🕷️ [WEB] Scraping URL via Firecrawl: {url}")
    if not firecrawl_app: return "Firecrawl API not configured."
    try:
        res = firecrawl_app.scrape_url(url, params={'formats': ['markdown']})
        return res.get('markdown', str(res))[:4000] # Limit tokens
    except Exception as e:
        return f"Scrape failed: {e}"

def generate_production_blueprint(ctx: dict) -> bool:
    topic = ctx["topic"]
    language = ctx.get("language", "English")
    print(f"\n🎬 [PHASE 0] Defining Master Artistic Vision via GPT-4o for: {topic}")
    
    system_prompt = f"""
    You are an elite, visionary A24-style art-house filmmaker and Master Director.
    Your job is to orchestrate the ENTIRE artistic, visual, and audio direction for a sweeping, emotional, deeply human cinematic short film about: "{topic}".
    
    CRITICAL INSTRUCTION: You MUST use the `tavily_search` tool to search the live web for profound artistic motifs, poetic visual metaphors, and human-centric emotional anchors related to the topic BEFORE finalizing your blueprint.
    
    After gathering your inspiration, you will formulate a masterpiece 'Production Blueprint'. You are moving AWAY from cold scientific documentaries and moving TOWARD deeply emotional art-house cinema. You must explore the freedom of expression of ordinary things in life—turning everyday reality into a masterpiece that echoes to the viewers. The footage must be immersive, balancing extreme psychological tension with breathtaking tranquility. Explore the meaning of life, love, family, and 'who am I' within the context of the topic.
    
    [CRITICAL AESTHETIC LAW]: DO NOT be afraid of blending worlds. Mix 2D, 3D animation, hand drawings, and raw cinematic camera footage. Be creatively fearless and express the emotion fully through whatever medium fits the psychological beat.
    
    Your blueprint must define an emotional masterpiece. Obey the following constraints:
    1. **Director's Vision**: Describe the profound emotional arc, the meaning, and the deep psychological human connection the script should follow. It must be an emotional ride into the director's mind.
    2. **Cinematography Rules**: Set the camera laws to capture both raw tension and gentle tranquility (e.g., "gentle handheld camera movements mixed with stark, locked-off wide shots of empty rooms").
    3. **Color Grading & Visual Aesthetics**: Define the exact color palette and lighting (e.g., "warm golden hour hues contrasting with deep, melancholic cinematic blues").
    4. **Sound Design & Music**: Define the musical instrumentation, specific Foley environments, and ambient sonic vibe.
    5. **The Hero Subject**: Formulate one definitive, highly specific 'Hero Object' or 'Subject' that physically anchors the emotion of the film (e.g., 'a worn-out pair of hands holding a fading photograph' or 'a single drop of rain on a foggy window'). This explicit subject MUST be the core visual anchor in every single shot to guarantee phenomenal visual continuity.
    
    Return your entire final command strictly adhering to the JSON schema once you have finished using the research tools.
    """
    
    tools = [
        {
            "type": "function",
            "function": {
                "name": "tavily_search",
                "description": "Searches the live internet for up-to-date visual references, aesthetic facts, and inspiration related to the topic.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The internet search query (e.g., 'aesthetic and visual inspiration for corporate real estate documentaries')."
                        }
                    },
                    "required": ["query"],
                    "additionalProperties": False
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "firecrawl_scrape_url",
                "description": "Scrapes and reads the raw markdown content of a specific URL obtained from your search results.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string"
                        }
                    },
                    "required": ["url"],
                    "additionalProperties": False
                }
            }
        }
    ]
    
    response_schema = {
        "name": "production_blueprint",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "director_vision": {"type": "string", "description": "The chief director's overarching vision for the emotional arc, narrative tension, and psychological impact of the video."},
                "cinematography_rules": {"type": "string", "description": "The exact overarching camera movement and framing philosophy for the video."},
                "color_grading_palette": {"type": "string", "description": "The explicit color palette, brightness curves, and lighting contrast."},
                "sound_design_and_music": {"type": "string", "description": "The musical orchestration, background audio soundscape, and SFX philosophy."},
                "hero_subject": {"type": "string", "description": "The exact physical 'Hero Object' or 'Subject' that will appear in every shot to ground the visual continuity. Must be highly descriptive."},
                "music_vibe": {
                    "type": "string",
                    "enum": ["suspense", "corporate", "gritty", "cyberpunk"],
                    "description": "Select the closest emotional music preset."
                }
            },
            "required": ["director_vision", "cinematography_rules", "color_grading_palette", "sound_design_and_music", "hero_subject", "music_vibe"],
            "additionalProperties": False
        }
    }
    
    messages = [{"role": "system", "content": system_prompt}]
    
    try:
        # Step 1: Tool loop
        max_tool_calls = 3
        for _ in range(max_tool_calls):
            response = openai_client.chat.completions.create(
                model="gpt-5.4-pro",
                messages=messages,
                tools=tools,
                tool_choice="auto"
            )
            
            response_message = response.choices[0].message
            if response_message.tool_calls:
                messages.append(response_message)
                for tool_call in response_message.tool_calls:
                    function_name = tool_call.function.name
                    function_args = json.loads(tool_call.function.arguments)
                    
                    if function_name == "tavily_search":
                        tool_result = search_tavily(function_args.get("query"))
                    elif function_name == "firecrawl_scrape_url":
                        tool_result = scrape_firecrawl(function_args.get("url"))
                    else:
                        tool_result = "Unknown tool."
                        
                    messages.append({
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": function_name,
                        "content": tool_result
                    })
            else:
                break
                
        # Step 2: Final JSON Generation
        print("   ↳ Research Complete. Director is formulating the Final Blueprint...")
        final_response = openai_client.chat.completions.create(
            model="gpt-5.4-pro",
            messages=messages,
            response_format={"type": "json_schema", "json_schema": response_schema}
        )
        
        blueprint = json.loads(final_response.choices[0].message.content)
        ctx["production_blueprint"] = blueprint
        ctx["music_vibe"] = blueprint.get("music_vibe", "suspense")
        
        print(f"   ↳ Art Direction: {blueprint['director_vision'][:60]}...")
        print(f"   ↳ Hero Subject: {blueprint['hero_subject']}")
        print(f"   ↳ Color Grade: {blueprint['color_grading_palette']}")
        return True
        
    except Exception as e:
        print(f"❌ Error generating Master Blueprint via GPT-4o: {e}")
        return False

if __name__ == "__main__":
    ctx = {"topic": "The hidden real estate empire of McDonald's"}
    if generate_production_blueprint(ctx):
        print("\nGenerated Blueprint Final Output:")
        print(json.dumps(ctx["production_blueprint"], indent=4))
