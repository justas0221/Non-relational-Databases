from flask import Blueprint, request, jsonify, Response
import json
from elasticsearch_connection import search_documents

search_bp = Blueprint('search', __name__)

@search_bp.route('/search/events', methods=['GET'])
def search_events():
    query = request.args.get('q', '')
    if not query:
        return jsonify({'error': 'Query parameter required'}), 400
    
    results = search_documents('events', query, ['title', 'category', 'venue_name', 'venue_city'])
    return Response(json.dumps(results, ensure_ascii=False, indent=2), mimetype='application/json')

@search_bp.route('/search/venues', methods=['GET'])
def search_venues():
    query = request.args.get('q', '')
    if not query:
        return jsonify({'error': 'Query parameter required'}), 400
    
    results = search_documents('venues', query, ['name', 'city'])
    return Response(json.dumps(results, ensure_ascii=False, indent=2), mimetype='application/json')

@search_bp.route('/search/autocomplete', methods=['GET'])
def autocomplete():
    query = request.args.get('q', '').strip().lower()
    if not query or len(query) < 2:
        return Response(json.dumps([], ensure_ascii=False, indent=2), mimetype='application/json')
    
    from elasticsearch_connection import es_client
    
    search_body = {
        "query": {
            "wildcard": {
                "title": {
                    "value": f"{query}*",
                    "case_insensitive": True
                }
            }
        },
        "size": 5
    }
    
    venue_body = {
        "query": {
            "wildcard": {
                "name": {
                    "value": f"{query}*",
                    "case_insensitive": True
                }
            }
        },
        "size": 5
    }
    
    suggestions = []
    
    try:
        events_result = es_client.search(index='events', body=search_body)
        for hit in events_result.get('hits', {}).get('hits', []):
            suggestions.append({'type': 'event', 'text': hit['_source']['title']})
    except Exception as e:
        print(f"Autocomplete events error: {e}")
    
    try:
        venues_result = es_client.search(index='venues', body=venue_body)
        for hit in venues_result.get('hits', {}).get('hits', []):
            suggestions.append({'type': 'venue', 'text': hit['_source']['name']})
    except Exception as e:
        print(f"Autocomplete venues error: {e}")
    
    return Response(json.dumps(suggestions[:10], ensure_ascii=False, indent=2), mimetype='application/json')
