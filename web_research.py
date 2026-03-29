"""
Cinema Production Tool — Shared Web Research Module
Provides Tavily search and Firecrawl scraping as tools available to all LLM calls.
Reused from phase_0_director.py pattern, extracted for shared use.
"""

import os
import json
from dotenv import load_dotenv

load_dotenv()

# Initialize clients once
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


def search_web(query: str) -> str:
    """Search the web via Tavily for reference material."""
    print(f"   🔍 [WEB] Searching: {query}")
    client = _get_tavily()
    if not client:
        return "Tavily API not configured."
    try:
        res = client.search(query=query, search_depth="advanced", max_results=3)
        parts = []
        for r in res.get("results", []):
            parts.append(f"Title: {r['title']}\nContent: {r['content'][:500]}")
        return "\n\n".join(parts) if parts else "No results found."
    except Exception as e:
        return f"Search failed: {e}"


def scrape_url(url: str) -> str:
    """Scrape a URL via Firecrawl for detailed content."""
    print(f"   🕷️ [WEB] Scraping: {url}")
    app = _get_firecrawl()
    if not app:
        return "Firecrawl API not configured."
    try:
        res = app.scrape_url(url, params={"formats": ["markdown"]})
        return res.get("markdown", str(res))[:4000]
    except Exception as e:
        return f"Scrape failed: {e}"


# Tool definitions for GPT-4o tool-calling
TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "tavily_search",
            "description": "Search the live web for reference material, visual inspiration, cinematography techniques, location details, character archetypes, or any research needed to improve the output quality.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query"}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "firecrawl_scrape_url",
            "description": "Scrape a specific URL to get detailed content. Use when you found a useful link from search results and need the full page content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The URL to scrape"}
                },
                "required": ["url"],
            },
        },
    },
]


def handle_tool_call(tool_name: str, arguments: dict) -> str:
    """Execute a tool call and return the result string."""
    if tool_name == "tavily_search":
        return search_web(arguments.get("query", ""))
    elif tool_name == "firecrawl_scrape_url":
        return scrape_url(arguments.get("url", ""))
    return f"Unknown tool: {tool_name}"


def run_with_tools(
    client,
    model: str,
    system_prompt: str,
    user_prompt: str,
    max_tool_rounds: int = 3,
    response_format: dict = None,
) -> str:
    """
    Run a GPT-4o call with Tavily/Firecrawl tools available.
    Handles the tool-calling loop automatically.

    Args:
        client: OpenAI client instance
        model: Model name (e.g., "gpt-4o")
        system_prompt: System message with instructions to use tools when helpful
        user_prompt: User message
        max_tool_rounds: Max number of tool-calling rounds
        response_format: Optional response format (e.g., {"type": "json_object"})

    Returns:
        The final text response from the model.
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    tools_available = bool(_get_tavily() or _get_firecrawl())

    # Phase 1: Tool-calling rounds (no response_format — can't mix with tools)
    if tools_available:
        for round_num in range(max_tool_rounds):
            kwargs = {
                "model": model,
                "messages": messages,
                "tools": TOOLS_SCHEMA,
                "tool_choice": "auto",
            }

            try:
                response = client.chat.completions.create(**kwargs)
                msg = response.choices[0].message

                if msg.tool_calls:
                    messages.append(msg)
                    for tc in msg.tool_calls:
                        args = json.loads(tc.function.arguments)
                        result = handle_tool_call(tc.function.name, args)
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": result,
                        })
                    print(f"   🔄 Tool round {round_num + 1}: {len(msg.tool_calls)} tool call(s) processed")
                    continue
                else:
                    # Model chose not to use tools — proceed to final call
                    break
            except Exception as e:
                print(f"   ⚠️ Tool round failed: {e}")
                break

    # Phase 2: Final response call (with response_format if needed, no tools)
    kwargs = {"model": model, "messages": messages}
    if response_format:
        kwargs["response_format"] = response_format

    response = client.chat.completions.create(**kwargs)
    content = response.choices[0].message.content
    return content.strip() if content else ""
