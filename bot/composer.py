import json
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

from bot.prompts import build_context_summary, get_prompt
from bot.llm import call_llm


def compose(
    category: dict,
    merchant: dict,
    trigger: dict,
    customer: dict = None,
) -> dict:
    context_summary = build_context_summary(category, merchant, trigger, customer)
    has_customer = customer is not None
    trigger_kind = trigger.get("kind", "default") if trigger else "default"

    system_prompt = get_prompt(trigger_kind, has_customer)

    user_prompt = f"""Compose a WhatsApp message for this scenario:

{context_summary}

Return ONLY valid JSON with keys: body, cta, rationale, suppression_key."""

    raw = None
    with ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(call_llm, system_prompt, user_prompt, 0.0, 1000)
        try:
            raw = fut.result(timeout=28)
        except FuturesTimeout:
            return _fallback(trigger, merchant, category, customer, "LLM timeout after 28s")
        except Exception as e:
            return _fallback(trigger, merchant, category, customer, f"LLM error: {e}")

    result = _parse_llm_response(raw)
    result = _validate_action(result, trigger, merchant, category, customer)
    return result


def _parse_llm_response(raw: str) -> dict:
    match = re.search(r"\{[\s\S]*\}", raw)
    if not match:
        return {}
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        cleaned = re.sub(r",\s*}", "}", match.group())
        cleaned = re.sub(r",\s*]", "]", cleaned)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return {}


def _validate_action(result: dict, trigger: dict, merchant: dict, category: dict, customer: dict = None) -> dict:
    identity = merchant.get("identity", {}) if merchant else {}
    owner_name = identity.get("owner_first_name", "there")
    merchant_name = identity.get("name", "your business")
    merchant_id = merchant.get("merchant_id", "") if merchant else ""
    customer_id = customer.get("customer_id", "") if customer else None
    has_cust = customer is not None

    body = result.get("body", "")
    cta = result.get("cta", "open_ended")
    rationale = result.get("rationale", "Composed from context")

    if not body or len(body) < 10:
        body = f"Hi {owner_name}, I noticed something relevant to {merchant_name}. Want to discuss? Reply YES to learn more."
        cta = "binary_yes_no"
        rationale = "Fallback: LLM output was empty or too short"

    if cta not in ("binary_yes_no", "open_ended", "none", "multi_choice_slot"):
        cta = "open_ended"

    suppression_key = result.get("suppression_key") or (trigger.get("suppression_key", "") if trigger else "")
    trigger_id = trigger.get("id", "") if trigger else ""
    send_as = "merchant_on_behalf" if has_cust else "vera"
    template_name = f"vera_{trigger.get('kind', 'generic')}_v1" if trigger else "vera_generic_v1"
    template_params = [owner_name, body[:100]]

    return {
        "body": body,
        "cta": cta,
        "send_as": send_as,
        "trigger_id": trigger_id,
        "suppression_key": suppression_key,
        "template_name": template_name,
        "template_params": template_params,
        "rationale": rationale,
        "merchant_id": merchant_id,
        "customer_id": customer_id,
    }


def _fallback(trigger: dict, merchant: dict, category: dict, customer: dict = None, reason: str = "") -> dict:
    identity = merchant.get("identity", {}) if merchant else {}
    owner_name = identity.get("owner_first_name", "there")
    merchant_name = identity.get("name", "your business")
    city = identity.get("city", "")
    locality = identity.get("locality", "")
    merchant_id = merchant.get("merchant_id", "") if merchant else ""
    customer_id = customer.get("customer_id", "") if customer else None
    has_cust = customer is not None
    trigger_id = trigger.get("id", "") if trigger else ""
    trigger_kind = trigger.get("kind", "") if trigger else ""
    perf = merchant.get("performance", {}) if merchant else {}
    signals = merchant.get("signals", []) if merchant else {}
    offers = [o.get("title", "") for o in (merchant.get("offers", []) if merchant else []) if o.get("status") == "active"]

    if has_cust:
        cust_name = customer.get("identity", {}).get("name", "there")
        cust_last = customer.get("relationship", {}).get("last_visit", "some time ago")
        cust_services = customer.get("relationship", {}).get("services_received", [])
        cust_lang = customer.get("identity", {}).get("language_pref", "en")
        body = f"Hi {cust_name}, {merchant_name} here — it's been a while since your last visit ({cust_last}). We have some new services you might like. Want to know more?"
        if offers:
            body = f"Hi {cust_name}, {merchant_name} here — it's been a while! We have {offers[0]} available. Want to come by?"
        cta = "binary_yes_no"
    elif trigger_kind == "research_digest":
        digest = (category or {}).get("digest", [])
        item = digest[0] if digest else {}
        title = item.get("title", "latest industry research")
        source = item.get("source", "")
        body = f"Hi {owner_name}, saw {source} has a new piece on {title}. Relevant to your practice — want me to pull the key points?"
        cta = "binary_yes_no"
    elif trigger_kind == "perf_dip":
        metric = trigger.get("payload", {}).get("metric", "performance")
        delta = trigger.get("payload", {}).get("delta_pct", "?")
        body = f"Hi {owner_name}, noticed your {metric} dropped {delta}% recently. Want me to take a look and suggest what might help?"
        cta = "binary_yes_no"
    elif trigger_kind == "perf_spike":
        metric = trigger.get("payload", {}).get("metric", "performance")
        delta = trigger.get("payload", {}).get("delta_pct", "?")
        body = f"Hi {owner_name}, great news — your {metric} is up {delta}%! Want me to help amplify this momentum with a GBP post?"
        cta = "binary_yes_no"
    elif trigger_kind == "milestone_reached":
        metric = trigger.get("payload", {}).get("metric", "?")
        val = trigger.get("payload", {}).get("value_now", "?")
        body = f"Hi {owner_name}, you're at {val} {metric}! A quick thank-you post could help you cross the next milestone. Want me to draft one?"
        cta = "binary_yes_no"
    elif trigger_kind == "renewal_due":
        days = trigger.get("payload", {}).get("days_remaining", "?")
        plan = trigger.get("payload", {}).get("plan", "your plan")
        body = f"Hi {owner_name}, your {plan} plan renews in {days} days. Want me to share what you'd lose and help you renew?"
        cta = "binary_yes_no"
    elif trigger_kind == "regulation_change":
        deadline = trigger.get("payload", {}).get("deadline_iso", "soon")
        top_item_id = trigger.get("payload", {}).get("top_item_id")
        digest = (category or {}).get("digest", [])
        item = next((d for d in digest if d.get("id") == top_item_id), {}) if top_item_id else (digest[0] if digest else {})
        title = item.get("title", "new regulation")
        body = f"Hi {owner_name}, there's a regulation update affecting your practice: {title} (deadline: {deadline[:10] if isinstance(deadline, str) else deadline}). Want me to summarize what it means for you?"
        cta = "binary_yes_no"
    elif trigger_kind == "competitor_opened":
        comp = trigger.get("payload", {}).get("competitor_name", "a new competitor")
        dist = trigger.get("payload", {}).get("distance_km", "nearby")
        body = f"Hi {owner_name}, noticed {comp} opened {dist}km from your location. Your {perf.get('ctr', '?')} CTR and established reputation are strong advantages. Want me to suggest some positioning moves?"
        cta = "binary_yes_no"
    elif trigger_kind == "supply_alert":
        mol = trigger.get("payload", {}).get("molecule", "medication")
        batches = trigger.get("payload", {}).get("affected_batches", [])
        body = f"Hi {owner_name}, alert on {mol} batches {', '.join(batches[:2])}. Want me to pull your affected customer list and draft the notification?"
        cta = "binary_yes_no"
    elif trigger_kind == "ipl_match_today":
        match = trigger.get("payload", {}).get("match", "today's match")
        body = f"Hi {owner_name}, {match} is on tonight! Want me to suggest how to adjust your offers/visibility for the match crowd?"
        cta = "binary_yes_no"
    elif trigger_kind == "festival_upcoming":
        fest = trigger.get("payload", {}).get("festival", "upcoming festival")
        body = f"Hi {owner_name}, {fest} is coming up! Want me to draft a festive post or offer for your customers?"
        cta = "binary_yes_no"
    elif trigger_kind == "curious_ask_due":
        body = f"Hi {owner_name}! Quick check — what's been the most popular service this week at your business? I'll turn your answer into a GBP post. Takes 5 min."
        cta = "open_ended"
    elif trigger_kind == "active_planning_intent":
        topic = trigger.get("payload", {}).get("intent_topic", "your idea").replace("_", " ")
        body = f"Hi {owner_name}, following up on {topic} — I've drafted a starter version. Want me to share it for your review?"
        cta = "binary_yes_no"
    elif trigger_kind == "seasonal_perf_dip":
        metric = trigger.get("payload", {}).get("metric", "performance")
        delta = trigger.get("payload", {}).get("delta_pct", "some")
        body = f"Hi {owner_name}, your {metric} is down {delta}% — but this is a normal seasonal pattern for your category. Want me to suggest a retention-focused plan for this period?"
        cta = "binary_yes_no"
    elif trigger_kind == "review_theme_emerged":
        theme = trigger.get("payload", {}).get("theme", "a topic")
        count = trigger.get("payload", {}).get("occurrences_30d", "several")
        body = f"Hi {owner_name}, noticed '{theme}' mentioned in {count} recent reviews. Want me to draft a response and suggest improvements?"
        cta = "binary_yes_no"
    elif trigger_kind == "gbp_unverified":
        uplift = trigger.get("payload", {}).get("estimated_uplift_pct", 0.30)
        uplift_pct = int(uplift * 100) if isinstance(uplift, float) and uplift < 1 else uplift
        body = f"Hi {owner_name}, your Google Business Profile isn't verified yet — estimated {uplift_pct}% boost in calls once verified. Want me to walk through the 5-min verification?"
        cta = "binary_yes_no"
    elif trigger_kind == "cde_opportunity":
        digest = (category or {}).get("digest", [])
        top_id = trigger.get("payload", {}).get("digest_item_id")
        item = next((d for d in digest if d.get("id") == top_id), {}) if top_id else (digest[0] if digest else {})
        title = item.get("title", "a training opportunity")
        credits = trigger.get("payload", {}).get("credits", "")
        fee = trigger.get("payload", {}).get("fee", "")
        body = f"Hi {owner_name}, there's a CDE opportunity: {title} ({credits} credits, {fee}). Want me to share details and a registration link?"
        cta = "binary_yes_no"
    elif trigger_kind == "winback_eligible":
        days = trigger.get("payload", {}).get("days_since_expiry", "some time")
        body = f"Hi {owner_name}, it's been {days} days since your subscription ended. We've made some improvements since then — want a quick re-onboarding tour?"
        cta = "binary_yes_no"
    elif trigger_kind == "dormant_with_vera":
        days = trigger.get("payload", {}).get("days_since_last_merchant_message", "a while")
        body = f"Hi {owner_name}, it's been {days} days — wanted to share something new that might interest you. Got 2 min?"
        cta = "binary_yes_no"
    elif trigger_kind == "category_seasonal":
        trends = trigger.get("payload", {}).get("trends", [])
        trend_items = ", ".join(trends[:3]) if trends else "shifting demand"
        body = f"Hi {owner_name}, seasonal demand is shifting — {trend_items}. Want me to suggest how to adjust your inventory/offers?"
        cta = "binary_yes_no"
    elif trigger_kind == "customer_lapsed_hard" or trigger_kind == "customer_lapsed_soft":
        cust_name = customer.get("identity", {}).get("name", "your customer") if customer else "a customer"
        days = trigger.get("payload", {}).get("days_since_last_visit", "some time")
        body = f"Hi {owner_name}, {cust_name} hasn't visited in {days} days. Want me to draft a gentle winback message?"
        cta = "binary_yes_no"
    else:
        body = f"Hi {owner_name}, noticed something about {merchant_name} worth checking. Want me to share details?"
        cta = "binary_yes_no"

    return {
        "body": body,
        "cta": cta,
        "send_as": "merchant_on_behalf" if has_cust else "vera",
        "trigger_id": trigger_id,
        "suppression_key": trigger.get("suppression_key", "") if trigger else "",
        "template_name": "vera_fallback_v1",
        "template_params": [owner_name, body[:100]],
        "rationale": f"Fallback composition: {reason}",
        "merchant_id": merchant_id,
        "customer_id": customer_id,
    }
