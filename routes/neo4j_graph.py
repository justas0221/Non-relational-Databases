from flask import Blueprint, jsonify, request
from neo4j_connection import run_cypher

neo4j_graph_bp = Blueprint("neo4j_graph", __name__)

# Helper: limit param with sane default
def _get_limit():
    try:
        return int(request.args.get("limit", 4))
    except ValueError:
        return 4


@neo4j_graph_bp.get("/api/graph/ping")
def neo4j_ping():
    """Simple health check: is Neo4j reachable."""
    try:
        rows = run_cypher("RETURN 1 AS ok")
        ok = bool(rows and rows[0].get("ok") == 1)
        return jsonify({"ok": ok}), 200 if ok else 500
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@neo4j_graph_bp.get("/api/graph/user/<user_id>/recommended-events")
def recommended_events_for_user(user_id):
    """
    Feature A #1:
    Rekomenduojame renginius vartotojui pagal kitus panašius vartotojus
    (User -> Event <- OtherUser -> OtherEvent).
    """
    limit = _get_limit()
    try:
        query = """
        MATCH (u:User {id: $userId})-[:ATTENDED|VIEWED]->(e:Event)
        WITH u, collect(DISTINCT e) AS userEvents

        MATCH (u)-[:ATTENDED|VIEWED]->(:Event)<-[:ATTENDED|VIEWED]-(other:User)
        MATCH (other)-[:ATTENDED|VIEWED]->(rec:Event)
        WHERE NOT rec IN userEvents
        RETURN rec.id   AS event_id,
               rec.title AS title,
               count(DISTINCT other) AS score
        ORDER BY score DESC
        LIMIT $limit
        """
        rows = run_cypher(query, {"userId": user_id, "limit": limit})
        return jsonify({"user_id": user_id, "recommendations": rows})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@neo4j_graph_bp.get("/api/graph/user/<user_id>/deep-recommendations")
def deep_recommendations_for_user(user_id):
    """
    Feature A #2:
    Gili (1..3 hop) rekomendacija per kelių šuolių kelius.
    """
    limit = _get_limit()
    try:
        query = """
        MATCH (u:User {id: $userId})
        MATCH path = (u)-[:ATTENDED|VIEWED*1..3]->(e:Event)
        WHERE NOT (u)-[:ATTENDED|VIEWED]->(e)
        RETURN e.id        AS event_id,
               e.title     AS title,
               length(path) AS distance,
               count(*)    AS score
        ORDER BY score DESC, distance ASC
        LIMIT $limit
        """
        rows = run_cypher(query, {"userId": user_id, "limit": limit})
        return jsonify({"user_id": user_id, "recommendations": rows})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@neo4j_graph_bp.get("/api/graph/event/<event_id>/similar-events")
def similar_events(event_id):
    """
    Feature A #3:
    Panašūs renginiai pagal bendrą auditoriją (event -> users -> kiti eventai).
    """
    limit = _get_limit()
    try:
        query = """
        MATCH (e:Event {id: $eventId})
        MATCH path = (e)<-[:ATTENDED|VIEWED*1..3]-(:User)-[:ATTENDED|VIEWED*1..3]->(other:Event)
        WHERE e <> other
        RETURN other.id   AS event_id,
               other.title AS title,
               count(path) AS score
        ORDER BY score DESC
        LIMIT $limit
        """
        rows = run_cypher(query, {"eventId": event_id, "limit": limit})
        return jsonify({"event_id": event_id, "similar_events": rows})
    except Exception as e:
        return jsonify({"error": str(e)}), 500