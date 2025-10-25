from flask import Blueprint, request, jsonify
from pymongo.errors import DuplicateKeyError
from .utils import oid, serialize, parse_int, login_required

users = Blueprint('users', __name__)

def init_users(app, db):
    """Initialize user routes with database connection"""
    
    @users.post("/users")
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

    @users.get("/users")
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

    @users.get("/users/<user_id>")
    def get_user(user_id):
        _id = oid(user_id)
        if not _id:
            return jsonify({"error": "invalid id"}), 400
        doc = db.users.find_one({"_id": _id})
        if not doc:
            return jsonify({"error": "not found"}), 404
        return jsonify(serialize(doc))

    @users.delete("/users/<user_id>")
    def delete_user(user_id):
        _id = oid(user_id)
        if not _id:
            return jsonify({"error": "invalid id"}), 400
        res = db.users.delete_one({"_id": _id})
        if res.deleted_count == 0:
            return jsonify({"error": "not found"}), 404
        return jsonify({"ok": True}), 200

    @users.patch("/users/<user_id>")
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

    @users.get("/ui/users")
    @login_required
    def ui_users():
        return app.send_static_file("ui/users.html")
    
    return users
