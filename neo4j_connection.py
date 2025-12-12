"""
Neo4j connection module for executing Cypher queries.
"""

import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

NEO4J_URI = os.getenv('NEO4J_URI')
NEO4J_USER = os.getenv('NEO4J_USER') or os.getenv('NEO4J_USERNAME')
NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD')
NEO4J_DATABASE = os.getenv('NEO4J_DATABASE', 'neo4j')

if not all([NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD]):
    raise RuntimeError("Missing Neo4j configuration. Ensure NEO4J_URI, NEO4J_USER/NEO4J_USERNAME and NEO4J_PASSWORD are set.")

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

def execute_cypher(query, parameters=None):
    """Execute a Cypher write query (CREATE, MERGE, SET, DELETE)"""
    with driver.session(database=NEO4J_DATABASE) as session:
        result = session.run(query, parameters or {})
        summary = result.consume()
        return summary

def query_cypher(query, parameters=None):
    """Execute a Cypher read query (MATCH) and return results as list of dicts"""
    with driver.session(database=NEO4J_DATABASE) as session:
        result = session.run(query, parameters or {})
        return [dict(record) for record in result]

def run_cypher(query, parameters=None):
    """Backward-compatible helper that returns result rows as list of dicts."""
    return query_cypher(query, parameters)

def close_driver():
    """Close the Neo4j driver connection"""
    driver.close()
