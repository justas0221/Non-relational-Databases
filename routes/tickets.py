from flask import Blueprint, request, jsonify
from .utils import oid, serialize
from redis_cache import cache

tickets = Blueprint('tickets', __name__)

def init_tickets(db):
    """Initialize ticket routes with database connection"""
    
    @tickets.get("/tickets")
    def list_tickets():
        event_id = request.args.get("eventId")
        if not event_id:
            return jsonify({"error": "eventId is required"}), 400
        _event = oid(event_id)
        if not _event:
            return jsonify({"error": "invalid eventId"}), 400

        q = {"eventId": _event}
        ttype = request.args.get("type")
        if ttype:
            ttype = ttype.strip()
            if ttype not in ("GA", "seat"):
                return jsonify({"error": "type must be GA or seat"}), 400
            q["type"] = ttype

        try:
            min_price = request.args.get("minPrice")
            max_price = request.args.get("maxPrice")
            if min_price or max_price:
                q["price"] = {}
                if min_price:
                    q["price"]["$gte"] = int(float(min_price) * 100)
                if max_price:
                    q["price"]["$lte"] = int(float(max_price) * 100)
        except ValueError:
            return jsonify({"error": "invalid price filter"}), 400

        seat = request.args.get("seat", "").strip().upper()
        if seat and seat != "ALL":
            if seat in ("GA", "GENERAL", "GENERAL ADMISSION"):
                q["$or"] = [
                    {"isGeneralAdmission": True},
                    {"type": {"$regex": r"^GA$", "$options": "i"}},
                    {"seat": {"$regex": r"^GA$", "$options": "i"}},
                ]
            else:
                q["$or"] = [
                    {"seat": {"$regex": f"^{seat}", "$options": "i"}},
                    {"type": {"$regex": f"^{seat}", "$options": "i"}},
                ]

        # 1. Reserved in ORDERS (paid/pending)
        reserved_ticket_ids = set()
        for o in db.orders.find({"status": {"$in": ["paid", "pending"]}}, {"items.ticketId": 1}):
            for it in o.get("items", []):
                tid = it.get("ticketId")
                if tid:
                    reserved_ticket_ids.add(tid)
        
        # 2. Reserved in CARTS (Redis Set members)
        if cache.redis_client:
            try:
                # Get all cart:* keys
                cart_keys = cache.redis_client.keys("cart:*")
                for cart_key in cart_keys:
                    # Get all ticket IDs from cart Set
                    ticket_ids_in_cart = cache.redis_client.smembers(cart_key)
                    for tid_str in ticket_ids_in_cart:
                        tid_decoded = tid_str.decode() if isinstance(tid_str, bytes) else tid_str
                        tid_obj = oid(tid_decoded)
                        if tid_obj:
                            reserved_ticket_ids.add(tid_obj)
            except Exception as e:
                print(f"Error checking cart reservations: {e}")

        tickets = list(db.tickets.find(q))
        available_tickets = [t for t in tickets if t["_id"] not in reserved_ticket_ids]

        ga_tickets = [t for t in available_tickets if t.get("isGeneralAdmission") or (t.get("type") and str(t.get("type")).upper() == "GA")]
        seat_tickets = [t for t in available_tickets if t not in ga_tickets]

        data = []
        if ga_tickets:
            price = ga_tickets[0].get("price", 0)
            data.append({
                "_id": "GA",
                "type": "GA",
                "seat": None,
                "price": round(price / 100, 2),
                "available": len(ga_tickets)
            })

        for t in seat_tickets:
            d = serialize(t)
            if "price" in d and d["price"] is not None:
                d["price"] = round(d["price"] / 100, 2)
            d["available"] = 1
            data.append(d)

        data.sort(key=lambda x: (0 if x["type"] == "GA" else 1, str(x.get("seat") or x.get("type") or "")))

        return jsonify({
            "data": data,
            "meta": {"total": len(data)}
        })
    
    return tickets
