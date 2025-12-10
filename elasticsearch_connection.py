import os
from elasticsearch import Elasticsearch
from dotenv import load_dotenv

load_dotenv()

ELASTICSEARCH_URL = os.getenv('ELASTICSEARCH_URL', 'http://localhost:9200')
es_client = Elasticsearch([ELASTICSEARCH_URL])

def index_document(index_name, doc_id, document):
    try:
        return es_client.index(index=index_name, id=doc_id, document=document)
    except Exception as e:
        print(f"Elasticsearch index error: {e}")
        return None

def update_document(index_name, doc_id, document):
    try:
        return es_client.update(index=index_name, id=doc_id, doc=document)
    except Exception as e:
        print(f"Elasticsearch update error: {e}")
        return None

def delete_document(index_name, doc_id):
    try:
        return es_client.delete(index=index_name, id=doc_id)
    except Exception as e:
        print(f"Elasticsearch delete error: {e}")
        return None

def search_documents(index_name, query, fields, size=10):
    try:
        search_query = {
            "query": {
                "multi_match": {
                    "query": query,
                    "fields": fields,
                    "type": "best_fields"
                }
            },
            "size": size
        }
        result = es_client.search(index=index_name, body=search_query)
        hits = []
        for hit in result.get('hits', {}).get('hits', []):
            hits.append(hit['_source'])
        return {'hits': hits, 'total': result.get('hits', {}).get('total', {}).get('value', 0)}
    except Exception as e:
        print(f"Elasticsearch search error: {e}")
        return {'hits': [], 'total': 0}
