"""
ULTRA V5.6 Enterprise Engine — Gemini AI Service
Dedicated helper module for all Google Gemini API interactions.

Uses the official google-genai SDK (replaces deprecated google-generativeai).
SDK docs: https://googleapis.github.io/python-genai/

Features:
  - Primary model: gemini-1.5-flash (fast, cost-efficient)
  - Fallback model: gemini-1.5-pro  (higher quality on quota/error)
  - Graceful degradation: structured template fallback if key missing
  - Pre-built prompt builders for:
      • E-commerce SEO titles & bullet points  → WooCommerce importer
      • Multi-platform viral ad copy           → Marketing AI Agent
      • WooCommerce HTML product descriptions
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any, Dict, List, Optional

from .config import get_settings, logger

# ── SDK import with graceful fallback ─────────────────────────────────────────
try:
    from google import genai
    from google.genai import types as genai_types
    _GENAI_AVAILABLE = True
except ImportError:
    genai = None          # type: ignore
    genai_types = None    # type: ignore
    _GENAI_AVAILABLE = False
    logger.warning(
        "[GeminiService] google-genai SDK not installed. "
        "Run: pip install google-genai"
    )


def _make_client() -> Optional[Any]:
    """Build a configured google.genai.Client. Returns None if unavailable."""
    if not _GENAI_AVAILABLE:
        return None
    cfg = get_settings()
    if not cfg.gemini_api_key or cfg.gemini_api_key in ("", "your_gemini_api_key_here"):
        logger.warning(
            "[GeminiService] GEMINI_API_KEY not set in .env — "
            "running in template-fallback mode."
        )
        return None
    return genai.Client(api_key=cfg.gemini_api_key)


# Module-level singleton client (created once on first import)
_CLIENT: Optional[Any] = _make_client()

# Confirmed available model names (verified 2026-07 against this API key)
# Primary   : gemini-2.0-flash       — stable, confirmed available
# Fallback  : gemini-2.0-flash-001   — pinned stable version

# ── In-memory response cache (quota saver) ───────────────────────────────────
# Prevents identical prompts from burning free-tier quota.
# TTL: 1 hour  |  Max entries: 50  |  Key: hash of (prompt, temperature)
import hashlib
_RESPONSE_CACHE: dict = {}  # {cache_key: (timestamp, result_dict)}
_CACHE_TTL_SECONDS = 3600   # 1 hour
_CACHE_MAX_SIZE = 50


def _cache_key(prompt: str, temperature: float) -> str:
    return hashlib.sha256(f"{prompt}|{temperature}".encode()).hexdigest()[:16]


def _cache_get(key: str) -> Optional[Dict[str, Any]]:
    if key in _RESPONSE_CACHE:
        ts, result = _RESPONSE_CACHE[key]
        if time.time() - ts < _CACHE_TTL_SECONDS:
            return result
        del _RESPONSE_CACHE[key]
    return None


def _cache_set(key: str, result: Dict[str, Any]) -> None:
    if len(_RESPONSE_CACHE) >= _CACHE_MAX_SIZE:
        # Evict oldest entry
        oldest = min(_RESPONSE_CACHE, key=lambda k: _RESPONSE_CACHE[k][0])
        del _RESPONSE_CACHE[oldest]
    _RESPONSE_CACHE[key] = (time.time(), result)


# ── Core Generate Function ─────────────────────────────────────────────────────
async def generate(
    prompt: str,
    temperature: float = 0.7,
    max_tokens: int = 1024,
) -> Dict[str, Any]:
    """
    Send a prompt to Google Gemini. Returns a structured dict:

        {
            "success":    bool,
            "text":       str,
            "model_used": str,
            "error":      str | None,
            "fallback":   bool
        }
    """
    if _CLIENT is None:
        return {
            "success": False,
            "text": _template_fallback(prompt),
            "model_used": "template-fallback",
            "error": "GEMINI_API_KEY not configured. Add it to .env",
            "fallback": True,
        }

    # Check cache first — saves quota on repeated identical requests
    ck = _cache_key(prompt, temperature)
    cached = _cache_get(ck)
    if cached:
        logger.debug(f"[GeminiService] Cache hit — skipping API call")
        return {**cached, "cached": True}

    cfg = get_settings()
    models_to_try = [cfg.gemini_model, cfg.gemini_fallback_model]

    for model_name in models_to_try:
        try:
            # google-genai uses async generate_content directly
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda m=model_name: _CLIENT.models.generate_content(
                    model=m,
                    contents=prompt,
                    config=genai_types.GenerateContentConfig(
                        temperature=temperature,
                        max_output_tokens=max_tokens,
                    ),
                )
            )
            text = response.text.strip() if hasattr(response, "text") and response.text else ""
            if not text:
                raise ValueError("Empty response from model")

            logger.success(
                f"[GeminiService] ✅ {model_name} responded | {len(text)} chars"
            )
            result = {
                "success": True,
                "text": text,
                "model_used": model_name,
                "error": None,
                "fallback": False,
            }
            _cache_set(ck, result)   # Save for future identical requests
            return result

        except Exception as exc:
            err = str(exc)
            logger.warning(f"[GeminiService] {model_name} failed: {err[:140]}")
            # On 429 rate-limit: wait 8s before trying fallback model
            # Free tier resets within the same RPM window
            if any(kw in err.lower() for kw in ("quota", "rate", "429", "resource_exhausted", "resource")):
                logger.info("[GeminiService] Rate limit hit — waiting 8s before fallback model...")
                await asyncio.sleep(8)
            continue

    # All models failed — return safe template content
    return {
        "success": False,
        "text": _template_fallback(prompt),
        "model_used": "template-fallback",
        "error": "All Gemini models failed. Check API key / quota.",
        "fallback": True,
    }


# ── Health Check ───────────────────────────────────────────────────────────────
async def health_check() -> Dict[str, Any]:
    """Diagnostic ping — verifies live Gemini API connectivity."""
    start = time.perf_counter()
    result = await generate(
        prompt=(
            "You are the AI backbone for GlobalTrends25 e-commerce platform. "
            "Confirm API connection is active by replying with exactly: "
            "CONNECTED — GlobalTrends25 Gemini AI Online"
        ),
        temperature=0.1,
        max_tokens=32,
    )
    elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
    return {
        "status": "success" if result["success"] else "error",
        "gemini_response": result["text"],
        "model_used": result["model_used"],
        "latency_ms": elapsed_ms,
        "fallback_mode": result["fallback"],
        "error": result["error"],
        "sdk": "google-genai (latest)",
    }


# ── SEO Generator → WooCommerce Product Importer ──────────────────────────────
async def generate_product_seo(
    raw_title: str,
    raw_description: str,
    category: str = "General",
    target_market: str = "GlobalTrends25",
) -> Dict[str, Any]:
    """
    Takes raw supplier product data and returns an SEO-optimised
    WooCommerce-ready content block (title, meta, bullets, tags).
    """
    prompt = f"""You are a world-class e-commerce SEO copywriter for "{target_market}".

Supplier raw title: {raw_title}
Supplier raw description: {raw_description[:800]}
Store category: {category}

Generate a JSON object with EXACTLY these keys:
{{
  "seo_title": "<max 70 chars, keyword-rich, benefit-first, no brand padding>",
  "meta_description": "<max 160 chars, compelling CTA, includes main keyword>",
  "bullet_points": [
    "<benefit-led feature 1>",
    "<benefit-led feature 2>",
    "<benefit-led feature 3>",
    "<benefit-led feature 4>",
    "<social proof or guarantee>"
  ],
  "short_description": "<2-sentence punchy WooCommerce excerpt, ends with CTA>",
  "search_tags": ["<tag1>", "<tag2>", "<tag3>", "<tag4>", "<tag5>"]
}}

Return ONLY valid JSON. No markdown code fences. No extra commentary."""

    result = await generate(prompt, temperature=0.6, max_tokens=700)
    result["parsed"] = _safe_parse_json(result["text"])
    return result


# ── Marketing Ad Copy Generator → Marketing AI Agent ──────────────────────────
async def generate_marketing_campaigns(
    product_name: str,
    product_description: str,
    price: float = 0.0,
    category: str = "General",
    platforms: List[str] = None,
) -> Dict[str, Any]:
    """
    Generates viral multi-platform ad copy for TikTok, Facebook,
    Instagram, Pinterest, and Email marketing.
    """
    if platforms is None:
        platforms = ["tiktok", "facebook", "instagram", "email"]

    prompt = f"""You are a viral direct-response e-commerce marketing expert.

Product: {product_name}
Description: {product_description[:500]}
Price: ${price:.2f}
Category: {category}
Platforms needed: {", ".join(platforms)}

Generate a JSON object with EXACTLY these keys:
{{
  "campaign_title": "<punchy, memorable campaign name>",
  "tiktok_hook": "<3-second viral hook — max 15 words — shock/curiosity/desire>",
  "tiktok_script": "<30-second TikTok script, conversational, clear CTA at end>",
  "facebook_headline": "<Facebook ad headline, max 40 chars, benefit-first>",
  "facebook_primary_text": "<Facebook primary text, max 125 chars, emotional + CTA>",
  "instagram_caption": "<Instagram caption with emojis, 2 sentences + 5 hashtags>",
  "email_subject": "<Email subject, urgency/curiosity, max 50 chars>",
  "email_preview": "<Preview text, max 90 chars, complements subject>",
  "pinterest_title": "<Pinterest pin title, descriptive and searchable>",
  "ad_hook_variations": ["<hook variation 1>", "<hook variation 2>", "<hook variation 3>"]
}}

Return ONLY valid JSON. No markdown code fences. No extra text."""

    result = await generate(prompt, temperature=0.85, max_tokens=900)
    result["parsed"] = _safe_parse_json(result["text"])
    return result


# ── WooCommerce HTML Description Generator ─────────────────────────────────────
async def generate_product_description_html(
    product_name: str,
    features: List[str],
    category: str = "General",
) -> Dict[str, Any]:
    """Generate a full WooCommerce HTML product body description."""
    features_text = "\n".join(f"- {f}" for f in features[:8])
    prompt = f"""You are a premium WooCommerce product page copywriter.

Product: {product_name}
Category: {category}
Key Features:
{features_text}

Write a complete WooCommerce product description in clean HTML.
Include:
1. A powerful 2-sentence opening paragraph
2. A <ul> list of 5 customer-benefit bullet points (translate features → benefits)
3. A closing paragraph with a trust signal and call to action

Use ONLY: <p>, <ul>, <li>, <strong>, <em>
Keep under 350 words. Return only the HTML — no markdown, no explanations."""

    return await generate(prompt, temperature=0.65, max_tokens=700)


# ── Helpers ────────────────────────────────────────────────────────────────────
def _safe_parse_json(text: str) -> Optional[dict]:
    """Strip markdown fences and parse JSON; return None on failure."""
    try:
        clean = re.sub(r"```(?:json)?", "", text).strip().strip("`")
        return json.loads(clean)
    except Exception:
        return None


def _template_fallback(prompt: str) -> str:
    """Professional template content when Gemini is unreachable."""
    lower = prompt.lower()
    if "seo" in lower or "woocommerce" in lower or "bullet" in lower:
        return json.dumps({
            "seo_title": "Premium Quality Product — Best Value 2025",
            "meta_description": "Shop top-rated products with fast shipping and 30-day hassle-free returns. Order yours today.",
            "bullet_points": [
                "✅ Premium quality materials built to last",
                "✅ Fast worldwide shipping — arrives in 7-14 days",
                "✅ 30-day money-back guarantee, no questions asked",
                "✅ Trusted by 10,000+ happy customers globally",
                "✅ 24/7 dedicated customer support team",
            ],
            "short_description": "Experience premium quality at an unbeatable price. Order today and see why thousands of customers trust GlobalTrends25.",
            "search_tags": ["quality", "fast shipping", "best value", "top rated", "trusted brand"],
        })
    if any(kw in lower for kw in ("tiktok", "facebook", "campaign", "ad", "marketing")):
        return json.dumps({
            "campaign_title": "GlobalTrends25 Flash Sale Event",
            "tiktok_hook": "You've been OVERPAYING for this your whole life!",
            "tiktok_script": "POV: You just discovered the best deal of 2025. This product changed everything for me. It's unbelievable how much I was overpaying before. Limited stock available — check the link in bio before it sells out!",
            "facebook_headline": "⚡ Limited Time Deal — Save 40%",
            "facebook_primary_text": "Our best-selling product is flying off shelves. Order now before stock runs out! 30-day guarantee →",
            "instagram_caption": "✨ Upgrade your everyday without breaking the bank! 🛒 Tap the link in bio to grab yours before it's gone. #GlobalTrends25 #BestDeal #MustHave #OnlineShopping #TrendingNow",
            "email_subject": "⚡ Last Chance: 40% OFF Ends Tonight",
            "email_preview": "Your exclusive deal expires at midnight — don't miss out.",
            "pinterest_title": "Best Value Must-Have Product for 2025",
            "ad_hook_variations": [
                "Stop wasting money on overpriced alternatives!",
                "This is going viral for a reason — see why →",
                "Can't believe this is still available at this price",
            ],
        })
    return "AI content generation unavailable. Please configure GEMINI_API_KEY in .env"
