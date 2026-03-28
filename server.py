#!/usr/bin/env python3
"""MercadoLibre MCP Server — comprehensive ML API integration via FastMCP."""

from __future__ import annotations

import json
import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from ml_auth import MLAuth
from ml_client import MLClient

# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------

mcp = FastMCP("mercadolibre")

CREDS_PATH = os.environ.get(
    "ML_CREDENTIALS_PATH",
    os.path.expanduser("~/Proyectos/ml-scripts/config/ml_credentials_palishopping.json"),
)
READER_CREDS_PATH = os.environ.get(
    "ML_READER_CREDENTIALS_PATH",
    os.path.expanduser("~/Proyectos/ml-scripts/config/ml_credentials_cajasordenadoras.json"),
)

auth = MLAuth(CREDS_PATH)
reader_auth = MLAuth(READER_CREDS_PATH) if os.path.exists(READER_CREDS_PATH) else None
ml = MLClient(auth, reader_auth)

J = json.dumps  # shorthand for formatting results


def _fmt(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False)


# ============================= ACCOUNT =====================================

@mcp.tool()
def get_account_info() -> str:
    """Get authenticated user profile, reputation and seller status."""
    return _fmt(ml.get("/users/me"))


@mcp.tool()
def get_user_info(user_id: int) -> str:
    """Get public info for any ML user by ID."""
    return _fmt(ml.get(f"/users/{user_id}"))


@mcp.tool()
def get_user_addresses() -> str:
    """Get addresses of authenticated user."""
    return _fmt(ml.get(f"/users/{ml.user_id}/addresses"))


# ============================= ITEMS =======================================

@mcp.tool()
def list_items(
    status: str = "active",
    offset: int = 0,
    limit: int = 50,
    sort: str = "last_updated_desc",
) -> str:
    """List authenticated seller's items. Status: active|paused|closed|under_review. Max limit=100."""
    params = {"status": status, "offset": offset, "limit": limit, "sort": sort}
    search = ml.get(f"/users/{ml.user_id}/items/search", params=params)
    ids = search.get("results", [])
    if not ids:
        return _fmt({"total": search.get("paging", {}).get("total", 0), "items": []})
    # multiget (max 20 per call)
    items = []
    for i in range(0, len(ids), 20):
        batch = ",".join(ids[i : i + 20])
        items.extend(ml.get(f"/items?ids={batch}"))
    return _fmt({"total": search.get("paging", {}).get("total", 0), "items": items})


@mcp.tool()
def search_items_by_sku(sku: str) -> str:
    """Search seller's items by SKU (seller_custom_field)."""
    search = ml.get(f"/users/{ml.user_id}/items/search", params={"sku": sku})
    ids = search.get("results", [])
    if not ids:
        return _fmt({"results": []})
    batch = ",".join(ids[:20])
    return _fmt(ml.get(f"/items?ids={batch}"))


@mcp.tool()
def get_item(item_id: str, include_description: bool = True) -> str:
    """Get full item details. Optionally includes description."""
    item = ml.get(f"/items/{item_id}")
    if include_description:
        try:
            desc = ml.get(f"/items/{item_id}/description")
            item["description"] = desc
        except Exception:
            item["description"] = None
    return _fmt(item)


@mcp.tool()
def get_items_multi(item_ids: str) -> str:
    """Get multiple items at once. Pass comma-separated IDs (max 20)."""
    return _fmt(ml.get(f"/items?ids={item_ids}"))


@mcp.tool()
def validate_item(payload: str) -> str:
    """Validate item JSON before publishing. Returns errors or 'valid'.
    payload: JSON string of the item body."""
    body = json.loads(payload)
    try:
        result = ml.post("/items/validate", json_data=body)
        return _fmt(result)
    except Exception as e:
        return f"Validation error: {e}"


@mcp.tool()
def create_item(payload: str) -> str:
    """Create a new ML listing. payload: JSON string with full item body
    (title/family_name, category_id, price, currency_id, available_quantity,
    buying_mode, listing_type_id, condition, pictures, attributes, etc.)."""
    body = json.loads(payload)
    return _fmt(ml.post("/items", json_data=body))


@mcp.tool()
def update_item(item_id: str, payload: str) -> str:
    """Update item fields. payload: JSON string with fields to update
    (price, available_quantity, pictures, attributes, shipping, etc.)."""
    body = json.loads(payload)
    return _fmt(ml.put(f"/items/{item_id}", json_data=body))


@mcp.tool()
def update_price(item_id: str, price: float) -> str:
    """Update item price."""
    return _fmt(ml.put(f"/items/{item_id}", json_data={"price": price}))


@mcp.tool()
def update_stock(item_id: str, quantity: int) -> str:
    """Update item available quantity."""
    return _fmt(ml.put(f"/items/{item_id}", json_data={"available_quantity": quantity}))


@mcp.tool()
def pause_item(item_id: str) -> str:
    """Pause a listing."""
    return _fmt(ml.put(f"/items/{item_id}", json_data={"status": "paused"}))


@mcp.tool()
def activate_item(item_id: str) -> str:
    """Activate/unpause a listing."""
    return _fmt(ml.put(f"/items/{item_id}", json_data={"status": "active"}))


@mcp.tool()
def close_item(item_id: str) -> str:
    """Close a listing permanently."""
    return _fmt(ml.put(f"/items/{item_id}", json_data={"status": "closed"}))


@mcp.tool()
def delete_item(item_id: str) -> str:
    """Delete a closed/paused item."""
    return _fmt(ml.put(f"/items/{item_id}", json_data={"deleted": "true"}))


@mcp.tool()
def relist_item(item_id: str, price: float, quantity: int = 10000, listing_type_id: str = "gold_special") -> str:
    """Relist a closed item with new price/quantity."""
    return _fmt(ml.post(f"/items/{item_id}/relist", json_data={
        "price": price,
        "quantity": quantity,
        "listing_type_id": listing_type_id,
    }))


# ============================= DESCRIPTIONS ================================

@mcp.tool()
def get_item_description(item_id: str) -> str:
    """Get item description text."""
    return _fmt(ml.get(f"/items/{item_id}/description"))


@mcp.tool()
def set_item_description(item_id: str, plain_text: str) -> str:
    """Create or update item description (plain text only, no markdown/emojis)."""
    body = {"plain_text": plain_text}
    try:
        return _fmt(ml.post(f"/items/{item_id}/description", json_data=body))
    except Exception:
        return _fmt(ml.put(f"/items/{item_id}/description?api_version=2", json_data=body))


# ============================= VARIATIONS ==================================

@mcp.tool()
def get_item_variations(item_id: str) -> str:
    """Get all variations for an item."""
    return _fmt(ml.get(f"/items/{item_id}/variations"))


@mcp.tool()
def get_variation_detail(item_id: str, variation_id: str) -> str:
    """Get specific variation with all attributes."""
    return _fmt(ml.get(f"/items/{item_id}/variations/{variation_id}?include_attributes=all"))


# ============================= PICTURES ====================================

@mcp.tool()
def upload_picture(file_path: str) -> str:
    """Upload an image to ML. Returns picture ID and URLs. Recommended >=1200x1200px."""
    data = ml.upload(file_path)
    # pick best variation
    best = None
    best_area = 0
    for v in data.get("variations", []):
        try:
            w, h = v["size"].split("x")
            area = int(w) * int(h)
            if area > best_area:
                best_area = area
                best = v
        except Exception:
            pass
    return _fmt({
        "id": data.get("id"),
        "best_url": (best or {}).get("secure_url") or (best or {}).get("url"),
        "all_variations": data.get("variations"),
    })


# ============================= SEARCH ======================================

@mcp.tool()
def search_public(query: str, site_id: str = "MLA", offset: int = 0, limit: int = 20) -> str:
    """Public search on ML by keyword. site_id: MLA (AR), MLB (BR), MLM (MX), etc."""
    return _fmt(ml.get(f"/sites/{site_id}/search", params={
        "q": query, "offset": offset, "limit": limit,
    }))


@mcp.tool()
def search_by_seller(seller_id: int, site_id: str = "MLA", offset: int = 0, limit: int = 50) -> str:
    """Public search: all items from a specific seller."""
    return _fmt(ml.get(f"/sites/{site_id}/search", params={
        "seller_id": seller_id, "offset": offset, "limit": limit,
    }))


# ============================= CATEGORIES ==================================

@mcp.tool()
def get_site_categories(site_id: str = "MLA") -> str:
    """Get all top-level categories for a site."""
    return _fmt(ml.get(f"/sites/{site_id}/categories"))


@mcp.tool()
def get_category(category_id: str) -> str:
    """Get category details: children, path, settings, attributes."""
    return _fmt(ml.get(f"/categories/{category_id}"))


@mcp.tool()
def get_category_attributes(category_id: str) -> str:
    """Get required/optional attributes for a category."""
    return _fmt(ml.get(f"/categories/{category_id}/attributes"))


@mcp.tool()
def search_categories(query: str, site_id: str = "MLA") -> str:
    """Search categories by keyword (domain discovery)."""
    return _fmt(ml.get(f"/sites/{site_id}/domain_discovery/search", params={"q": query}))


@mcp.tool()
def get_category_sale_terms(category_id: str) -> str:
    """Get sale terms (IVA, warranty options) for a category."""
    return _fmt(ml.get(f"/categories/{category_id}/sale_terms"))


# ============================= ORDERS ======================================

@mcp.tool()
def list_orders(
    status: str = "",
    date_from: str = "",
    date_to: str = "",
    offset: int = 0,
    limit: int = 50,
    sort: str = "date_desc",
) -> str:
    """List seller orders. status: paid|shipped|delivered|cancelled. Dates: ISO format."""
    params: dict[str, Any] = {
        "seller": ml.user_id,
        "offset": offset,
        "limit": limit,
        "sort": sort,
    }
    if status:
        params["order.status"] = status
    if date_from:
        params["order.date_created.from"] = date_from
    if date_to:
        params["order.date_created.to"] = date_to
    return _fmt(ml.get("/orders/search", params=params))


@mcp.tool()
def get_order(order_id: str) -> str:
    """Get full order details."""
    return _fmt(ml.get(f"/orders/{order_id}"))


@mcp.tool()
def get_order_feedback(order_id: str) -> str:
    """Get buyer/seller feedback for an order."""
    return _fmt(ml.get(f"/orders/{order_id}/feedback"))


# ============================= QUESTIONS ===================================

@mcp.tool()
def list_questions(
    item_id: str = "",
    status: str = "UNANSWERED",
    offset: int = 0,
    limit: int = 50,
    sort: str = "DATE_CREATED_DESC",
) -> str:
    """List questions for seller. Filter by item_id and status (UNANSWERED|ANSWERED|ALL).
    sort: DATE_CREATED_DESC|DATE_CREATED_ASC."""
    params: dict[str, Any] = {
        "seller_id": ml.user_id,
        "api_version": 4,
        "offset": offset,
        "limit": limit,
        "sort_fields": sort,
    }
    if item_id:
        params["item"] = item_id
    if status and status != "ALL":
        params["status"] = status
    return _fmt(ml.get("/questions/search", params=params))


@mcp.tool()
def get_question(question_id: int) -> str:
    """Get question detail including buyer info."""
    return _fmt(ml.get(f"/questions/{question_id}?api_version=4"))


@mcp.tool()
def answer_question(question_id: int, text: str) -> str:
    """Answer a question. Max 2000 chars."""
    return _fmt(ml.post("/answers", json_data={
        "question_id": question_id,
        "text": text,
    }))


@mcp.tool()
def delete_question(question_id: int) -> str:
    """Delete a question."""
    return _fmt(ml.delete(f"/questions/{question_id}"))


# ============================= MESSAGES ====================================

@mcp.tool()
def get_unread_messages() -> str:
    """Get all packs with unread post-sale messages."""
    return _fmt(ml.get("/messages/unread?role=seller&tag=post_sale"))


@mcp.tool()
def get_pack_messages(pack_id: str, mark_as_read: bool = False) -> str:
    """Get messages for a specific order pack."""
    mark = "true" if mark_as_read else "false"
    return _fmt(ml.get(
        f"/messages/packs/{pack_id}/sellers/{ml.user_id}?tag=post_sale&mark_as_read={mark}"
    ))


@mcp.tool()
def send_message(pack_id: str, text: str) -> str:
    """Send a post-sale message to buyer."""
    return _fmt(ml.post(f"/marketplace/messages/packs/{pack_id}", json_data={"text": text}))


# ============================= SHIPPING ====================================

@mcp.tool()
def get_shipment(shipment_id: str) -> str:
    """Get shipment details (tracking, status, dates)."""
    return _fmt(ml.get(f"/shipments/{shipment_id}"))


@mcp.tool()
def get_shipping_options(item_id: str) -> str:
    """Get available shipping options for an item."""
    return _fmt(ml.get(f"/items/{item_id}/shipping_options"))


@mcp.tool()
def get_shipping_preferences() -> str:
    """Get seller's shipping preferences (Flex, free shipping, etc.)."""
    return _fmt(ml.get(f"/users/{ml.user_id}/shipping_preferences"))


# ============================= VISITS / METRICS ============================

@mcp.tool()
def get_item_visits(item_id: str, date_from: str = "", date_to: str = "") -> str:
    """Get visits for an item. Dates: YYYY-MM-DD format."""
    params: dict[str, str] = {"ids": item_id}
    if date_from:
        params["date_from"] = date_from
    if date_to:
        params["date_to"] = date_to
    return _fmt(ml.get("/items/visits", params=params))


@mcp.tool()
def get_item_visits_window(item_id: str, last: int = 7, unit: str = "day") -> str:
    """Get item visits for a time window. unit: day|hour."""
    return _fmt(ml.get(f"/items/{item_id}/visits/time_window", params={
        "last": last, "unit": unit,
    }))


@mcp.tool()
def get_seller_visits(last: int = 30, unit: str = "day") -> str:
    """Get total visits across all seller items for a time window."""
    return _fmt(ml.get(f"/users/{ml.user_id}/items_visits/time_window", params={
        "last": last, "unit": unit,
    }))


# ============================= PROMOTIONS ==================================

@mcp.tool()
def list_promotions() -> str:
    """List all active promotions for seller."""
    return _fmt(ml.get(f"/seller-promotions/users/{ml.user_id}?app_version=v2"))


@mcp.tool()
def get_item_promotions(item_id: str) -> str:
    """Get promotions applied to a specific item."""
    return _fmt(ml.get(f"/seller-promotions/items/{item_id}?app_version=v2"))


@mcp.tool()
def apply_promotion(item_id: str, promotion_id: str, promotion_type: str, offer_id: str = "", price: float = 0) -> str:
    """Apply a promotion to an item.
    For SMART: pass promotion_id, promotion_type='SMART', offer_id (the ref_id from get_item_promotions).
    For DEAL: pass promotion_id, promotion_type='DEAL', price (within min/max range)."""
    body: dict = {"promotion_id": promotion_id, "promotion_type": promotion_type}
    if offer_id:
        body["offer_id"] = offer_id
    if price:
        body["price"] = price
    return _fmt(ml.post(
        f"/seller-promotions/items/{item_id}?app_version=v2",
        json_data=body,
    ))


# ============================= PRICES ======================================

@mcp.tool()
def get_item_prices(item_id: str) -> str:
    """Get all price types for an item (sale price, loyalty, channels)."""
    return _fmt(ml.get(f"/items/{item_id}/prices"))


@mcp.tool()
def get_sale_price(item_id: str) -> str:
    """Get current sale price for an item."""
    return _fmt(ml.get(f"/items/{item_id}/sale_price"))


# ============================= BILLING =====================================

@mcp.tool()
def get_billing_periods(group: str = "ML") -> str:
    """Get last 12 billing periods. group: ML or MP."""
    return _fmt(ml.get(f"/billing/integration/monthly/periods?group={group}"))


@mcp.tool()
def get_billing_detail(period_key: str, group: str = "ML") -> str:
    """Get billing documents for a period (YYYY-MM-01)."""
    return _fmt(ml.get(
        f"/billing/integration/periods/key/{period_key}/documents?group={group}"
    ))


# ============================= ADS =========================================

@mcp.tool()
def get_ad_campaigns() -> str:
    """Get Product Ads campaigns with metrics."""
    try:
        adv = ml.get("/advertising/advertisers?product_id=PADS")
        # Response can be {"advertisers": [...]} or direct {"id": ...}
        adv_id = adv.get("id") or adv.get("advertiser_id")
        if not adv_id and isinstance(adv.get("advertisers"), list) and adv["advertisers"]:
            adv_id = adv["advertisers"][0].get("advertiser_id") or adv["advertisers"][0].get("id")
        if not adv_id:
            return _fmt({"error": "No advertiser found", "raw": adv})
        return _fmt(ml.get(f"/advertising/advertisers/{adv_id}/product_ads/campaigns"))
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def get_item_ad(item_id: str) -> str:
    """Get Product Ads detail and metrics for a specific item."""
    return _fmt(ml.get(f"/advertising/product_ads/items/{item_id}"))


# ============================= LISTING TYPES ===============================

@mcp.tool()
def get_listing_types() -> str:
    """Get available listing types for the user."""
    return _fmt(ml.get(f"/users/{ml.user_id}/available_listing_types"))


# ============================= NOTIFICATIONS ===============================

@mcp.tool()
def get_missed_notifications(topic: str = "") -> str:
    """Get missed webhook notifications. topic: items|questions|orders_v2|messages|etc."""
    app_id = auth.credentials.get("app_id", "")
    params: dict[str, str] = {"app_id": app_id}
    if topic:
        params["topic"] = topic
    return _fmt(ml.get("/missed_feeds", params=params))


# ===========================================================================
# Run
# ===========================================================================

if __name__ == "__main__":
    mcp.run(transport="stdio")
