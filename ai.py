import os
import requests
import uuid
import json
import random
import logging
import sqlite3
from flask import g, Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from typing import List, Dict, Any, Tuple, Optional
import time

# ============================================================================
# AI CLIENT INITIALIZATION - ANTHROPIC RECOMMENDED
# ============================================================================

# ===== OPTION 2: OPENAI =====
from openai import OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
GPT_MINI_MODEL = "gpt-4.1-mini"
AI_PROVIDER = "openai"
 
def llm_complete(prompt, *, temperature=0.7, max_tokens=256):
    """OpenAI completion"""
    response = client.chat.completions.create(
        model=GPT_MINI_MODEL,
        messages=[
            {"role": "system", "content": "You are a helpful, playful word-game master."},
            {"role": "user", "content": prompt}
        ],
        temperature=temperature,
        max_tokens=max_tokens
    )
    return response.choices[0].message.content.strip()

GPT_NANO_MODEL = "gpt-4.1-nano"  # already correct
def llm_complete_fast(prompt: str, *, temperature: float = 0.0, max_tokens: int = 40) -> str:
    """
    Fast, cheap judge call for word equivalence.
    Uses GPT-4.1 nano (low latency).
    """
    resp = client.chat.completions.create(
        model=GPT_NANO_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return (resp.choices[0].message.content or "").strip()



GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.1-8b-instant"  # fastest Groq model, ~150ms

def llm_complete_fastest(prompt: str, temperature: float = 0.9, max_tokens: int = 150) -> str:
    """
    Ultra-fast commentary generation using Groq's llama-3.1-8b-instant.
    ~150ms latency. Used only for funny game commentary messages.
    """
    key = GROQ_API_KEY or os.getenv("GROQ_API_KEY")
    if not key:
        return ""  # Fail silently — commentary is cosmetic

    payload = {
        "model": GROQ_MODEL,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a funny, witty game show host commentating on a word-guessing game. "
                    "Generate ONE short funny reaction (max 10 words). "
                    "Be playful, use humor, vary your style. Just the reaction, nothing else. "
                    "You can also be a player who guesses a word, dependong on the prompt"
                )
            },
            {"role": "user", "content": prompt},
        ],
    }

    try:
        r = requests.post(
            GROQ_CHAT_URL,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=payload,
            timeout=5,  # short timeout — commentary is cosmetic, don't block game
        )
        r.raise_for_status()
        return (r.json()["choices"][0]["message"]["content"] or "").strip()
    except Exception:
        return ""  # Fail silently
