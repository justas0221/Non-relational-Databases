import os
import subprocess
import threading
from dotenv import load_dotenv

load_dotenv()

CASSANDRA_CONTAINER = os.getenv("CASSANDRA_CONTAINER", "cassandra-1")
CASSANDRA_KEYSPACE = os.getenv("CASSANDRA_KEYSPACE", "ticket_marketplace")


def execute_cql(cql_statement, async_mode=False):
    """Execute CQL via docker exec cqlsh
    """
    def _run():
        try:
            cmd = [
                "docker", "exec", CASSANDRA_CONTAINER, 
                "cqlsh", "-e", cql_statement
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                print(f"CQL error: {result.stderr}")
                return False
            return True
        except Exception as e:
            print(f"Failed to execute CQL: {e}")
            return False
    
    if async_mode:
        # Run in background thread
        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        return True
    else:
        return _run()


def query_cql(cql_statement):
    """Query CQL and return results as list of dicts"""
    try:
        cmd = [
            "docker", "exec", CASSANDRA_CONTAINER,
            "cqlsh", "-e", cql_statement
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            print(f"CQL query error: {result.stderr}")
            return []
        
        # Parse cqlsh output
        lines = result.stdout.strip().split('\n')
        
        # Find header line
        header_idx = -1
        for i, line in enumerate(lines):
            if '|' in line and not line.strip().startswith('-'):
                header_idx = i
                break
        
        if header_idx == -1:
            return []
        
        # Get headers
        header_line = lines[header_idx]
        headers = [h.strip() for h in header_line.split('|')]
        
        # Skip separator line if present
        data_start = header_idx + 1
        if data_start < len(lines) and lines[data_start].strip().startswith('-'):
            data_start += 1
        
        # Parse data rows
        rows = []
        for i in range(data_start, len(lines)):
            line = lines[i].strip()
            if not line or line.startswith('(') or not '|' in line:
                continue
            values = [v.strip() for v in line.split('|')]
            if len(values) == len(headers):
                rows.append(dict(zip(headers, values)))
        
        return rows
    except Exception as e:
        print(f"Failed to query CQL: {e}")
        import traceback
        traceback.print_exc()
        return []
