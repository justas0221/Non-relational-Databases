from flask import Blueprint, request, jsonify, session
from bson.int64 import Int64
from datetime import datetime, timezone
from .utils import oid, serialize
from redis_cache import CacheInvalidator
from neo4j_connection import run_cypher

orders = Blueprint('orders', __name__)

def init_orders(db):
    """Initialize order routes with database connection"""

    def _push_order_to_neo4j(order_doc, tickets):
        """Create/refresh Neo4j ATTENDED edges for this order."""
        try:
            if not order_doc:
                return
            user_obj_id = order_doc.get("userId")
            if not user_obj_id:
                return
            user_id = str(user_obj_id)
            created_at = order_doc.get("orderDate")
            created_at_str = created_at.isoformat() if created_at else None

            event_obj_ids = {t.get("eventId") for t in tickets or [] if t.get("eventId")}
            if not event_obj_ids:
                return

            event_titles = {}
            for ev in db.events.find({"_id": {"$in": list(event_obj_ids)}}, {"title": 1}):
                event_titles[str(ev["_id"])] = ev.get("title", "Unknown event")

            for event_obj_id in event_obj_ids:
                event_id = str(event_obj_id)
                event_title = event_titles.get(event_id, "Unknown event")
                run_cypher(
                    """
                    MERGE (u:User {id: $user_id})
                    MERGE (e:Event {id: $event_id})
                    ON CREATE SET e.title = $event_title
                    MERGE (u)-[:ATTENDED {source: 'order', created_at: $created_at}]->(e)
                    """,
                    {
                        "user_id": user_id,
                        "event_id": event_id,
                        "event_title": event_title,
                        "created_at": created_at_str,
                    },
                )
        except Exception as neo_err:
            print(f"Neo4j order sync failed: {neo_err}")
    
    def _create_order_internal(user_id, ticket_ids):
        _user = oid(user_id)
        if not _user or not db.users.find_one({"_id": _user}, {"_id": 1}):
            return False, {"status": 404, "body": {"error": "user not found"}}
        if not ticket_ids:
            return False, {"status": 400, "body": {"error": "no tickets"}}

        ticket_ids = list(dict.fromkeys(ticket_ids))

        tickets = list(db.tickets.find({"_id": {"$in": ticket_ids}}, {"price": 1, "type": 1, "seat": 1, "eventId": 1}))
        if len(tickets) != len(ticket_ids):
            found = {t["_id"] for t in tickets}
            missing = [str(t) for t in ticket_ids if t not in found]
            return False, {"status": 404, "body": {"error": "some tickets not found", "missing": missing}}

        conflicts = db.orders.aggregate([
            {"$match": {"status": {"$in": ["paid", "pending"]}}},
            {"$unwind": "$items"},
            {"$match": {"items.ticketId": {"$in": ticket_ids}}},
            {"$group": {"_id": "$items.ticketId"}}
        ])
        conflict_ids = [str(c["_id"]) for c in conflicts]
        if conflict_ids:
            return False, {"status": 409, "body": {"error": "some tickets are already reserved/sold", "conflicts": conflict_ids}}

        items = []
        total = 0
        t_by_id = {t["_id"]: t for t in tickets}
        for tid in ticket_ids:
            t = t_by_id[tid]
            price_int = int(t["price"])
            total += price_int
            items.append({
                "ticketId": tid,
                "price": Int64(price_int),
                "type": t.get("type"),
                "seat": t.get("seat")
            })

        order = {
            "userId": _user,
            "orderDate": datetime.now(timezone.utc),
            "status": "pending",
            "totalPrice": Int64(total),
            "items": items,
            "payment": {
                "totalAmount": Int64(total),
                "status": "pending",
                "paidAt": None
            }
        }
        res = db.orders.insert_one(order)
        created = db.orders.find_one({"_id": res.inserted_id})
        
        try:
            from neo4j_connection import execute_cypher
            user_id = str(_user)
            for item in items:
                ticket_id = item.get('ticketId')
                if ticket_id:
                    ticket = db.tickets.find_one({'_id': ticket_id}, {'eventId': 1})
                    if ticket and ticket.get('eventId'):
                        event_id = str(ticket['eventId'])
                        execute_cypher(
                            """
                            MERGE (u:User {id: $userId})
                            MERGE (e:Event {id: $eventId})
                            MERGE (u)-[:BOUGHT]->(e)
                            """,
                            {"userId": user_id, "eventId": event_id}
                        )
        except Exception as e:
            print(f"Neo4j sync error: {e}")
        
        return True, {"order": created}
    
    @orders.post("/orders")
    def create_order():
        data = request.get_json(silent=True) or {}
        user_id = session.get('user_id') or data.get("userId")
        items_in = data.get("items", [])

        if not user_id or not items_in:
            return jsonify({"error": "userId and items are required"}), 400

        ticket_ids = []
        ga_qty = 0
        for it in items_in:
            tid = it.get("ticketId")
            if tid == "GA":
                qty = int(it.get("quantity", 1))
                if qty < 1:
                    return jsonify({"error": "Invalid GA quantity"}), 400
                ga_qty += qty
            else:
                tid_obj = oid(tid)
                if not tid_obj:
                    return jsonify({"error": "invalid ticketId in items"}), 400
                ticket_ids.append(tid_obj)

        # If GA requested, find available GA ticket IDs
        if ga_qty > 0:
            event_id = None
            if ticket_ids:
                t = db.tickets.find_one({"_id": ticket_ids[0]}, {"eventId": 1})
                if t:
                    event_id = t.get("eventId")
            if not event_id:
                event_id = data.get("eventId")
                if event_id:
                    event_id = oid(event_id)
            if not event_id:
                return jsonify({"error": "eventId required for GA tickets"}), 400
            reserved_ticket_ids = set()
            for o in db.orders.find({"status": {"$in": ["paid", "pending"]}}, {"items.ticketId": 1}):
                for it in o.get("items", []):
                    tid = it.get("ticketId")
                    if tid:
                        reserved_ticket_ids.add(tid)
            ga_tickets = list(db.tickets.find({
                "eventId": event_id,
                "$or": [
                    {"isGeneralAdmission": True},
                    {"type": {"$regex": r"^GA$", "$options": "i"}},
                    {"seat": {"$regex": r"^GA$", "$options": "i"}},
                ]
            }))
            available_ga = [t for t in ga_tickets if t["_id"] not in reserved_ticket_ids]
            if len(available_ga) < ga_qty:
                return jsonify({"error": "Not enough GA tickets available", "available": len(available_ga)}), 409
            ticket_ids.extend([t["_id"] for t in available_ga[:ga_qty]])

        ok, result = _create_order_internal(user_id, ticket_ids)
        if not ok:
            return jsonify(result.get('body', {"error": "order_failed"})), result.get('status', 400)
        CacheInvalidator.invalidate_order_related()
        return jsonify(serialize(result['order'])), 201

    @orders.get("/orders/<order_id>")
    def get_order(order_id):
        _id = oid(order_id)
        if not _id:
            return jsonify({"error":"invalid id"}), 400
        doc = db.orders.find_one({"_id": _id})
        if not doc:
            return jsonify({"error":"not found"}), 404
        return jsonify(serialize(doc))

    @orders.patch("/orders/<order_id>/pay")
    def pay_order(order_id):
        _id = oid(order_id)
        if not _id:
            return jsonify({"error":"invalid id"}), 400
        now = datetime.now(timezone.utc)
        res = db.orders.find_one_and_update(
            {"_id": _id, "status": "pending"},
            {"$set": {"status": "paid", "payment.status": "paid", "payment.paidAt": now}},
            return_document=True
        )
        if not res:
            return jsonify({"error":"order not pending or not found"}), 409
        
        CacheInvalidator.invalidate_order_related()
        return jsonify(serialize(res))

    @orders.patch("/orders/<order_id>/cancel")
    def cancel_order(order_id):
        _id = oid(order_id)
        if not _id:
            return jsonify({"error":"invalid id"}), 400
        res = db.orders.find_one_and_update(
            {"_id": _id, "status": {"$in": ["pending"]}},
            {"$set": {"status": "canceled", "payment.status": "failed", "payment.paidAt": None}},
            return_document=True
        )
        if not res:
            return jsonify({"error":"order not cancellable or not found"}), 409
        return jsonify(serialize(res))
    
    # Return both blueprint and internal function for cart to use
    return orders, _create_order_internal
