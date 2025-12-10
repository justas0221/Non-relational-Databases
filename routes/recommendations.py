from flask import Blueprint, jsonify
from neo4j_connection import query_cypher

recommendations = Blueprint('recommendations', __name__)

def init_recommendations(app, db):
    
    @recommendations.get("/api/recommendations/user/<user_id>")
    def get_user_recommendations(user_id):
        query = """
        MATCH (me:User {id: $userId})-[:BOUGHT|VIEWED*1..3]-(similar:User)-[:BOUGHT]->(rec:Event)
        WHERE me <> similar AND NOT (me)-[:BOUGHT|VIEWED]->(rec)
        WITH rec, COUNT(DISTINCT similar) AS score
        ORDER BY score DESC
        LIMIT 10
        RETURN rec.id AS eventId, rec.title AS title, rec.category AS category, score
        """
        results = query_cypher(query, {"userId": user_id})
        return jsonify(results)
    
    @recommendations.get("/api/recommendations/user/<user_id>/nearby")
    def get_nearby_recommendations(user_id):
        query = """
        MATCH (me:User {id: $userId})-[:BOUGHT]->(myEvent:Event)
        WHERE myEvent.venueId IS NOT NULL
        WITH me, myEvent, myEvent.venueId AS myVenue
        MATCH (rec:Event)
        WHERE rec.venueId = myVenue 
          AND rec.id <> myEvent.id
          AND NOT (me)-[:BOUGHT|VIEWED]->(rec)
        WITH rec, COUNT(*) AS relevance
        ORDER BY relevance DESC
        LIMIT 10
        RETURN rec.id AS eventId, rec.title AS title, rec.category AS category, 
               rec.eventDate AS eventDate, rec.venueId AS venueId, relevance
        """
        results = query_cypher(query, {"userId": user_id})
        return jsonify(results)
    
    @recommendations.get("/api/recommendations/user/<user_id>/deep")
    def get_deep_recommendations(user_id):
        query = """
        MATCH (me:User {id: $userId})-[:BOUGHT]->(e:Event)<-[:BOUGHT]-(similar:User)
        WHERE me <> similar
        WITH me, similar, COUNT(e) AS similarity
        ORDER BY similarity DESC, similar.id ASC
        LIMIT 10
        MATCH (similar)-[:VIEWED]->(viewed:Event)-[:HAS_CATEGORY]->(c:Category)
        WITH me, similar, viewed, c
        WITH me, c, COUNT(viewed) AS categoryPopularity, collect(DISTINCT similar) AS viewingUsers
        ORDER BY categoryPopularity DESC
        LIMIT 3
        MATCH (c)<-[:HAS_CATEGORY]-(rec:Event)
        WHERE NOT (me)-[:BOUGHT|VIEWED]->(rec)
        WITH rec, c, viewingUsers
        UNWIND viewingUsers AS user
        OPTIONAL MATCH (user)-[:VIEWED]->(rec)
        WITH rec, COUNT(user) AS deepScore
        ORDER BY deepScore DESC
        LIMIT 10
        RETURN rec.id AS eventId, rec.title AS title, rec.category AS category, deepScore
        """
        results = query_cypher(query, {"userId": user_id})
        return jsonify(results)
    
    @recommendations.get("/api/recommendations/explain/<user_id>/<event_id>")
    def explain_recommendation(user_id, event_id):
        query = """
        MATCH path = shortestPath((me:User {id: $userId})-[*1..5]-(target:Event {id: $eventId}))
        RETURN [node IN nodes(path) | 
                CASE 
                    WHEN 'User' IN labels(node) THEN {type: 'User', id: node.id}
                    WHEN 'Event' IN labels(node) THEN {type: 'Event', id: node.id, title: node.title}
                    WHEN 'Category' IN labels(node) THEN {type: 'Category', name: node.name}
                END
        ] AS path, LENGTH(path) AS distance
        """
        results = query_cypher(query, {"userId": user_id, "eventId": event_id})
        if results:
            return jsonify(results[0])
        return jsonify({"error": "no path found"}), 404
    
    return recommendations
