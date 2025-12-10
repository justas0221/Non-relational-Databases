from flask import Blueprint, request, jsonify, session, redirect
from datetime import datetime
from bson.int64 import Int64
from .utils import oid, serialize, parse_int, organizer_required
from redis_cache import CacheInvalidator
from routes.event_views import track_event_view

events = Blueprint('events', __name__)

def init_events(app, db):
    """Initialize event routes with database connection"""
    
    @events.get("/venues")
    def list_venues():
        try:
            venues = list(db.venues.find())
            return jsonify({"data": [serialize(v) for v in venues]})
        except Exception as e:
            return jsonify({"error": "Failed to load venues"}), 500

    @events.post("/events")
    @organizer_required
    def create_event():
        data = request.get_json(silent=True) or {}
        
        title = (data.get('title') or '').strip()
        event_date_str = data.get('eventDate')
        venue_id = data.get('venueId')
        category = data.get('category')
        description = (data.get('description') or '').strip()
        
        if not title:
            return jsonify({"error": "title is required"}), 400
        if not event_date_str:
            return jsonify({"error": "eventDate is required"}), 400
        if not venue_id:
            return jsonify({"error": "venueId is required"}), 400
        if not category:
            return jsonify({"error": "category is required"}), 400
        
        allowed_categories = ["Koncertai", "Sportas", "Teatras", "Komedija", "Festivalis"]
        if category not in allowed_categories:
            return jsonify({"error": "invalid category"}), 400
        
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
            "organizerId": organizer_id,
            "category": category
        }
        
        if description:
            event["description"] = description
        
        try:
            result = db.events.insert_one(event)
            created_event = db.events.find_one({"_id": result.inserted_id})
        except Exception as e:
            return jsonify({"error": "Failed to create event"}), 500

        # Automatically create tickets for the event
        try:
            ticket_docs = []
            
            # 1. Create 100 GA (General Admission) tickets
            ga_price = Int64(2500)  # 25.00 EUR
            for _ in range(100):
                ticket_docs.append({
                    "eventId": result.inserted_id,
                    "type": "GA",
                    "seat": None,
                    "price": ga_price,
                })
            
            # 2. Create 100 Seated tickets (numbered A1-A50, B1-B50)
            seated_price = Int64(3500)  # 35.00 EUR
            rows = ['A', 'B']
            seats_per_row = 50
            
            for row in rows:
                for seat_num in range(1, seats_per_row + 1):
                    ticket_docs.append({
                        "eventId": result.inserted_id,
                        "type": "seat",
                        "seat": f"{row}{seat_num}",
                        "price": seated_price,
                    })
            
            # Insert all tickets at once
            if ticket_docs:
                db.tickets.insert_many(ticket_docs)
                print(f"Created {len(ticket_docs)} tickets for event {result.inserted_id}")
        except Exception as ticket_err:
            print(f"Error creating tickets: {ticket_err}")
            pass

        # Sync to Neo4j
        try:
            from neo4j_connection import execute_cypher
            event_id = str(created_event['_id'])
            title = created_event.get('title', 'Untitled')
            category = created_event.get('category')
            venue_id = str(created_event['venueId']) if created_event.get('venueId') else None
            event_date = created_event.get('eventDate').isoformat() if created_event.get('eventDate') else None
            
            execute_cypher(
                "MERGE (e:Event {id: $id}) SET e.title = $title, e.category = $category, e.venueId = $venueId, e.eventDate = $eventDate",
                {"id": event_id, "title": title, "category": category, "venueId": venue_id, "eventDate": event_date}
            )
            
            if category:
                execute_cypher(
                    """
                    MERGE (c:Category {name: $category})
                    MERGE (e:Event {id: $eventId})
                    MERGE (e)-[:HAS_CATEGORY]->(c)
                    """,
                    {"category": category, "eventId": event_id}
                )
        except Exception as e:
            print(f"Neo4j sync error: {e}")

        # Invalidate analytics cache - new event affects availability stats
        CacheInvalidator.invalidate_order_related()

        return jsonify(serialize(created_event)), 201

    @events.get("/")
    def home():
        if session.get('user_id'):
            return redirect('/ui')
        return redirect('/login')

    @events.get("/health")
    def health():
        return {"status": "ok"}

    @events.get("/events")
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

    @events.get("/events/<event_id>")
    def get_event(event_id):
        _id = oid(event_id)
        if not _id:
            return jsonify({"error": "invalid event ID"}), 400
        
        event = db.events.find_one({"_id": _id})
        if not event:
            return jsonify({"error": "event not found"}), 404
        
        # Track event view in Cassandra
        try:
            user_id = session.get('user_id')
            if user_id:
                track_event_view(
                    user_id=str(user_id),
                    event_id=event_id,
                    event_title=event.get('title', ''),
                    view_type='detail'
                )
        except Exception as e:
            print(f"Cassandra tracking error: {e}")
        
        return jsonify(serialize(event))
    
    return events
