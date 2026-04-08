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


def _extract_skus_from_item(item: dict) -> list[str]:
    """Devuelve TODOS los lugares donde puede estar un SKU en un item ML."""
    skus = []
    scf = item.get("seller_custom_field")
    if scf:
        skus.append(scf)
    for attr in item.get("attributes") or []:
        if (attr.get("id") or "").upper() == "SELLER_SKU":
            v = attr.get("value_name")
            if v:
                skus.append(v)
    for var in item.get("variations") or []:
        v_scf = var.get("seller_custom_field")
        if v_scf:
            skus.append(v_scf)
        for attr in var.get("attributes") or []:
            if (attr.get("id") or "").upper() == "SELLER_SKU":
                v = attr.get("value_name")
                if v:
                    skus.append(v)
    return skus


def _find_items_by_sku(sku: str) -> list[dict]:
    """Búsqueda robusta de items por SKU.

    1. Intenta el endpoint nativo del seller (rápido si el SKU está en
       seller_custom_field indexado).
    2. Si vuelve vacío, hace fallback paginando todos los items activos del
       seller y filtrando client-side por las 3 ubicaciones posibles del SKU.
    Devuelve lista de items completos (puede ser vacía).
    """
    # Intento 1: endpoint nativo
    search = ml.get(f"/users/{ml.user_id}/items/search", params={"sku": sku})
    ids = search.get("results", []) or []
    if ids:
        items: list[dict] = []
        for i in range(0, len(ids), 20):
            batch = ",".join(ids[i : i + 20])
            for entry in ml.get(f"/items?ids={batch}"):
                body = entry.get("body") if isinstance(entry, dict) else None
                if body:
                    items.append(body)
        return items

    # Intento 2 (fallback): paginar todos los items activos del seller y filtrar
    matches: list[dict] = []
    sku_upper = sku.strip().upper()
    offset = 0
    page_size = 50
    while True:
        page = ml.get(
            f"/users/{ml.user_id}/items/search",
            params={"status": "active", "offset": offset, "limit": page_size},
        )
        page_ids = page.get("results", []) or []
        if not page_ids:
            break
        for i in range(0, len(page_ids), 20):
            batch = ",".join(page_ids[i : i + 20])
            for entry in ml.get(f"/items?ids={batch}"):
                body = entry.get("body") if isinstance(entry, dict) else None
                if not body:
                    continue
                item_skus = [s.strip().upper() for s in _extract_skus_from_item(body)]
                if sku_upper in item_skus:
                    matches.append(body)
        offset += page_size
        total = (page.get("paging") or {}).get("total", 0)
        if offset >= total:
            break
    return matches


def _summarize_item(item: dict) -> dict:
    """Versión compacta de un item ML — solo lo importante para humanos."""
    shipping = item.get("shipping") or {}
    summary = {
        "id": item.get("id"),
        "title": item.get("title"),
        "permalink": item.get("permalink"),
        "price": item.get("price"),
        "currency": item.get("currency_id"),
        "available_quantity": item.get("available_quantity"),
        "sold_quantity": item.get("sold_quantity"),
        "initial_quantity": item.get("initial_quantity"),
        "status": item.get("status"),
        "listing_type_id": item.get("listing_type_id"),
        "category_id": item.get("category_id"),
        "domain_id": item.get("domain_id"),
        "condition": item.get("condition"),
        "free_shipping": shipping.get("free_shipping"),
        "logistic_type": shipping.get("logistic_type"),
        "date_created": item.get("date_created"),
        "last_updated": item.get("last_updated"),
        "seller_custom_field": item.get("seller_custom_field"),
        "skus_detected": _extract_skus_from_item(item),
    }
    # Atributos clave (marca, color, material, género, talle, modelo, sku oficial)
    keep_attrs = {"BRAND", "COLOR", "MATERIAL", "GENDER", "SIZE", "MODEL", "SELLER_SKU", "PACKAGE_LENGTH", "PACKAGE_WIDTH", "PACKAGE_HEIGHT"}
    attrs = {}
    for a in item.get("attributes") or []:
        aid = (a.get("id") or "").upper()
        if aid in keep_attrs and a.get("value_name"):
            attrs[aid] = a.get("value_name")
    if attrs:
        summary["attributes"] = attrs
    # Variaciones (resumen)
    vars_ = item.get("variations") or []
    if vars_:
        summary["variations_count"] = len(vars_)
    # Cantidad de fotos
    pics = item.get("pictures") or []
    if pics:
        summary["pictures_count"] = len(pics)
    return summary


@mcp.tool()
def search_items_by_sku(sku: str) -> str:
    """Buscar items del seller por SKU. Devuelve lista de items completos.

    Hace fallback automático: si el endpoint nativo no encuentra el SKU
    (porque está solo en attributes[SELLER_SKU] o en variations), lista todos
    los items activos del seller y filtra por las 3 ubicaciones posibles.

    NOTA: para info compacta usá find_item_by_sku — esta tool devuelve
    objetos full y puede ser pesada.
    """
    items = _find_items_by_sku(sku)
    return _fmt({"sku": sku, "count": len(items), "items": items})


@mcp.tool()
def find_item_by_sku(sku: str) -> str:
    """Buscar items del seller por SKU y devolver SOLO un resumen compacto
    (id, title, price, stock, status, permalink, atributos clave).

    Es el modo recomendado para "dame info de la publi con SKU X".
    Mucho más liviano que search_items_by_sku + get_item.

    Hace búsqueda robusta: prueba el endpoint nativo y si no encuentra,
    pagina todos los items activos y filtra client-side por seller_custom_field,
    attributes[SELLER_SKU] y variations[].seller_custom_field.
    """
    items = _find_items_by_sku(sku)
    summaries = [_summarize_item(it) for it in items]
    return _fmt({"sku": sku, "count": len(summaries), "items": summaries})


@mcp.tool()
def get_item(item_id: str, include_description: bool = False) -> str:
    """Get full item details. Por default NO incluye description (es larga).
    Pasar include_description=True solo si la necesitás explícitamente."""
    item = ml.get(f"/items/{item_id}")
    if include_description:
        try:
            desc = ml.get(f"/items/{item_id}/description")
            item["description"] = desc
        except Exception:
            item["description"] = None
    return _fmt(item)


@mcp.tool()
def get_item_summary(item_id: str) -> str:
    """Resumen compacto de un item: solo los campos importantes (~25 líneas).
    Usar esta tool en vez de get_item cuando solo querés info rápida y no
    necesitás description, todos los attributes, sale_terms, etc."""
    item = ml.get(f"/items/{item_id}")
    return _fmt(_summarize_item(item))


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


@mcp.tool()
def set_item_campaign(item_id: str, campaign_id: int, status: str = "active") -> str:
    """Assign an item to a Product Ads campaign (or update its ad status).
    campaign_id: the campaign ID (e.g. 355566060).
    status: 'active' or 'paused'."""
    return _fmt(ml.put(f"/advertising/product_ads/items/{item_id}", {
        "campaign_id": campaign_id,
        "status": status,
    }))


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
# COMPACT TOOLS — versiones resumidas para evitar inflar contexto
# ===========================================================================
#
# Patrón: cada tool _summary devuelve solo los campos importantes para
# decisiones humanas (típicamente ~30-50 líneas vs 200+ del raw). Usalas
# por default cuando solo necesites "info rápida" — las versiones full
# siguen disponibles si necesitás detalles específicos.

def _summarize_order(order: dict) -> dict:
    """Resumen compacto de una order de ML."""
    items = []
    for oi in order.get("order_items") or []:
        item = oi.get("item") or {}
        items.append({
            "item_id": item.get("id"),
            "title": item.get("title"),
            "variation_id": item.get("variation_id"),
            "seller_sku": item.get("seller_sku") or item.get("seller_custom_field"),
            "quantity": oi.get("quantity"),
            "unit_price": oi.get("unit_price"),
            "sale_fee": oi.get("sale_fee"),
        })
    payments = order.get("payments") or []
    first_payment = payments[0] if payments else {}
    buyer = order.get("buyer") or {}
    shipping = order.get("shipping") or {}
    return {
        "id": order.get("id"),
        "date_created": order.get("date_created"),
        "date_closed": order.get("date_closed"),
        "status": order.get("status"),
        "status_detail": order.get("status_detail"),
        "total_amount": order.get("total_amount"),
        "paid_amount": order.get("paid_amount"),
        "currency": order.get("currency_id"),
        "buyer": {
            "id": buyer.get("id"),
            "nickname": buyer.get("nickname"),
        },
        "items": items,
        "payment_id": first_payment.get("id"),
        "payment_method": first_payment.get("payment_method_id"),
        "payment_status": first_payment.get("status"),
        "shipping_id": shipping.get("id"),
        "shipping_status": shipping.get("status"),
    }


def _summarize_question(q: dict) -> dict:
    """Resumen compacto de una question."""
    answer = q.get("answer") or {}
    sender = q.get("from") or {}
    return {
        "id": q.get("id"),
        "text": q.get("text"),
        "status": q.get("status"),
        "date_created": q.get("date_created"),
        "item_id": q.get("item_id"),
        "from_id": sender.get("id"),
        "from_nickname": sender.get("nickname"),
        "answer_text": answer.get("text") if answer else None,
        "answer_date": answer.get("date_created") if answer else None,
    }


def _summarize_search_result(item: dict) -> dict:
    """Resumen compacto de un item devuelto por /sites/{site}/search (público)."""
    shipping = item.get("shipping") or {}
    seller = item.get("seller") or {}
    return {
        "id": item.get("id"),
        "title": item.get("title"),
        "permalink": item.get("permalink"),
        "price": item.get("price"),
        "currency": item.get("currency_id"),
        "available_quantity": item.get("available_quantity"),
        "sold_quantity": item.get("sold_quantity"),
        "condition": item.get("condition"),
        "listing_type_id": item.get("listing_type_id"),
        "category_id": item.get("category_id"),
        "free_shipping": shipping.get("free_shipping"),
        "seller_id": seller.get("id"),
        "seller_nickname": seller.get("nickname"),
    }


def _summarize_billing_doc(doc: dict) -> dict:
    """Resumen compacto de un documento de billing (los arrays de detalles
    son enormes y casi nunca importan)."""
    return {k: v for k, v in doc.items() if not isinstance(v, list)}


@mcp.tool()
def list_items_summary(
    status: str = "active",
    offset: int = 0,
    limit: int = 50,
    sort: str = "last_updated_desc",
) -> str:
    """Lista items del seller con resumen compacto (~30 campos por item).
    Mucho más liviano que list_items. Usar esta tool por default."""
    params = {"status": status, "offset": offset, "limit": limit, "sort": sort}
    search = ml.get(f"/users/{ml.user_id}/items/search", params=params)
    ids = search.get("results", []) or []
    if not ids:
        return _fmt({"total": (search.get("paging") or {}).get("total", 0), "items": []})
    summaries: list[dict] = []
    for i in range(0, len(ids), 20):
        batch = ",".join(ids[i : i + 20])
        for entry in ml.get(f"/items?ids={batch}"):
            body = entry.get("body") if isinstance(entry, dict) else None
            if body:
                summaries.append(_summarize_item(body))
    return _fmt({
        "total": (search.get("paging") or {}).get("total", 0),
        "count": len(summaries),
        "items": summaries,
    })


@mcp.tool()
def list_orders_summary(
    status: str = "",
    date_from: str = "",
    date_to: str = "",
    offset: int = 0,
    limit: int = 50,
    sort: str = "date_desc",
) -> str:
    """Lista orders del seller con resumen compacto (id, fecha, comprador,
    total, status, items con sku/cantidad/precio, payment, shipping).
    Mucho más liviano que list_orders."""
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
    data = ml.get("/orders/search", params=params)
    results = data.get("results") or []
    summaries = [_summarize_order(o) for o in results]
    return _fmt({
        "total": (data.get("paging") or {}).get("total", 0),
        "count": len(summaries),
        "orders": summaries,
    })


@mcp.tool()
def get_order_summary(order_id: str) -> str:
    """Resumen compacto de una order. Usar en vez de get_order cuando solo
    necesitás info rápida (sin shipping detail completo, sin tags, etc)."""
    order = ml.get(f"/orders/{order_id}")
    return _fmt(_summarize_order(order))


@mcp.tool()
def search_by_seller_summary(
    seller_id: int,
    site_id: str = "MLA",
    offset: int = 0,
    limit: int = 50,
) -> str:
    """Búsqueda pública de items por seller con resumen compacto.
    Mucho más liviano que search_by_seller."""
    data = ml.get(f"/sites/{site_id}/search", params={
        "seller_id": seller_id, "offset": offset, "limit": limit,
    })
    results = data.get("results") or []
    summaries = [_summarize_search_result(it) for it in results]
    return _fmt({
        "total": (data.get("paging") or {}).get("total", 0),
        "count": len(summaries),
        "items": summaries,
    })


@mcp.tool()
def list_questions_summary(
    item_id: str = "",
    status: str = "UNANSWERED",
    offset: int = 0,
    limit: int = 50,
    sort: str = "DATE_CREATED_DESC",
) -> str:
    """Lista preguntas del seller con resumen compacto (texto, estado,
    item, comprador, respuesta si existe). Mucho más liviano que
    list_questions."""
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
    data = ml.get("/questions/search", params=params)
    questions = data.get("questions") or []
    summaries = [_summarize_question(q) for q in questions]
    return _fmt({
        "total": data.get("total", len(summaries)),
        "count": len(summaries),
        "questions": summaries,
    })


@mcp.tool()
def get_billing_detail_summary(period_key: str, group: str = "ML") -> str:
    """Resumen compacto del billing de un período: solo los totales y
    metadata de cada documento, sin los arrays de detalle internos
    (que son enormes). Mucho más liviano que get_billing_detail."""
    data = ml.get(
        f"/billing/integration/periods/key/{period_key}/documents?group={group}"
    )
    docs = data.get("documents") or data if isinstance(data, list) else (data.get("documents") or [])
    if not isinstance(docs, list):
        # estructura inesperada — devolver tal cual
        return _fmt(data)
    return _fmt({
        "period_key": period_key,
        "group": group,
        "count": len(docs),
        "documents": [_summarize_billing_doc(d) for d in docs],
    })


# ===========================================================================
# Run
# ===========================================================================

if __name__ == "__main__":
    mcp.run(transport="stdio")
