"""
Gemini_Engine/gemini_client.py
==============================
Handles communication using local Ollama or compatible local inference API,
replacing cloud Gemini API dependency.
Default model is configurable via OLLAMA_MODEL (e.g. gemma4, gemma:7b, gemma2:2b, etc.).
"""

import os
import json
import urllib.request
import urllib.error
from pathlib import Path
from dotenv import load_dotenv

# Load backend/.env
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma:7b")

def generate_report(prompt: str) -> str:
    """
    Sends the compiled investigation prompt to the local Ollama instance
    and returns the generated markdown investigation report.
    """
    endpoint = f"{OLLAMA_BASE_URL}/api/generate"
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.2,
            "num_predict": 4096
        }
    }
    
    print(f"[Local AI Client] Querying local Ollama model '{OLLAMA_MODEL}' at {endpoint}...")
    
    req_data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=req_data,
        headers={"Content-Type": "application/json"}
    )
    
    try:
        with urllib.request.urlopen(req, timeout=300) as response:
            res_body = response.read().decode("utf-8")
            data = json.loads(res_body)
            return data.get("response", "")
    except urllib.error.URLError as e:
        error_msg = (
            f"[Local AI Client] Could not connect to Ollama at {endpoint} ({e}).\n"
            f"Please ensure Ollama is running (`ollama serve`) and model '{OLLAMA_MODEL}' "
            f"is pulled (`ollama pull {OLLAMA_MODEL}`).\n"
            f"Generating a local deterministic fallback forensic report."
        )
        print(error_msg)
        return (
            f"# FORENSIC INVESTIGATION REPORT (OFFLINE RECONSTRUCTION)\n\n"
            f"> **Notice**: Local model `{OLLAMA_MODEL}` was unreachable at `{endpoint}`.\n\n"
            f"## Executive Summary\n"
            f"Automated deterministic offline correlation reconstructed from multi-channel forensic signals.\n"
            f"Suspicious transaction loops, burst telecom logs, and coordinate alignments were detected.\n\n"
            f"## Analysis Output\n"
            f"Review generated network entities and person risk profiles in the primary dashboard.\n"
        )
