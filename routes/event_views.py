from flask import Blueprint, jsonify
from datetime import datetime, timezone
from cassandra_connection import execute_cql, query_cql
import uuid

event_views_bp = Blueprint('event_views', __name__)

def track_event_view(user_id, event_id, event_title=None, view_type='detail'):
    """Track event page views in Cassandra"""
    try:
        view_time = datetime.now(timezone.utc).isoformat()
        view_id = str(uuid.uuid1())
        
        # Batch detail record inserts (regular inserts)
        batch_cql = f"""BEGIN BATCH
            INSERT INTO ticket_marketplace.event_view_by_user 
            (user_id, view_time, view_id, event_id, event_title, view_type)
            VALUES ('{user_id}', '{view_time}', {view_id}, '{event_id}', '{event_title or ''}', '{view_type}')
            USING TTL 2592000;
            INSERT INTO ticket_marketplace.event_view_by_event 
            (event_id, view_time, view_id, user_id, event_title, view_type)
            VALUES ('{event_id}', '{view_time}', {view_id}, '{user_id}', '{event_title or ''}', '{view_type}')
            USING TTL 2592000;
            APPLY BATCH;"""
        
        # Counter update must be separate
        counter_cql = f"""UPDATE ticket_marketplace.event_view_counter 
            SET view_count = view_count + 1 
            WHERE event_id = '{event_id}';"""
        
        # Execute both async so it doesn't block the HTTP response
        execute_cql(batch_cql, async_mode=True)
        execute_cql(counter_cql, async_mode=True)
            
    except Exception as e:
        print(f"Error tracking event view: {e}")


@event_views_bp.get('/api/event-views/user/<user_id>')
def get_user_event_views(user_id):
    """Get event views for a specific user"""
    try:
        cql = f"SELECT view_time, event_id, event_title, view_type FROM ticket_marketplace.event_view_by_user WHERE user_id = '{user_id}' LIMIT 100;"
        rows = query_cql(cql)
        
        views = []
        for row in rows:
            views.append({
                'view_time': row.get('view_time'),
                'event_id': row.get('event_id'),
                'event_title': row.get('event_title'),
                'view_type': row.get('view_type')
            })
        
        return jsonify({'user_id': user_id, 'views': views})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@event_views_bp.get('/api/event-views/event/<event_id>')
def get_event_views(event_id):
    """Get all views for a specific event"""
    try:
        cql = f"SELECT view_time, user_id, event_title, view_type FROM ticket_marketplace.event_view_by_event WHERE event_id = '{event_id}' LIMIT 100;"
        rows = query_cql(cql)
        
        views = []
        for row in rows:
            views.append({
                'view_time': row.get('view_time'),
                'user_id': row.get('user_id'),
                'event_title': row.get('event_title'),
                'view_type': row.get('view_type')
            })
        
        return jsonify({'event_id': event_id, 'views': views})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@event_views_bp.get('/api/event-views/event/<event_id>/count')
def get_event_views_count(event_id):
    """Get view count for a specific event"""
    try:
        cql = f"SELECT COUNT(*) as view_count FROM ticket_marketplace.event_view_by_event WHERE event_id = '{event_id}';"
        rows = query_cql(cql)
        
        count = int(rows[0].get('view_count', 0)) if rows else 0
        return jsonify({'event_id': event_id, 'view_count': count})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@event_views_bp.get('/api/event-views/top-events')
def get_top_viewed_events():
    """Get most viewed events from Cassandra counter table"""
    try:
        from flask import request
        limit = int(request.args.get('limit', 10))
        
        # Query counter table - get all view counts
        cql = "SELECT event_id, view_count FROM ticket_marketplace.event_view_counter;"
        rows = query_cql(cql)
        
        if not rows:
            return jsonify([])
        
        # Get all event_ids
        event_ids = [row.get('event_id', '').strip() for row in rows if row.get('event_id')]
        
        # Build title lookup map by querying titles for each event
        title_map = {}
        for event_id in event_ids:
            title_cql = f"SELECT event_id, event_title, view_type FROM ticket_marketplace.event_view_by_event WHERE event_id = '{event_id}' LIMIT 1;"
            title_rows = query_cql(title_cql)
            title_map[event_id] = title_rows[0].get('event_title', '').strip() if title_rows else 'Unknown Event'
        
        # Build list with counts and titles
        event_counts = []
        for row in rows:
            event_id = row.get('event_id', '').strip()
            view_count = row.get('view_count', '0').strip()
            
            if not event_id:
                continue
            
            event_counts.append({
                'event_id': event_id,
                'event_title': title_map.get(event_id, 'Unknown Event'),
                'view_count': int(view_count)
            })
        
        # Sort by view count descending
        event_counts.sort(key=lambda x: x['view_count'], reverse=True)
        
        return jsonify(event_counts[:limit])
    except Exception as e:
        return jsonify({'error': str(e)}), 500
