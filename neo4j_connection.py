import os
from dotenv import load_dotenv
from neo4j import GraphDatabase, basic_auth

load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

_driver = None


def get_driver():
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(
            NEO4J_URI,
            auth=basic_auth(NEO4J_USERNAME, NEO4J_PASSWORD),
        )
    return _driver


def run_cypher(query, parameters=None):
    """Run a Cypher query and return list of dict rows."""
    driver = get_driver()
    parameters = parameters or {}
    with driver.session(database=NEO4J_DATABASE) as session:
        result = session.run(query, parameters)
        return [record.data() for record in result]


def close_driver():
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None

if __name__ == "__main__":
    try:
        result = run_cypher("RETURN 1 AS number")
        if result and result[0].get("number") == 1:
            print("Connected to Neo4j successfully.")
        else:
            print("Failed to connect to Neo4j.")
    except Exception as e:
        print(f"Error connecting to Neo4j: {e}")
