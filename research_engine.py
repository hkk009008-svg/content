"""
Cinema Production Tool — Research Engine
Uses Tavily (web search) and Firecrawl (URL scraping) to enhance
scene quality with real-world reference data.

Upgrades:
1. Scene Research — searches for cinematography techniques matching the mood/location
2. Location Reference — finds real photographs of described locations for visual grounding
3. Trend Research — discovers trending topics and audience preferences
4. Music Reference — finds real film scores matching the mood for better BGM prompts
"""

import os
import json
from typing import Optional, Dict, List
from dotenv import load_dotenv

load_dotenv()

# Initialize clients
_tavily_client = None
_firecrawl_app = None


def _get_tavily():
    global _tavily_client
    if _tavily_client is None and os.getenv("TAVILY_API_KEY"):
        try:
            from tavily import TavilyClient
            _tavily_client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
        except Exception:
            pass
    return _tavily_client


def _get_firecrawl():
    global _firecrawl_app
    if _firecrawl_app is None and os.getenv("FIRECRAWL_API_KEY"):
        try:
            from firecrawl import FirecrawlApp
            _firecrawl_app = FirecrawlApp(api_key=os.getenv("FIRECRAWL_API_KEY"))
        except Exception:
            pass
    return _firecrawl_app


def research_cinematography(mood: str, location: str, action: str) -> str:
    """
    Search for real cinematography techniques matching the scene's mood and setting.
    Returns a reference string to inject into the scene decomposer for better shot design.
    """
    tavily = _get_tavily()
    if not tavily:
        return ""

    query = f"cinematography techniques for {mood} mood scene in {location}, {action}, camera angles lighting"
    try:
        result = tavily.search(query=query, search_depth="basic", max_results=3)
        insights = []
        for r in result.get("results", [])[:3]:
            content = r.get("content", "")[:200]
            if content:
                insights.append(content)

        if insights:
            combined = " | ".join(insights)
            print(f"   [RESEARCH] Cinematography reference found ({len(insights)} sources)")
            return f"[RESEARCH REFERENCE]: {combined[:500]}"
        return ""
    except Exception as e:
        print(f"   [RESEARCH] Cinematography search failed: {e}")
        return ""


def research_location_visual(location_description: str) -> List[str]:
    """
    Search for real photographs of the described location for visual grounding.
    Returns list of image URLs that can be used as reference for image generation.
    """
    tavily = _get_tavily()
    if not tavily:
        return []

    query = f"{location_description} photograph high quality"
    try:
        result = tavily.search(query=query, search_depth="basic", max_results=5,
                               include_images=True)
        images = result.get("images", [])
        if images:
            print(f"   [RESEARCH] Found {len(images)} reference images for location")
        return images[:5]
    except Exception as e:
        print(f"   [RESEARCH] Location image search failed: {e}")
        return []


def research_music_reference(mood: str, scene_description: str) -> str:
    """
    Search for real film scores and music references matching the mood.
    Returns enhanced music prompt with real-world references.
    """
    tavily = _get_tavily()
    if not tavily:
        return ""

    query = f"film score {mood} mood music similar to, soundtrack reference, instruments tempo"
    try:
        result = tavily.search(query=query, search_depth="basic", max_results=3)
        refs = []
        for r in result.get("results", [])[:3]:
            content = r.get("content", "")[:150]
            if content:
                refs.append(content)

        if refs:
            print(f"   [RESEARCH] Music reference found ({len(refs)} sources)")
            return " | ".join(refs)[:300]
        return ""
    except Exception as e:
        print(f"   [RESEARCH] Music search failed: {e}")
        return ""


def scrape_technique_reference(url: str) -> str:
    """
    Scrape a specific URL (cinematography tutorial, film analysis) for technique details.
    Uses Firecrawl for clean markdown extraction.
    """
    firecrawl = _get_firecrawl()
    if not firecrawl:
        return ""

    try:
        result = firecrawl.scrape_url(url, params={"formats": ["markdown"]})
        content = result.get("markdown", "")
        if content:
            # Truncate to useful length
            return content[:1000]
        return ""
    except Exception as e:
        print(f"   [RESEARCH] Scrape failed: {e}")
        return ""


def research_trending_topics(category: str = "cinema") -> List[str]:
    """
    Research trending topics for content generation.
    """
    tavily = _get_tavily()
    if not tavily:
        return []

    query = f"trending {category} topics 2026, viral video ideas, popular themes"
    try:
        result = tavily.search(query=query, search_depth="advanced", max_results=5)
        topics = []
        for r in result.get("results", [])[:5]:
            title = r.get("title", "")
            if title:
                topics.append(title)
        return topics
    except Exception:
        return []
