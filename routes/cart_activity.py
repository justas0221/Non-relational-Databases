from flask import Blueprint, jsonify
from datetime import datetime, timezone
from cassandra_connection import execute_cql, query_cql
import uuid

cart_activity_bp = Blueprint('cart_activity', __name__)

def track_cart_activity(user_id, action, ticket_id, event_id=None, ticket_type=None, ticket_price=None, ticket_seat=None):
    """Track cart add/remove actions in Cassandra"""
    try:
        activity_time = datetime.now(timezone.utc).isoformat()
        activity_id = str(uuid.uuid1())
        
        # Batch both inserts into single subprocess call for better performance
        if event_id:
            batch_cql = f"""BEGIN BATCH
                INSERT INTO ticket_marketplace.cart_activity_by_user 
                (user_id, activity_time, activity_id, action, ticket_id, event_id, ticket_type, ticket_price, ticket_seat)
                VALUES ('{user_id}', '{activity_time}', {activity_id}, '{action}', '{ticket_id}', '{event_id}', '{ticket_type or ''}', {ticket_price or 0}, '{ticket_seat or ''}')
                USING TTL 2592000;
                INSERT INTO ticket_marketplace.cart_activity_by_event 
                (event_id, activity_time, activity_id, user_id, action, ticket_id, ticket_type, ticket_price, ticket_seat)
                VALUES ('{event_id}', '{activity_time}', {activity_id}, '{user_id}', '{action}', '{ticket_id}', '{ticket_type or ''}', {ticket_price or 0}, '{ticket_seat or ''}')
                USING TTL 2592000;
                APPLY BATCH;"""
            # Execute async so it doesn't block the HTTP response
            execute_cql(batch_cql, async_mode=True)
        else:
            # Just insert into user table if no event_id
            cql = f"""INSERT INTO ticket_marketplace.cart_activity_by_user 
                (user_id, activity_time, activity_id, action, ticket_id, event_id, ticket_type, ticket_price, ticket_seat)
                VALUES ('{user_id}', '{activity_time}', {activity_id}, '{action}', '{ticket_id}', '', '', {ticket_price or 0}, '')
                USING TTL 2592000;"""
            execute_cql(cql, async_mode=True)
            
    except Exception as e:
        print(f"Error tracking cart activity: {e}")


@cart_activity_bp.get('/api/cart-activity/user/<user_id>')
def get_user_cart_activity(user_id):
    """Get cart activity for a specific user"""
    try:
        cql = f"SELECT activity_time, action, ticket_id, event_id, ticket_type, ticket_price, ticket_seat FROM ticket_marketplace.cart_activity_by_user WHERE user_id = '{user_id}' LIMIT 100;"
        rows = query_cql(cql)
        
        activities = []
        for row in rows:
            activities.append({
                'activity_time': row.get('activity_time'),
                'action': row.get('action'),
                'ticket_id': row.get('ticket_id'),
                'event_id': row.get('event_id'),
                'ticket_type': row.get('ticket_type'),
                'ticket_price': row.get('ticket_price'),
                'ticket_seat': row.get('ticket_seat')
            })
        
        return jsonify({'user_id': user_id, 'activities': activities})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@cart_activity_bp.get('/api/cart-activity/event/<event_id>')
def get_event_cart_activity(event_id):
    """Get cart activity for a specific event"""
    try:
        cql = f"SELECT activity_time, user_id, action, ticket_id, ticket_type, ticket_price, ticket_seat FROM ticket_marketplace.cart_activity_by_event WHERE event_id = '{event_id}' LIMIT 100;"
        rows = query_cql(cql)
        
        activities = []
        for row in rows:
            activities.append({
                'activity_time': row.get('activity_time'),
                'user_id': row.get('user_id'),
                'action': row.get('action'),
                'ticket_id': row.get('ticket_id'),
                'ticket_type': row.get('ticket_type'),
                'ticket_price': row.get('ticket_price'),
                'ticket_seat': row.get('ticket_seat')
            })
        
        return jsonify({'event_id': event_id, 'activities': activities})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
