# main.py
"""
VerdictAI - FastAPI entrypoint (MATCHES CURRENT REPO)

This main.py is aligned with your actual codebase:
- cod_agents.py exports: CoD_Agents with .run_debate(...)
- you_search.py exports: YouSearcher with .search(...)
- memory.py exports: Memory with .init_db(), .find_similar_claim(), .store_claim()
- integrations.py exports: ActionEngine with .execute_actions()

It also serves index.html from project root (no hard-coded /home/claude paths).
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional, List

from fastapi import FastAPI, Response
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from config import config
from memory import Memory
from you_search import YouSearcher
from cod_agents import CoD_Agents
from integrations import ActionEngine

APP_TITLE = "VerdictAI"
APP_VERSION = "0.1.0"

app = FastAPI(title=APP_TITLE, version=APP_VERSION)

# Singletons
memory = Memory(config.DATABASE_PATH)
you = YouSearcher()
cod = CoD_Agents()
actions = ActionEngine()


# -------------------------
# Models
# -------------------------
class AnalyzeContext(BaseModel):
    source: str = Field(default="user", description="user|news|social|intercom")
    audience: str = Field(default="public", description="public|internal")
    urgency_hint: str = Field(default="medium", description="low|medium|high")


class AnalyzeRequest(BaseModel):
    claim: str = Field(..., min_length=3)
    context: Optional[AnalyzeContext] = None


# -------------------------
# Helpers
# -------------------------
def _now_ms() -> int:
    return int(time.time() * 1000)


def _read_ui() -> str:
    candidates = [
        "index.html",
        os.path.join(os.path.dirname(__file__), "index.html"),
        os.path.join(os.getcwd(), "index.html"),
    ]
    for path in candidates:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            continue

    return """
    <html>
      <head><title>VerdictAI</title></head>
      <body style="font-family: system-ui; padding: 24px;">
        <h2>VerdictAI</h2>
        <p><b>index.html</b> not found in project root.</p>
      </body>
    </html>
    """


def _normalize_evidence(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Ensure evidence items are dicts with title/url/snippet keys."""
    normalized = []
    for r in results or []:
        if not isinstance(r, dict):
            continue
        normalized.append(
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("snippet", ""),
            }
        )
    return normalized


# -------------------------
# Startup / Routes
# -------------------------
@app.on_event("startup")
async def on_startup() -> None:
    # Creates claims table in file DB
    await memory.init_db()


# Explicit HEAD handler so probes that use HEAD (e.g. UptimeRobot) receive 200
@app.head("/")
async def serve_ui_head() -> Response:
    # HEAD responses should not include a body. Return 200 with empty body.
    return Response(status_code=200)


@app.get("/", response_class=HTMLResponse)
async def serve_ui() -> HTMLResponse:
    return HTMLResponse(content=_read_ui())


@app.get("/health")
async def health() -> Dict[str, Any]:
    return {
        "ok": True,
        "app": APP_TITLE,
        "version": APP_VERSION,
        "env": config.APP_ENV,
        "db_path": config.DATABASE_PATH,
        "llm_configured": bool(config.LLM_API_KEY),
        "you_configured": bool(config.YOU_API_KEY),
        "intercom_configured": bool(getattr(config, "INTERCOM_TOKEN", "")) and bool(
            getattr(config, "INTERCOM_TARGET_ID", "")
        ),
        "plivo_configured": bool(getattr(config, "PLIVO_AUTH_ID", "")) and bool(
            getattr(config, "PLIVO_AUTH_TOKEN", "")
        ),
    }


@app.post("/analyze")
async def analyze(req: AnalyzeRequest) -> JSONResponse:
    t0 = _now_ms()
    claim = req.claim.strip()
    context = (req.context or AnalyzeContext()).model_dump()

    # 1) Memory lookup (fast reuse)
    try:
        cached = await memory.find_similar_claim(claim)
        if cached and isinstance(cached, dict) and cached.get("json_blob"):
            blob = cached["json_blob"]
            blob.setdefault("memory", {})
            blob["memory"]["hit"] = True
            blob["memory"]["matched_claim_id"] = cached.get("id")
            blob.setdefault("meta", {})
            blob["meta"]["latency_ms"] = _now_ms() - t0
            return JSONResponse(content=blob)
    except Exception:
        # Keep demo running even if memory fails
        pass

    # 2) Evidence retrieval (You.com or mock)
    base_results = await you.search(claim, num_results=5)
    debunk_results = await you.search(f"debunk {claim}", num_results=5)

    base_results = _normalize_evidence(base_results)
    debunk_results = _normalize_evidence(debunk_results)

    evidence = {
        "for": base_results[:3],
        "against": debunk_results[:3],
        "all": (base_results + debunk_results)[:8],
    }

    # 3) Chain-of-Debate
    try:
        debate_out = await cod.run_debate(claim, evidence)
    except Exception as e:
        debate_out = {
            "verdict": "uncertain",
            "confidence": 20,
            "risk_level": "medium",
            "topic": "general",
            "why_bullets": ["CoD pipeline failed; returning conservative uncertainty."],
            "uncertainties": [str(e)],
            "debate_transcript": [
                {"agent": "moderator", "message": "Fallback uncertain verdict due to error."}
            ],
            "reply_templates": {
                "neutral": "I’m not fully sure this is accurate—worth checking reliable sources before sharing.",
                "firm_mod": "We can’t verify this claim with reliable evidence right now.",
                "friendly": "Not sure this is true—maybe double-check before reposting.",
            },
            "evidence_for": evidence["for"],
            "evidence_against": evidence["against"],
        }

    # Ensure response has XAI fields even if agents didn’t include them
    response: Dict[str, Any] = {
        "claim": claim,
        "context": context,
        "verdict": debate_out.get("verdict", "uncertain"),
        "confidence": int(debate_out.get("confidence", 0)),
        "risk_level": debate_out.get("risk_level", "medium"),
        "topic": debate_out.get("topic", "general"),
        "evidence_for": debate_out.get("evidence_for", evidence["for"]),
        "evidence_against": debate_out.get("evidence_against", evidence["against"]),
        "explainability": {
            "why_bullets": debate_out.get("why_bullets", []),
            "uncertainties": debate_out.get("uncertainties", []),
            "debate_transcript": debate_out.get("debate_transcript", []),
        },
        "reply_templates": debate_out.get("reply_templates", {}),
        "actions": {"intercom": {"sent": False}, "plivo_sms": {"sent": False}},
        "memory": {"hit": False, "matched_claim_id": None},
        "meta": {"latency_ms": None},
    }

    # 4) Execute actions (Intercom/Plivo)
    try:
        action_results = await actions.execute_actions(response)
        if isinstance(action_results, dict):
            response["actions"] = action_results
    except Exception:
        pass

    # 5) Store in memory
    try:
        await memory.store_claim(response["claim"], response)
    except Exception:
        pass

    response["meta"]["latency_ms"] = _now_ms() - t0
    return JSONResponse(content=response)
