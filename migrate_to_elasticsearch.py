import os
from pymongo import MongoClient
from dotenv import load_dotenv
from elasticsearch_connection import es_client

load_dotenv()

MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
client = MongoClient(MONGO_URI)
db = client['ticket_marketplace']

def clear_elasticsearch():
    print("Clearing Elasticsearch indices...")
    try:
        if es_client.indices.exists(index="events"):
            es_client.indices.delete(index="events")
        if es_client.indices.exists(index="venues"):
            es_client.indices.delete(index="venues")
        print("Elasticsearch cleared")
    except Exception as e:
        print(f"Error clearing: {e}")

def create_indices():
    print("Creating Elasticsearch indices...")
    
    events_mapping = {
        "mappings": {
            "properties": {
                "id": {"type": "keyword"},
                "title": {"type": "text", "analyzer": "standard"},
                "category": {"type": "keyword"},
                "venue_name": {"type": "text"},
                "venue_city": {"type": "keyword"},
                "event_date": {"type": "date"},
                "price": {"type": "float"}
            }
        }
    }
    
    venues_mapping = {
        "mappings": {
            "properties": {
                "id": {"type": "keyword"},
                "name": {"type": "text"},
                "city": {"type": "keyword"},
                "address": {"type": "text"}
            }
        }
    }
    
    try:
        es_client.indices.create(index="events", body=events_mapping)
        print("Created events index")
    except Exception as e:
        print(f"Error creating events index: {e}")
    
    try:
        es_client.indices.create(index="venues", body=venues_mapping)
        print("Created venues index")
    except Exception as e:
        print(f"Error creating venues index: {e}")

def migrate_venues():
    print("Migrating venues...")
    venues = list(db.venues.find({}))
    
    for venue in venues:
        venue_id = str(venue['_id'])
        doc = {
            "id": venue_id,
            "name": venue.get('name', ''),
            "city": venue.get('city', ''),
            "address": venue.get('address', '')
        }
        
        try:
            es_client.index(index="venues", id=venue_id, document=doc)
        except Exception as e:
            print(f"Error indexing venue {venue_id}: {e}")
    
    print(f"Migrated {len(venues)} venues")

def migrate_events():
    print("Migrating events...")
    events = list(db.events.find({}))
    print(f"Found {len(events)} events in MongoDB")
    
    event_count = 0
    for event in events:
        event_id = str(event['_id'])
        
        venue = db.venues.find_one({'_id': event.get('venueId')})
        venue_name = venue.get('name', '') if venue else ''
        venue_city = venue.get('city', '') if venue else ''
        
        tickets = list(db.tickets.find({'eventId': event['_id']}, {'price': 1}))
        min_price = min([float(t['price']) for t in tickets]) if tickets else 0.0
        
        doc = {
            "id": event_id,
            "title": event.get('title', ''),
            "category": event.get('category', ''),
            "venue_name": venue_name,
            "venue_city": venue_city,
            "event_date": event.get('eventDate').isoformat() if event.get('eventDate') else None,
            "price": min_price
        }
        
        try:
            es_client.index(index="events", id=event_id, document=doc)
            event_count += 1
        except Exception as e:
            print(f"Error indexing event {event_id}: {e}")
    
    print(f"Successfully indexed {event_count} events")

def verify_migration():
    print("Verifying migration...")
    
    try:
        es_client.indices.refresh(index="events")
        es_client.indices.refresh(index="venues")
        
        events_count = es_client.count(index="events")
        venues_count = es_client.count(index="venues")
        
        print(f"Events: {events_count['count']}")
        print(f"Venues: {venues_count['count']}")
    except Exception as e:
        print(f"Verification error: {e}")

if __name__ == '__main__':
    print("Starting Elasticsearch migration")
    
    try:
        clear_elasticsearch()
        create_indices()
        migrate_venues()
        migrate_events()
        verify_migration()
        
        print("Migration complete")
        
    except Exception as e:
        print(f"Migration failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        client.close()
