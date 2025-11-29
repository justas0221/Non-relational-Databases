import os, sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))  # add repo root
from neo4j_connection import run_cypher
user_id = "68ea8c121311767a7b59f6eb"
rows = run_cypher("""
MATCH (u:User {id: $uid})-[:ATTENDED]->(e)
RETURN e.id AS event_id, e.title AS title
""", {"uid": user_id})
print(rows)