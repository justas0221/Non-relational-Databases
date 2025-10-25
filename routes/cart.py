from flask import Blueprint, request, jsonify, session
from .utils import oid, login_required
from redis_cache import cache, CacheInvalidator

cart = Blueprint('cart', __name__)

def init_cart(app, db, create_order_internal_fn):
    """Initialize cart routes with database connection and order function"""
    
    @cart.get("/cart")
    @login_required
    def get_cart():
        user_id = session.get('user_id')
        cart_key = f"cart:{user_id}"
        
        # Gauti visus ticket ID iš Redis Set
        ticket_ids_bytes = cache.redis_client.smembers(cart_key) if cache.redis_client else set()
        ticket_ids = [oid(t.decode() if isinstance(t, bytes) else t) for t in ticket_ids_bytes]
        ticket_ids = [t for t in ticket_ids if t]  # Filter None values
        
        if not ticket_ids:
            return jsonify({"items": [], "total": 0, "count": 0})
        
        tickets = list(db.tickets.find({"_id": {"$in": ticket_ids}}, {"price":1, "type":1, "seat":1, "eventId":1}))
        t_by_id = {t["_id"]: t for t in tickets}
        items = []
        total = 0
        for tid in ticket_ids:
            t = t_by_id.get(tid)
            if not t:
                continue
            price_int = int(t.get("price", 0))
            total += price_int
            items.append({
                "ticketId": str(tid),
                "type": t.get("type"),
                "seat": t.get("seat"),
                "price": round(price_int/100, 2),
                "eventId": str(t.get("eventId")) if t.get("eventId") else None
            })
        return jsonify({
            "items": items,
            "total": round(total/100, 2),
            "count": len(items)
        })

    @cart.post("/cart/items")
    @login_required
    def add_to_cart():
        user_id = session.get('user_id')
        cart_key = f"cart:{user_id}"
        data = request.get_json(silent=True) or {}
        raw_tid = data.get("ticketId")
        
        if raw_tid == 'GA':
            qty = int(data.get('quantity', 1))
            event_id = oid(data.get('eventId'))
            if not event_id:
                return jsonify({"error": "eventId required for GA"}), 400
            if qty < 1:
                return jsonify({"error": "quantity must be >=1"}), 400
            reserved_ticket_ids = set()
            for o in db.orders.find({"status": {"$in": ["paid", "pending"]}}, {"items.ticketId": 1}):
                for it in o.get("items", []):
                    tidx = it.get("ticketId")
                    if tidx:
                        reserved_ticket_ids.add(tidx)
            ga_tickets = list(db.tickets.find({
                "eventId": event_id,
                "$or": [
                    {"isGeneralAdmission": True},
                    {"type": {"$regex": r"^GA$", "$options": "i"}},
                    {"seat": {"$regex": r"^GA$", "$options": "i"}},
                ]
            }, {"_id":1}))
            available_ga = [t for t in ga_tickets if t['_id'] not in reserved_ticket_ids]
            if len(available_ga) < qty:
                return jsonify({"error": "not enough GA available", "available": len(available_ga)}), 409
            
            # Redis Set: pridėti GA bilietus
            added = 0
            for t in available_ga:
                sid = str(t['_id'])
                if not cache.redis_client.sismember(cart_key, sid):
                    cache.redis_client.sadd(cart_key, sid)
                    cache.redis_client.expire(cart_key, 900)  # 15 min TTL
                    added += 1
                if added >= qty:
                    break
            return get_cart()
        
        tid = oid(raw_tid)
        if not tid:
            return jsonify({"error": "invalid ticketId"}), 400
        t = db.tickets.find_one({"_id": tid}, {"_id":1})
        if not t:
            return jsonify({"error": "ticket not found"}), 404
        conflict = db.orders.find_one({
            "status": {"$in": ["paid", "pending"]},
            "items.ticketId": tid
        }, {"_id":1})
        if conflict:
            return jsonify({"error": "ticket already reserved/sold"}), 409
        
        # Redis Set: pridėti bilietą
        tid_str = str(tid)
        if cache.redis_client.sismember(cart_key, tid_str):
            return jsonify({"ok": True, "message": "already in cart"})
        
        cache.redis_client.sadd(cart_key, tid_str)
        cache.redis_client.expire(cart_key, 900)  # 15 min TTL
        return get_cart()

    @cart.delete("/cart/items/<ticket_id>")
    @login_required
    def remove_from_cart(ticket_id):
        user_id = session.get('user_id')
        cart_key = f"cart:{user_id}"
        
        # Redis Set: ištrinti bilietą
        removed = cache.redis_client.srem(cart_key, ticket_id) if cache.redis_client else 0
        return jsonify({"removed": bool(removed)})

    @cart.post("/cart/clear")
    @login_required
    def clear_cart():
        user_id = session.get('user_id')
        cart_key = f"cart:{user_id}"
        
        # Redis Hash: ištrinti visą krepšelį
        cache.redis_client.delete(cart_key) if cache.redis_client else None
        return jsonify({"ok": True})

    @cart.post("/cart/checkout")
    @login_required
    def cart_checkout():
        from .utils import serialize
        from datetime import datetime, timezone
        
        user_id = session.get('user_id')
        cart_key = f"cart:{user_id}"
        
        # Redis Set: gauti visus ticket IDs
        ticket_ids_bytes = cache.redis_client.smembers(cart_key) if cache.redis_client else set()
        ticket_ids = [oid(t.decode() if isinstance(t, bytes) else t) for t in ticket_ids_bytes]
        ticket_ids = [t for t in ticket_ids if t]
        
        if not ticket_ids:
            return jsonify({"error": "cart is empty"}), 400
        
        ok, result = create_order_internal_fn(user_id, ticket_ids)
        if not ok:
            return jsonify(result.get('body', {"error": "order_failed"})), result.get('status', 400)
        
        # Automatically mark order as paid
        order_id = result['order']['_id']
        now = datetime.now(timezone.utc)
        db.orders.update_one(
            {"_id": order_id},
            {"$set": {
                "status": "paid",
                "payment.status": "paid",
                "payment.paidAt": now
            }}
        )
        
        # Get updated order
        paid_order = db.orders.find_one({"_id": order_id})
        
        # Invalidate analytics cache (order created and paid)
        CacheInvalidator.invalidate_order_related()
        
        # Redis Set: išvalyti krepšelį po sėkmingo užsakymo
        cache.redis_client.delete(cart_key) if cache.redis_client else None
        return jsonify({"ok": True, "order": serialize(paid_order)}), 201

    @cart.get('/ui/cart')
    @login_required
    def ui_cart():
        return app.send_static_file('ui/cart.html')
    
    return cart
