from flask import Flask, request, jsonify, send_from_directory, session, redirect
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError
from bson import ObjectId
from bson.int64 import Int64
from datetime import datetime, timezone
import os
from functools import wraps
from dotenv import load_dotenv
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME", "ticket_marketplace")

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")

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

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            if request.is_json:
                return jsonify({"error": "Authentication required"}), 401
            else:
                return redirect('/login')
        return f(*args, **kwargs)
    return decorated_function

def organizer_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('user_type') != 'organizer':
            if request.is_json:
                return jsonify({"error": "Organizer access required"}), 403
            else:
                return redirect('/login')
        return f(*args, **kwargs)
    return decorated_function

try:
    db.users.create_index([("email", 1)], unique=True)
except Exception:
    pass


@app.post("/users")
def create_user():
    data = request.get_json(silent=True) or {}
    name = data.get("name")
    email = data.get("email")
    phone = (data.get("phoneNumber") or "").strip()
    if not name or not email:
        return jsonify({"error": "name and email required"}), 400
    user = {"name": name, "email": email}
    if phone:
        user["phoneNumber"] = phone
    try:
        res = db.users.insert_one(user)
    except DuplicateKeyError:
        return jsonify({"error": "email already exists"}), 409
    created = db.users.find_one({"_id": res.inserted_id})
    return jsonify(serialize(created)), 201


@app.get("/users")
def list_users():
    page = parse_int("page", 1, 1, 1_000_000)
    limit = parse_int("limit", 20, 1, 200)
    skip = (page - 1) * limit

    q = {}

    has_phone = request.args.get("hasPhone")
    if has_phone is not None:
        v = has_phone.lower()
        if v in ("1", "true", "yes", "with"):
            q["$and"] = [
                {"phoneNumber": {"$exists": True}},
                {"phoneNumber": {"$ne": ""}},
                {"phoneNumber": {"$ne": None}}
            ]
        elif v in ("0", "false", "no", "without"):
            q["$or"] = [
                {"phoneNumber": {"$exists": False}},
                {"phoneNumber": ""},
                {"phoneNumber": None}
            ]

    if (s := request.args.get("q")):
        q["$or"] = q.get("$or", []) + [
            {"name": {"$regex": s, "$options": "i"}},
            {"email": {"$regex": s, "$options": "i"}}
        ]

    sort_field = request.args.get("sort", "name")
    dir_ = 1 if request.args.get("dir", "asc") == "asc" else -1

    total = db.users.count_documents(q)
    cursor = db.users.find(q).sort(sort_field, dir_).skip(skip).limit(limit)
    data = [serialize(d) for d in cursor]
    return jsonify({"data": data, "meta": {"page": page, "limit": limit, "total": total}})

@app.get("/users/<user_id>")
def get_user(user_id):
    _id = oid(user_id)
    if not _id:
        return jsonify({"error": "invalid id"}), 400
    doc = db.users.find_one({"_id": _id})
    if not doc:
        return jsonify({"error": "not found"}), 404
    return jsonify(serialize(doc))


@app.delete("/users/<user_id>")
def delete_user(user_id):
    _id = oid(user_id)
    if not _id:
        return jsonify({"error": "invalid id"}), 400
    res = db.users.delete_one({"_id": _id})
    if res.deleted_count == 0:
        return jsonify({"error": "not found"}), 404
    return jsonify({"ok": True}), 200

@app.patch("/users/<user_id>")
def update_user(user_id):
    _id = oid(user_id)
    if not _id:
        return jsonify({"error": "invalid id"}), 400
    data = request.get_json(silent=True) or {}
    set_ops = {}
    unset_ops = {}
    for k in ("name", "email", "phoneNumber"):
        if k in data:
            if k == "phoneNumber":
                val = data.get("phoneNumber")
                if isinstance(val, str):
                    val = val.strip()
                if not val:
                    unset_ops["phoneNumber"] = ""
                else:
                    set_ops["phoneNumber"] = val
            else:
                set_ops[k] = data[k]
    if not set_ops and not unset_ops:
        return jsonify({"error": "no fields to update"}), 400
    ops = {}
    if set_ops:
        ops["$set"] = set_ops
    if unset_ops:
        ops["$unset"] = unset_ops
    try:
        res = db.users.find_one_and_update({"_id": _id}, ops, return_document=True)
    except DuplicateKeyError:
        return jsonify({"error": "email already exists"}), 409
    if not res:
        return jsonify({"error": "not found"}), 404
    return jsonify(serialize(res))


@app.get("/ui/users")
@login_required
def ui_users():
    return app.send_static_file("ui/users.html")

@app.get("/ui")
@login_required
def ui_index():
    return app.send_static_file("ui/events.html")

@app.get("/ui/event")
@login_required
def ui_event():
    return app.send_static_file("ui/event.html")

@app.get("/login")
def login_page():
    if session.get('user_id'):
        return redirect('/ui')
    return app.send_static_file("ui/login.html")

@app.post("/auth/login")
def auth_login():
    data = request.get_json(silent=True) or {}
    email = (data.get('email') or '').strip().lower()
    if not email:
        return jsonify({"error": "email required"}), 400

    user = db.users.find_one({"email": email})
    user_type = 'user'
    if not user:
        org = db.organizers.find_one({"email": email}) if 'organizers' in db.list_collection_names() else None
        if not org:
            return jsonify({"error": "email not found"}), 404
        user = org
        user_type = 'organizer'

    session['user_id'] = str(user['_id'])
    session['user_type'] = user_type
    session.modified = True
    return jsonify({"ok": True, "userId": session['user_id'], "userType": user_type})

@app.post("/auth/logout")
def auth_logout():
    session.clear()
    return jsonify({"ok": True})

@app.get("/auth/me")
def auth_me():
    if 'user_id' not in session:
        return jsonify({"authenticated": False}), 200
    return jsonify({
        "authenticated": True,
        "userId": session.get('user_id'),
        "userType": session.get('user_type')
    })

@app.get("/organizer/dashboard")
@organizer_required
def organizer_dashboard():
    return app.send_static_file("ui/organizer.html")

@app.get("/venues")
def list_venues():
    try:
        venues = list(db.venues.find())
        return jsonify({"data": [serialize(v) for v in venues]})
    except Exception as e:
        return jsonify({"error": "Failed to load venues"}), 500

@app.post("/events")
@organizer_required
def create_event():
    data = request.get_json(silent=True) or {}
    
    title = (data.get('title') or '').strip()
    event_date_str = data.get('eventDate')
    venue_id = data.get('venueId')
    description = (data.get('description') or '').strip()
    
    if not title:
        return jsonify({"error": "title is required"}), 400
    if not event_date_str:
        return jsonify({"error": "eventDate is required"}), 400
    if not venue_id:
        return jsonify({"error": "venueId is required"}), 400
    
    try:
        event_date = datetime.fromisoformat(event_date_str.replace('Z', '+00:00'))
    except ValueError:
        return jsonify({"error": "invalid eventDate format"}), 400
    
    venue_oid = oid(venue_id)
    if not venue_oid or not db.venues.find_one({"_id": venue_oid}):
        return jsonify({"error": "venue not found"}), 404
    
    organizer_id = oid(session.get('user_id'))
    if not organizer_id:
        return jsonify({"error": "invalid session"}), 401
    
    event = {
        "title": title,
        "eventDate": event_date,
        "venueId": venue_oid,
        "organizerId": organizer_id
    }
    
    if description:
        event["description"] = description
    
    try:
        result = db.events.insert_one(event)
        created_event = db.events.find_one({"_id": result.inserted_id})
    except Exception as e:
        return jsonify({"error": "Failed to create event"}), 500

    try:
        ga_count = data.get('ticketCount', 100)
        ga_price = data.get('ticketPrice', 2500)
        ga_count = int(ga_count) if isinstance(ga_count, (int, str)) and str(ga_count).isdigit() else 100
        ga_price = int(ga_price) if isinstance(ga_price, (int, str)) and str(ga_price).isdigit() else 2500
        ticket_docs = [{
            "eventId": result.inserted_id,
            "type": "GA",
            "isGeneralAdmission": True,
            "price": ga_price,
        } for _ in range(ga_count)]
        if ticket_docs:
            db.tickets.insert_many(ticket_docs)
    except Exception as ticket_err:
        pass

    return jsonify(serialize(created_event)), 201

@app.get("/")
def home():
    if session.get('user_id'):
        return redirect('/ui')
    return redirect('/login')

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/events")
def list_events():
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

    reserved_ticket_ids = set()
    for o in db.orders.find({"status": {"$in": ["paid", "pending"]}}, {"items.ticketId": 1}):
        for it in o.get("items", []):
            tid = it.get("ticketId")
            if tid:
                reserved_ticket_ids.add(tid)

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


@app.post("/orders")
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
    return jsonify(serialize(result['order'])), 201

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
    return True, {"order": created}

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

@app.get("/cart")
@login_required
def get_cart():
    cart = session.get('cart', {})
    ticket_ids = [oid(t) for t in cart.get('tickets', []) if oid(t)]
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

@app.post("/cart/items")
@login_required
def add_to_cart():
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
        cart = session.get('cart') or {"tickets": []}
        added = 0
        for t in available_ga:
            sid = str(t['_id'])
            if sid not in cart['tickets']:
                cart['tickets'].append(sid)
                added += 1
            if added >= qty:
                break
        session['cart'] = cart
        session.modified = True
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
    cart = session.get('cart') or {"tickets": []}
    if str(tid) in cart['tickets']:
        return jsonify({"ok": True, "message": "already in cart"})
    cart['tickets'].append(str(tid))
    session['cart'] = cart
    session.modified = True
    return get_cart()

@app.delete("/cart/items/<ticket_id>")
@login_required
def remove_from_cart(ticket_id):
    cart = session.get('cart') or {"tickets": []}
    before = len(cart['tickets'])
    cart['tickets'] = [t for t in cart['tickets'] if t != ticket_id]
    session['cart'] = cart
    session.modified = True
    removed = before != len(cart['tickets'])
    return jsonify({"removed": removed})

@app.post("/cart/clear")
@login_required
def clear_cart():
    session['cart'] = {"tickets": []}
    session.modified = True
    return jsonify({"ok": True})

@app.post("/cart/checkout")
@login_required
def cart_checkout():
    cart = session.get('cart') or {"tickets": []}
    ticket_ids = [oid(t) for t in cart.get('tickets', []) if oid(t)]
    if not ticket_ids:
        return jsonify({"error": "cart is empty"}), 400
    ok, result = _create_order_internal(session.get('user_id'), ticket_ids)
    if not ok:
        return jsonify(result.get('body', {"error": "order_failed"})), result.get('status', 400)
    session['cart'] = {"tickets": []}
    session.modified = True
    return jsonify({"ok": True, "order": serialize(result['order'])}), 201

@app.get('/ui/cart')
@login_required
def ui_cart():
    return app.send_static_file('ui/cart.html')

if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)
