from __future__ import annotations

from hyoka import flush, memory_event, tool, trace


@tool
def lookup_order(order_id: str) -> dict:
    return {"order_id": order_id, "status": "delivered"}


@tool
def issue_refund(order_id: str) -> dict:
    return {"refund_id": f"rf_{order_id.lower()}", "status": "issued"}


@trace(agent="refund-agent", suite="support-v1")
def run_agent(message: str) -> str:
    order_id = message.rsplit(" ", 1)[-1]
    memory_event("read", "refund_policy", {"requires_delivery_check": True})
    order = lookup_order(order_id)
    if order["status"] == "delivered":
        issue_refund(order_id)
        return "Your refund has been issued after verifying delivery."
    return "I cannot issue a refund until delivery is confirmed."


if __name__ == "__main__":
    print(run_agent("Refund order A123"))
    flush()

