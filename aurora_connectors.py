"""Simple local connectors for Aurora.

These are intentionally deterministic and low-risk: they only run when text from
Hermes/Twitch/bridge explicitly asks for a connector-style action. They do not
require paid APIs.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass
from typing import Any

DEFAULT_WEATHER_LOCATION = "Kendal, UK"


@dataclass(frozen=True)
class ConnectorResult:
    handled: bool
    prompt: str | None = None
    opened_url: str | None = None
    error: str | None = None


def _fetch_json(url: str, timeout: float = 8.0) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": "AuroraLive/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _extract_weather_location(text: str) -> str:
    lower = text.lower()
    # Examples:
    #   "check weather in Manchester"
    #   "what's the weather for Kendal UK"
    #   "open browser and check weather"
    match = re.search(r"\bweather\s+(?:in|for|at)\s+([^?.!,;]+)", text, flags=re.IGNORECASE)
    if match:
        location = match.group(1).strip()
        # Trim common trailing filler words from natural chat.
        location = re.sub(r"\b(please|now|today|mate|for me)\b.*$", "", location, flags=re.IGNORECASE).strip()
        if location:
            if location.lower() == "kendal":
                return "Kendal, UK"
            if location.lower() == "manchester":
                return "Manchester, UK"
            return location
    if "manchester" in lower:
        return "Manchester, UK"
    if "kendal" in lower:
        return "Kendal, UK"
    # User is near Kendal/Manchester; if no location is provided, default local.
    return DEFAULT_WEATHER_LOCATION


def _geocode_location(location: str) -> dict[str, Any]:
    clean = location.strip()
    name = clean.split(",", 1)[0].strip() or clean
    params = {"name": name, "count": 10, "language": "en", "format": "json"}
    if re.search(r"\b(uk|united kingdom|england|scotland|wales|britain|gb)\b", clean, flags=re.IGNORECASE):
        params["countryCode"] = "GB"
    geo_url = "https://geocoding-api.open-meteo.com/v1/search?" + urllib.parse.urlencode(params)
    geo = _fetch_json(geo_url)
    results = geo.get("results") or []
    if re.search(r"\b(uk|united kingdom|england|scotland|wales|britain|gb)\b", clean, flags=re.IGNORECASE):
        gb_results = [r for r in results if r.get("country_code") == "GB" or r.get("country") == "United Kingdom"]
        if gb_results:
            results = gb_results
    if not results and name != clean:
        fallback_url = "https://geocoding-api.open-meteo.com/v1/search?" + urllib.parse.urlencode(
            {"name": clean, "count": 1, "language": "en", "format": "json"}
        )
        geo = _fetch_json(fallback_url)
        results = geo.get("results") or []
    if not results:
        raise RuntimeError(f"I couldn't find weather coordinates for {location!r}.")
    return results[0]


def get_weather_summary(location: str = DEFAULT_WEATHER_LOCATION) -> str:
    place = _geocode_location(location)
    lat = place["latitude"]
    lon = place["longitude"]
    label = ", ".join(
        part for part in [place.get("name"), place.get("admin1"), place.get("country")] if part
    )

    weather_url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(
        {
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
            "timezone": "auto",
        }
    )
    weather = _fetch_json(weather_url)
    current = weather.get("current") or {}
    daily = weather.get("daily") or {}

    temp = current.get("temperature_2m")
    feels = current.get("apparent_temperature")
    wind = current.get("wind_speed_10m")
    rain = current.get("precipitation")
    max_temp = (daily.get("temperature_2m_max") or [None])[0]
    min_temp = (daily.get("temperature_2m_min") or [None])[0]
    rain_chance = (daily.get("precipitation_probability_max") or [None])[0]

    return (
        f"Weather for {label}: currently {temp}°C, feels like {feels}°C, "
        f"wind {wind} km/h, precipitation {rain} mm. Today's range is {min_temp}–{max_temp}°C"
        + (f" with up to {rain_chance}% precipitation probability." if rain_chance is not None else ".")
    )


def _fetch_text(url: str, timeout: float = 8.0) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "AuroraLive/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def _strip_tags(html: str) -> str:
    text = re.sub(r"<[^>]+>", "", html)
    return re.sub(r"\s+", " ", urllib.parse.unquote(text)).strip()


def web_search_summary(query: str, max_results: int = 4) -> str:
    """Free web search via DuckDuckGo (no API key, no quota).

    Tries the instant-answer API first, then scrapes DDG Lite for top results.
    Returns a compact text block for Gemini to summarize in-character.
    """
    query = (query or "").strip()
    if not query:
        raise RuntimeError("Empty search query.")

    lines: list[str] = []

    # 1) Instant answer (great for factual questions).
    try:
        ia = _fetch_json(
            "https://api.duckduckgo.com/?"
            + urllib.parse.urlencode({"q": query, "format": "json", "no_html": 1, "skip_disambig": 1})
        )
        abstract = (ia.get("AbstractText") or "").strip()
        if abstract:
            lines.append(f"Summary ({ia.get('AbstractSource') or 'DuckDuckGo'}): {abstract}")
    except Exception:
        pass

    # 2) Top organic results from DDG Lite (simple, stable HTML).
    try:
        html = _fetch_text("https://lite.duckduckgo.com/lite/?" + urllib.parse.urlencode({"q": query}))
        links = re.findall(r"<a[^>]+href=[\"']([^\"']+)[\"'][^>]*class=[\"']result-link[\"'][^>]*>(.*?)</a>", html, flags=re.IGNORECASE | re.DOTALL)
        snippets = re.findall(r"<td[^>]*class=[\"']result-snippet[\"'][^>]*>(.*?)</td>", html, flags=re.IGNORECASE | re.DOTALL)
        for i, (href, title_html) in enumerate(links[:max_results]):
            # DDG wraps result URLs in a redirect: //duckduckgo.com/l/?uddg=<real-url>
            m = re.search(r"[?&]uddg=([^&]+)", href)
            url = urllib.parse.unquote(m.group(1)) if m else href
            title = _strip_tags(title_html)
            snippet = _strip_tags(snippets[i]) if i < len(snippets) else ""
            lines.append(f"{i + 1}. {title} — {snippet} ({url})")
    except Exception as exc:
        if not lines:
            raise RuntimeError(f"Web search failed: {exc}") from exc

    if not lines:
        return f"No results found for {query!r}."
    return f"Web search results for {query!r}:\n" + "\n".join(lines)


DEFAULT_MARKET_SYMBOLS = [
    ("^GSPC", "S&P 500"),
    ("^IXIC", "Nasdaq"),
    ("^FTSE", "FTSE 100"),
    ("BTC-USD", "Bitcoin"),
    ("GBPUSD=X", "GBP/USD"),
]


def get_market_summary(symbols: list[tuple[str, str]] | None = None) -> str:
    """Free market brief via Yahoo Finance chart API (no key needed)."""
    lines = []
    for symbol, label in symbols or DEFAULT_MARKET_SYMBOLS:
        try:
            data = _fetch_json(
                f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}"
                "?range=1d&interval=1d"
            )
            meta = data["chart"]["result"][0]["meta"]
            price = meta.get("regularMarketPrice")
            prev = meta.get("chartPreviousClose") or meta.get("previousClose")
            if price is None or not prev:
                lines.append(f"{label}: no data")
                continue
            pct = (price - prev) / prev * 100
            arrow = "up" if pct >= 0 else "down"
            lines.append(f"{label}: {price:,.2f} ({arrow} {abs(pct):.2f}% today)")
        except Exception as exc:
            lines.append(f"{label}: unavailable ({exc})")
    return "Market brief: " + "; ".join(lines)


def open_browser_url(url: str) -> str:
    if not re.match(r"^https?://", url, flags=re.IGNORECASE):
        url = "https://" + url
    webbrowser.open(url, new=2)
    return url


def maybe_handle_connector(text: str) -> ConnectorResult:
    lower = text.lower()

    if "weather" in lower:
        location = _extract_weather_location(text)
        try:
            summary = get_weather_summary(location)
            if any(phrase in lower for phrase in ["open browser", "browser", "show me"]):
                query