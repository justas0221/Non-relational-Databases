from flask import Blueprint, jsonify
from .utils import parse_int
from redis_cache import cache

analytics = Blueprint('analytics', __name__)

def init_analytics(db):
    """Initialize analytics routes with database connection"""
    
    @analytics.get("/analytics/top-events")
    def top_events():
        limit = parse_int("limit", 100, 1, 1000)
        cache_key = f"analytics_top_events:{limit}"
        
        # Try to get from cache
        cached = cache.get(cache_key)
        if cached is not None:
            print(f"Cache HIT: analytics_top_events")
            return jsonify(cached)
        
        # Expensive aggregation
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
        result = list(db.orders.aggregate(pipeline))
        
        # Cache result
        cache.set(cache_key, result, 300)  # 5 min TTL
        print(f"Cache SAVE: analytics_top_events (TTL: 300s)")
        
        return jsonify(result)

    @analytics.get("/analytics/availability")
    def availability():
        cache_key = "analytics_availability"
        
        # Try to get from cache
        cached = cache.get(cache_key)
        if cached is not None:
            print(f"Cache HIT: analytics_availability")
            return jsonify(cached)
        
        # Expensive aggregation
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
        
        # Cache result
        cache.set(cache_key, data, 300)  # 5 min TTL
        print(f"Cache SAVE: analytics_availability (TTL: 300s)")
        
        return jsonify(data)
    
    return analytics
