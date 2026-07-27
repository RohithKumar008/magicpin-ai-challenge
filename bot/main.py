import os
import time
import uuid
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Any, Optional

from bot.context_store import ContextStore
from bot.composer import compose
from bot.reply_handler import handle_reply
from bot.config import TEAM_NAME, TEAM_MEMBERS, CONTACT_EMAIL, BOT_VERSION

START_TIME = time.time()
context_store = ContextStore()
conversation_store = {}
sent_bodies = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

app = FastAPI(title="Vera AI Challenge Bot", version=BOT_VERSION, lifespan=lifespan)

# ─── Schemas ───────────────────────────────────────────────────────────────────

class CtxBody(BaseModel):
    scope: str
    context_id: str
    version: int
    payload: dict[str, Any]
    delivered_at: str = ""

class TickBody(BaseModel):
    now: str
    available_triggers: list[str] = []

class ReplyBody(BaseModel):
    conversation_id: str
    merchant_id: Optional[str] = None
    customer_id: Optional[str] = None
    from_role: str
    message: str
    received_at: str = ""
    turn_number: int = 1

# ─── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/v1/healthz")
async def healthz():
    counts = context_store.counts()
    return {
        "status": "ok",
        "uptime_seconds": int(time.time() - START_TIME),
        "contexts_loaded": counts,
    }

@app.get("/v1/metadata")
async def metadata():
    return {
        "team_name": TEAM_NAME,
        "team_members": TEAM_MEMBERS,
        "model": os.environ.get("LLM_MODEL", "gpt-4o-mini"),
        "approach": "dispatched-prompt composer by trigger.kind with reply intent detection",
        "contact_email": CONTACT_EMAIL,
        "version": BOT_VERSION,
        "submitted_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }

@app.post("/v1/context")
async def push_context(body: CtxBody):
    valid_scopes = {"category", "merchant", "customer", "trigger"}
    if body.scope not in valid_scopes:
        return JSONResponse(
            status_code=400,
            content={"accepted": False, "reason": "invalid_scope", "details": f"Must be one of: {valid_scopes}"},
        )
    result = context_store.push(body.scope, body.context_id, body.version, body.payload, body.delivered_at)
    if result["accepted"]:
        return result
    return JSONResponse(status_code=409, content=result)

@app.post("/v1/tick")
async def tick(body: TickBody):
    actions = []

    for trigger_id in body.available_triggers:
        trigger = context_store.get_trigger(trigger_id)
        if not trigger:
            continue

        merchant_id = trigger.get("merchant_id")
        merchant = context_store.get_by_merchant_id(merchant_id)
        if not merchant:
            continue

        category = context_store.get_merchant_category(merchant)
        if not category:
            continue

        customer_id = trigger.get("customer_id")
        customer = context_store.get_merchant_customer(merchant_id, customer_id) if customer_id else None

        conv_id = f"conv_{merchant_id}_{trigger_id}_{uuid.uuid4().hex[:8]}"

        result = compose(category, merchant, trigger, customer)
        if not result.get("body"):
            continue

        conversation_store[conv_id] = {
            "turns": [],
            "suppressed": False,
            "auto_reply_count": 0,
        }
        sent_bodies.setdefault(conv_id, set()).add(result["body"].strip().lower())

        actions.append({
            "conversation_id": conv_id,
            "merchant_id": merchant_id,
            "customer_id": customer_id,
            "send_as": result.get("send_as", "vera"),
            "trigger_id": trigger_id,
            "template_name": result.get("template_name", "vera_generic_v1"),
            "template_params": result.get("template_params", []),
            "body": result["body"],
            "cta": result.get("cta", "open_ended"),
            "suppression_key": result.get("suppression_key", trigger.get("suppression_key", "")),
            "rationale": result.get("rationale", "Composed from context"),
        })

    return {"actions": actions}

@app.post("/v1/reply")
async def reply(body: ReplyBody):
    merchant = context_store.get_by_merchant_id(body.merchant_id)

    body_lower = body.message.strip().lower()
    sent_bodies_for_conv = sent_bodies.setdefault(body.conversation_id, set())
    if body_lower in sent_bodies_for_conv:
        return {
            "action": "send",
            "body": "You mentioned that already — how can I help further?",
            "cta": "open_ended",
            "rationale": "Merchant repeated themselves; gentle nudge forward.",
        }

    result = handle_reply(
        conversation_id=body.conversation_id,
        merchant_id=body.merchant_id,
        customer_id=body.customer_id,
        from_role=body.from_role,
        message=body.message,
        turn_number=body.turn_number,
        conversation_store=conversation_store,
        context_store=context_store,
    )

    if result.get("action") == "send" and result.get("body"):
        sent_bodies_for_conv.add(result["body"].strip().lower())

    return result

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("bot.main:app", host="0.0.0.0", port=port, reload=True)
