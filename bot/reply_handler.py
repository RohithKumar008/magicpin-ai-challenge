AUTO_REPLY_PATTERNS = [
    "thank you for contacting",
    "thank you for reaching out",
    "our team will respond shortly",
    "our team will get back to you",
    "we have received your message",
    "we appreciate your interest",
    "thanks for your message",
    "aapki jaankari ke liye dhanyavaad",
    "team tak pahuncha deti hoon",
    "automated assistant",
]

POSITIVE_INTENT = [
    "yes", "sure", "ok", "okay", "let's do it", "lets do it", "go ahead",
    "please", "send", "proceed", "confirm", "i'm in", "i am in", "sounds good",
    "do it", "start", "begin", "let's go", "lets go", "tell me more",
    "what's next", "whats next", "show me", "i want", "i'd like",
]

NEGATIVE_INTENT = [
    "stop", "unsubscribe", "don't message", "dont message", "not interested",
    "leave me alone", "spam", "stop messaging", "no more", "block",
    "don't contact", "dont contact", "not now", "nahi", "no thanks",
]

HOSTILE_INTENT = [
    "useless", "bothering", "harassing", "annoying", "stupid", "waste of time",
    "why are you", "who is this", "scam", "fraud",
]


def detect_intent(message: str) -> str:
    msg_lower = message.lower().strip()

    if any(h in msg_lower for h in HOSTILE_INTENT) and any(
        n in msg_lower for n in ["stop", "spam", "useless", "bother", "annoy"]
    ):
        return "HOSTILE"

    if any(n in msg_lower for n in NEGATIVE_INTENT):
        return "OPT_OUT"

    if msg_lower in ("yes", "ok", "okay", "sure", "do it", "go ahead", "let's do it", "lets do it"):
        return "COMMIT"

    if any(p in msg_lower for p in POSITIVE_INTENT):
        return "COMMIT"

    if message.endswith("?") or any(
        q in msg_lower for q in ["what", "how", "why", "when", "where", "can you", "could you", "tell me", "explain"]
    ):
        return "QUESTION"

    return "ENGAGED"


def is_auto_reply(message: str) -> bool:
    msg_lower = message.lower().strip()
    for pattern in AUTO_REPLY_PATTERNS:
        if pattern in msg_lower:
            return True
    return False


def handle_reply(
    conversation_id: str,
    merchant_id: str,
    customer_id: str,
    from_role: str,
    message: str,
    turn_number: int,
    conversation_store: dict,
    context_store,
) -> dict:
    conv = conversation_store.setdefault(conversation_id, {
        "turns": [],
        "auto_reply_count": 0,
        "suppressed": False,
        "last_body": None,
    })

    conv["turns"].append({"role": from_role, "msg": message, "turn": turn_number})

    if conv.get("suppressed"):
        return {"action": "end", "rationale": "Conversation previously suppressed"}

    if is_auto_reply(message):
        conv["auto_reply_count"] = conv.get("auto_reply_count", 0) + 1
        count = conv["auto_reply_count"]
        if count >= 3:
            return {"action": "end", "rationale": f"Auto-reply detected {count} times consecutively. No real engagement. Closing conversation."}
        elif count >= 2:
            return {"action": "wait", "wait_seconds": 86400, "rationale": "Same auto-reply twice in a row — owner not at phone. Waiting 24h before retry."}
        else:
            return {"action": "send", "body": "Looks like an auto-reply 😊 When the owner sees this, just reply 'Yes' if interested.", "cta": "binary_yes_no", "rationale": "Auto-reply detected; one prompt for the owner."}

    intent = detect_intent(message)

    if intent == "OPT_OUT":
        conv["suppressed"] = True
        return {"action": "end", "rationale": "Merchant opted out. Closing and suppressing conversation."}

    if intent == "HOSTILE":
        conv["suppressed"] = True
        return {"action": "end", "rationale": "Hostile response detected. Gracefully exiting conversation."}

    if intent == "COMMIT":
        merchant = context_store.get_by_merchant_id(merchant_id)
        owner = (merchant.get("identity", {}).get("owner_first_name", "there") if merchant else "there")
        return _handle_commit(conversation_id, owner, conv)

    if intent == "QUESTION":
        return _handle_question(message, conv)

    return _handle_engaged(message, conv)


def _handle_commit(conversation_id: str, owner_name: str, conv: dict) -> dict:
    return {
        "action": "send",
        "body": f"Great {owner_name}! Drafting it now — 90 seconds. I'll pre-fill the content for your review. Reply CONFIRM to send, or tell me what to adjust.",
        "cta": "binary_confirm_cancel",
        "rationale": "Merchant explicitly committed; switching from pitch to action. Concrete next step offered."
    }


def _handle_question(message: str, conv: dict) -> dict:
    return {
        "action": "send",
        "body": "Great question! Let me check — here's what I can share based on your data. Want me to dive deeper on this?",
        "cta": "binary_yes_no",
        "rationale": "Merchant asked a question; acknowledging and offering deeper info."
    }


def _handle_engaged(message: str, conv: dict) -> dict:
    return {
        "action": "send",
        "body": "Got it, thanks for sharing! Here's what I'd suggest as a next step — want me to put this together?",
        "cta": "binary_yes_no",
        "rationale": "Engaged response; keeping conversation flowing with a next step."
    }
