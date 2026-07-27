import time
from datetime import datetime, timezone

class ContextStore:
    def __init__(self):
        self._store = {}
        self._version_tracker = {}

    def push(self, scope: str, context_id: str, version: int, payload: dict, delivered_at: str = None):
        key = (scope, context_id)
        current = self._store.get(key)
        if current is not None and current["version"] >= version:
            return {"accepted": False, "reason": "stale_version", "current_version": current["version"]}
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        self._store[key] = {"version": version, "payload": payload, "stored_at": now}
        ack_id = f"ack_{context_id}_v{version}"
        return {"accepted": True, "ack_id": ack_id, "stored_at": now}

    def get(self, scope: str, context_id: str):
        entry = self._store.get((scope, context_id))
        return entry["payload"] if entry else None

    def get_by_merchant_id(self, merchant_id: str):
        return self.get("merchant", merchant_id)

    def get_merchant_category(self, merchant: dict):
        if not merchant:
            return None
        slug = merchant.get("category_slug")
        return self.get("category", slug) if slug else None

    def get_merchant_customer(self, merchant_id: str, customer_id: str):
        if not customer_id:
            return None
        return self.get("customer", customer_id)

    def get_trigger(self, trigger_id: str):
        return self.get("trigger", trigger_id)

    def counts(self):
        counts = {"category": 0, "merchant": 0, "customer": 0, "trigger": 0}
        for (scope, _) in self._store:
            if scope in counts:
                counts[scope] += 1
        return counts
