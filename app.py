from flask import Flask
from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME", "ticket_marketplace")

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")

client = MongoClient(MONGO_URI)
db = client[DB_NAME]

# Create unique index for users email
try:
    db.users.create_index([("email", 1)], unique=True)
except Exception:
    pass

# Import and register blueprints
from routes.auth import init_auth
from routes.users import init_users
from routes.events import init_events
from routes.tickets import init_tickets
from routes.orders import init_orders
from routes.cart import init_cart
from routes.analytics import init_analytics
from routes.debug import init_debug

# Initialize blueprints with db connection
auth_bp = init_auth(app, db)
users_bp = init_users(app, db)
events_bp = init_events(app, db)
tickets_bp = init_tickets(db)
orders_bp, create_order_internal = init_orders(db)
cart_bp = init_cart(app, db, create_order_internal)
analytics_bp = init_analytics(db)
debug_bp = init_debug()

# Register blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(users_bp)
app.register_blueprint(events_bp)
app.register_blueprint(tickets_bp)
app.register_blueprint(orders_bp)
app.register_blueprint(cart_bp)
app.register_blueprint(analytics_bp)
app.register_blueprint(debug_bp)

if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)
