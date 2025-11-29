import os
import sys
from dotenv import load_dotenv
from pymongo import MongoClient

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from neo4j_connection import run_cypher

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME", "ticket_marketplace")

client = MongoClient(MONGO_URI)
db = client[DB_NAME]

if __name__ == "__main__":
    run_cypher("MATCH (n) DETACH DELETE n")
    print("Neo4j: graph cleared.")

    orders = list(db.orders.find({}))
    print(f"Found {len(orders)} orders in MongoDB.")

    for o in orders:
        user_id = o.get("userId")
        items = o.get("items") or []
        if not user_id:
            continue

        for item in items:
            ticket_id = item.get("ticketId")
            if not ticket_id:
                continue

            ticket = db.tickets.find_one({"_id": ticket_id})
            if not ticket:
                continue

            event_id = ticket.get("eventId")
            if not event_id:
                continue

            event = db.events.find_one({"_id": event_id})
            event_title = (event or {}).get("title") or "Unknown event"

            cypher = """
            MERGE (u:User {id: $user_id})
            MERGE (e:Event {id: $event_id})
            ON CREATE SET e.title = $event_title
            MERGE (u)-[:ATTENDED {source: 'order'}]->(e)
            """
            run_cypher(
                cypher,
                {
                    "user_id": str(user_id),
                    "event_id": str(event_id),
                    "event_title": event_title,
                },
            )

    print("Neo4j: seeded ATTENDED relationships from orders.")