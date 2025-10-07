from flask import Flask, request, jsonify
from pymongo import MongoClient
from bson import ObjectId
from bson.int64 import Int64
from datetime import datetime, timezone
import os
from dotenv import load_dotenv
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME", "ticket_marketplace")

app = Flask(__name__)

client = MongoClient(MONGO_URI)
db = client[DB_NAME]

def oid(x):
    try:
        return ObjectId(x) if isinstance(x, str) else x
    except Exception:
        return None

def serialize(doc):
    if not doc:
        return doc
    doc["_id"] = str(doc["_id"])
    for k in ("userId", "organizerId", "venueId", "eventId"):
        if k in doc and isinstance(doc[k], ObjectId):
            doc[k] = str(doc[k])
    if "items" in doc:
        for it in doc["items"]:
            if "ticketId" in it and isinstance(it["ticketId"], ObjectId):
                it["ticketId"] = str(it["ticketId"])
            if "price" in it:
                it["price"] = int(it["price"])
    if "totalPrice" in doc:
        doc["totalPrice"] = int(doc["totalPrice"])
    if "payment" in doc and "totalAmount" in doc["payment"]:
        doc["payment"]["totalAmount"] = int(doc["payment"]["totalAmount"])
    return doc

def parse_int(name, default, min_v=1, max_v=1000):
    try:
        v = int(request.args.get(name, default))
        v = max(min_v, min(v, max_v))
    except Exception:
        v = default
    return v

@app.get("/")
def home():
    return {
        "status": "ok",
        "endpoints": [
            "GET  /events?organizerId=&venueId=&dateFrom=&dateTo=&q=&sort=&dir=&page=&limit=",
            "GET  /tickets?eventId=&type=&sort=&dir=&page=&limit=",
            "POST /orders  (body: {userId, items:[{ticketId}]})",
            "GET  /orders/<id>",
            "PATCH /orders/<id>/pay",
            "PATCH /orders/<id>/cancel",
            "GET  /analytics/top-events?limit=",
            "GET  /analytics/availability"
        ]
    }

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/events")
def list_events():
    """
    Filters: organizerId, venueId, dateFrom, dateTo, q (regex on title)
    Sort: sort=eventDate|title, dir=asc|desc
    Pagination: page (1..), limit (1..200)
    """
    q = {}
    if v := request.args.get("organizerId"):
        _v = oid(v)
        if not _v: return jsonify({"error":"invalid organizerId"}), 400
        q["organizerId"] = _v
    if v := request.args.get("venueId"):
        _v = oid(v)
        if not _v: return jsonify({"error":"invalid venueId"}), 400
        q["venueId"] = _v

    date_from = request.args.get("dateFrom")
    date_to = request.args.get("dateTo")
    if date_from or date_to:
        q["eventDate"] = {}
        if date_from:
            q["eventDate"]["$gte"] = datetime.fromisoformat(date_from)
        if date_to:
            q["eventDate"]["$lte"] = datetime.fromisoformat(date_to)

    if v := request.args.get("q"):
        q["title"] = {"$regex": v, "$options": "i"}

    sort_field = request.args.get("sort", "eventDate")
    dir_ = 1 if request.args.get("dir", "asc") == "asc" else -1
    page = parse_int("page", 1, 1, 1_000_000)
    limit = parse_int("limit", 20, 1, 200)
    skip = (page - 1) * limit

    total = db.events.count_documents(q)
    cursor = db.events.find(q).sort(sort_field, dir_).skip(skip).limit(limit)
    data = [serialize(d) for d in cursor]
    return jsonify({"data": data, "meta": {"page": page, "limit": limit, "total": total}})

@app.get("/tickets")
def list_tickets():
    """
    Required: eventId
    Optional: type=GA|seat
    Sort: sort=price|seat, dir=asc|desc
    Pagination: page, limit
    """
    event_id = request.args.get("eventId")
    if not event_id:
        return jsonify({"error":"eventId is required"}), 400
    _event = oid(event_id)
    if not _event:
        return jsonify({"error":"invalid eventId"}), 400

    q = {"eventId": _event}
    if v := request.args.get("type"):
        if v not in ("GA", "seat"):
            return jsonify({"error":"type must be GA or seat"}), 400
        q["type"] = v

    sort_field = request.args.get("sort", "price")
    dir_ = 1 if request.args.get("dir", "asc") == "asc" else -1
    page = parse_int("page", 1, 1, 1_000_000)
    limit = parse_int("limit", 50, 1, 500)
    skip = (page - 1) * limit

    total = db.tickets.count_documents(q)
    cursor = db.tickets.find(q).sort(sort_field, dir_).skip(skip).limit(limit)
    data = [serialize(d) for d in cursor]
    return jsonify({"data": data, "meta": {"page": page, "limit": limit, "total": total}})

@app.post("/orders")
def create_order():
    """
    Body:
    {
      "userId": "...",
      "items": [{"ticketId":"..."}, {"ticketId":"..."}]
    }
    Server-side:
      - validate user
      - load tickets by ids
      - check conflicts (tickets already in paid/pending orders)
      - compute total from DB prices; fill type/seat from DB
    """
    data = request.get_json(silent=True) or {}
    user_id = data.get("userId")
    items_in = data.get("items", [])

    if not user_id or not items_in:
        return jsonify({"error":"userId and items are required"}), 400

    _user = oid(user_id)
    if not _user or not db.users.find_one({"_id": _user}, {"_id":1}):
        return jsonify({"error":"user not found"}), 404

    ticket_ids = []
    for it in items_in:
        tid = oid(it.get("ticketId"))
        if not tid:
            return jsonify({"error":"invalid ticketId in items"}), 400
        ticket_ids.append(tid)

    tickets = list(db.tickets.find({"_id": {"$in": ticket_ids}},
                                   {"price":1, "type":1, "seat":1}))
    if len(tickets) != len(ticket_ids):
        found = {t["_id"] for t in tickets}
        missing = [str(t) for t in ticket_ids if t not in found]
        return jsonify({"error":"some tickets not found", "missing": missing}), 404

    conflicts = db.orders.aggregate([
        {"$match": {"status": {"$in": ["paid", "pending"]}}},
        {"$unwind": "$items"},
        {"$match": {"items.ticketId": {"$in": ticket_ids}}},
        {"$group": {"_id": "$items.ticketId"}}
    ])
    conflict_ids = [str(c["_id"]) for c in conflicts]
    if conflict_ids:
        return jsonify({
            "error": "some tickets are already reserved/sold",
            "conflicts": conflict_ids
        }), 409

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
    return jsonify(serialize(created)), 201

@app.get("/orders/<order_id>")
def get_order(order_id):
    _id = oid(order_id)
    if not _id:
        return jsonify({"error":"invalid id"}), 400
    doc = db.orders.find_one({"_id": _id})
    if not doc:
        return jsonify({"error":"not found"}), 404
    return jsonify(serialize(doc))

@app.patch("/orders/<order_id>/pay")
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
    return jsonify(serialize(res))

@app.patch("/orders/<order_id>/cancel")
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

@app.get("/analytics/top-events")
def top_events():
    limit = parse_int("limit", 10, 1, 100)
    pipeline = [
        {"$match": {"status": "paid"}},
        {"$unwind": "$items"},
        {"$group": {"_id": "$items.ticketId", "revenue": {"$sum": "$items.price"}}},
        {"$lookup": {"from": "tickets", "localField": "_id", "foreignField": "_id", "as": "t"}},
        {"$unwind": "$t"},
        {"$group": {"_id": "$t.eventId", "revenue": {"$sum": "$revenue"}, "ticketsSold": {"$sum": 1}}},
        {"$lookup": {"from": "events", "localField": "_id", "foreignField": "_id", "as": "event"}},
        {"$unwind": "$event"},
        {"$project": {
            "_id": 0,
            "eventId": {"$toString": "$_id"},
            "title": "$event.title",
            "eventDate": "$event.eventDate",
            "revenue": 1,
            "ticketsSold": 1
        }},
        {"$sort": {"revenue": -1}},
        {"$limit": limit}
    ]
    return jsonify(list(db.orders.aggregate(pipeline)))

@app.get("/analytics/availability")
def availability():
    pipeline = [
        {"$match": {"status": "paid"}},
        {"$unwind": "$items"},
        {"$lookup": {
            "from": "tickets",
            "localField": "items.ticketId",
            "foreignField": "_id",
            "as": "t"
        }},
        {"$unwind": "$t"},
        {"$group": {"_id": "$t.eventId", "sold": {"$sum": 1}}},
        {"$lookup": {
            "from": "tickets",
            "let": {"ev": "$_id"},
            "pipeline": [
                {"$match": {"$expr": {"$eq": ["$eventId", "$$ev"]}}},
                {"$count": "total"}
            ],
            "as": "totals"
        }},
        {"$addFields": {"total": {"$ifNull": [{"$first": "$totals.total"}, 0]}}},
        {"$project": {"totals": 0}},
        {"$addFields": {"available": {"$subtract": ["$total", "$sold"]}}},
        {"$sort": {"available": -1}}
    ]
    data = list(db.orders.aggregate(pipeline))
    for d in data:
        d["eventId"] = str(d.pop("_id"))
    return jsonify(data)

if __name__ == "__main__":
    app.run(debug=True)
