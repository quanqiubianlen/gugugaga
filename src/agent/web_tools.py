"""Web search and fetch tools for the Agent.

Let the LLM search the web (DuckDuckGo) and fetch page content (requests + BeautifulSoup).
"""

import re
import urllib.parse
from typing import Any

import requests


# ---------------------------------------------------------------------------
# Web search via DuckDuckGo HTML (no API key needed)
# ---------------------------------------------------------------------------

def web_search(query: str, max_results: int = 5) -> str:
    """Search the web using DuckDuckGo and return formatted results."""
    if not query.strip():
        return "Error: empty search query."

    max_results = max(1, min(10, max_results))

    try:
        url = "https://html.duckduckgo.com/html/"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        }
        resp = requests.post(url, data={"q": query}, headers=headers, timeout=15)
        resp.raise_for_status()

        results = _parse_duckduckgo_html(resp.text)
        if not results:
            return f"No results found for: {query}"

        lines = [f"Web search results for '{query}':", ""]
        for i, r in enumerate(results[:max_results], 1):
            lines.append(f"{i}. {r['title']}")
            lines.append(f"   {r['snippet']}")
            lines.append(f"   URL: {r['url']}")
            lines.append("")

        return "\n".join(lines)

    except requests.ConnectionError:
        return "Error: cannot connect to DuckDuckGo. Check your internet connection."
    except requests.Timeout:
        return "Error: search request timed out."
    except Exception as exc:
        return f"Error searching the web: {exc}"


def _parse_duckduckgo_html(html: str) -> list[dict[str, str]]:
    """Extract search results from DuckDuckGo HTML response."""
    results: list[dict[str, str]] = []

    blocks = re.findall(
        r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
        html, re.DOTALL | re.IGNORECASE,
    )
    snippets = re.findall(
        r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
        html, re.DOTALL | re.IGNORECASE,
    )

    for i, (href, title) in enumerate(blocks):
        title_clean = re.sub(r"<[^>]+>", "", title).strip()
        snippet_clean = ""
        if i < len(snippets):
            snippet_clean = re.sub(r"<[^>]+>", "", snippets[i]).strip()

        url = _decode_duckduckgo_url(href)

        if title_clean and url:
            results.append({
                "title": title_clean,
                "url": url,
                "snippet": snippet_clean,
            })

    return results


def _decode_duckduckgo_url(href: str) -> str:
    """Extract the real URL from a DuckDuckGo redirect."""
    if "uddg=" in href:
        parsed = urllib.parse.urlparse(href)
        qs = urllib.parse.parse_qs(parsed.query)
        target = qs.get("uddg", [href])[0]
        return urllib.parse.unquote(target)
    return href


# ---------------------------------------------------------------------------
# Web page fetching
# ---------------------------------------------------------------------------

def web_fetch(url: str, max_chars: int = 8000) -> str:
    """Fetch a web page and extract its text content."""
    if not url.strip():
        return "Error: empty URL."

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        }
        resp = requests.get(url, headers=headers, timeout=20, allow_redirects=True)
        resp.raise_for_status()

        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)
        except ImportError:
            text = re.sub(r"<[^>]+>", " ", resp.text)
            text = re.sub(r"\s+", " ", text)

        text = re.sub(r"\n\s*\n", "\n\n", text)
        text = text.strip()

        if len(text) > max_chars:
            text = text[:max_chars] + f"\n\n... (truncated, {len(text)} total chars)"

        if not text:
            return f"Fetched {url} but no readable text content found."

        return f"Content from {url}:\n\n{text}"

    except requests.ConnectionError:
        return f"Error: cannot connect to {url}."
    except requests.Timeout:
        return f"Error: request to {url} timed out."
    except requests.HTTPError as exc:
        return f"Error: HTTP {exc.response.status_code} when fetching {url}."
    except Exception as exc:
        return f"Error fetching {url}: {exc}"


# ---------------------------------------------------------------------------
# Tool definitions for LLM function-calling
# ---------------------------------------------------------------------------

WEB_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search the web using DuckDuckGo. Returns results with titles, snippets, and URLs. "
                "Use for current events, recent information, or facts not in your training data."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (be specific and include relevant keywords).",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Number of results (1-10, default 5).",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": (
                "Fetch and extract text content from a web page. "
                "Use after web_search to read a specific page in detail."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL of the page to fetch.",
                    },
                },
                "required": ["url"],
            },
        },
    },
]


def execute_web_tool(name: str, arguments: dict[str, Any]) -> str:
    """Execute a web tool and return the result string."""
    if name == "web_search":
        return web_search(
            query=arguments.get("query", ""),
            max_results=arguments.get("max_results", 5),
        )
    elif name == "web_fetch":
        return web_fetch(url=arguments.get("url", ""))
    else:
        return f"Unknown web tool: {name}"

