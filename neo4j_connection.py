"""
Neo4j connection module for executing Cypher queries.
"""

import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

NEO4J_URI = os.getenv('NEO4J_URI')
NEO4J_USER = os.getenv('NEO4J_USER')
NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD')

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

def execute_cypher(query, parameters=None):
    """Execute a Cypher write query (CREATE, MERGE, SET, DELETE)"""
    with driver.session() as session:
        result = session.run(query, parameters or {})
        summary = result.consume()
        return summary

def query_cypher(query, parameters=None):
    """Execute a Cypher read query (MATCH) and return results as list of dicts"""
    with driver.session() as session:
        result = session.run(query, parameters or {})
        return [dict(record) for record in result]

def run_cypher(query, parameters=None):
    """Backward-compatible helper that returns result rows as list of dicts."""
    return query_cypher(query, parameters)

def close_driver():
    """Close the Neo4j driver connection"""
    driver.close()
