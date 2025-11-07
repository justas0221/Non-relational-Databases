from flask import Blueprint, request, jsonify, session, redirect
from .utils import login_required, organizer_required

auth = Blueprint('auth', __name__)

def init_auth(app, db):
    """Initialize auth routes with database connection"""
    
    @auth.get("/login")
    def login_page():
        if session.get('user_id'):
            return redirect('/ui')
        return app.send_static_file("ui/login.html")

    @auth.post("/auth/login")
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

    @auth.post("/auth/logout")
    def auth_logout():
        session.clear()
        return jsonify({"ok": True})

    @auth.get("/auth/me")
    def auth_me():
        if 'user_id' not in session:
            return jsonify({"authenticated": False}), 200
        return jsonify({
            "authenticated": True,
            "userId": session.get('user_id'),
            "userType": session.get('user_type')
        })

    @auth.get("/organizer/dashboard")
    @organizer_required
    def organizer_dashboard():
        return app.send_static_file("ui/organizer.html")
    
    @auth.get("/ui")
    @login_required
    def ui_index():
        return app.send_static_file("ui/events.html")

    @auth.get("/ui/event")
    @login_required
    def ui_event():
        return app.send_static_file("ui/event.html")
    
    return auth
