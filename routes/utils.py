from bson import ObjectId
from flask import request, jsonify, session, redirect
from functools import wraps

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
