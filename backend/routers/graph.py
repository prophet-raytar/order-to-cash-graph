from fastapi import APIRouter

from services.neo4j_service import driver
from fastapi import APIRouter, HTTPException
import logging

logger = logging.getLogger("uvicorn.error")

router = APIRouter()


@router.get("/api/graph")
def get_graph_data():
    """Fetches initial graph state for react-force-graph."""
    # ENTERPRISE FIX: Find top orders, get paths, and UNWIND them into n, r, m pairs for the UI
    query = """
    MATCH (so:SalesOrder)
    WITH so ORDER BY toFloat(so.amount) DESC LIMIT 20
    MATCH path = (c:Customer)-[:PLACED]-(so)-[:HAS_ITEM]-(soi:SalesOrderItem)-[:FOR_PRODUCT]-(p:Product)
    UNWIND relationships(path) AS r
    RETURN startNode(r) AS n, r, endNode(r) AS m
    """
    nodes_dict = {}
    links = []
    
    with driver.session() as session:
        result = session.run(query)
        for record in result:
            # Now 'n', 'r', and 'm' exist again!
            n, r, m = record["n"], record["r"], record["m"]
            
            if n.element_id not in nodes_dict:
                nodes_dict[n.element_id] = {"id": n.element_id, "label": list(n.labels)[0], "properties": dict(n)}
            if m.element_id not in nodes_dict:
                nodes_dict[m.element_id] = {"id": m.element_id, "label": list(m.labels)[0], "properties": dict(m)}
                
            links.append({
                "source": n.element_id,
                "target": m.element_id,
                "label": r.type
            })
            
    return {"nodes": list(nodes_dict.values()), "links": links}


@router.get("/api/expand/{node_id}")
def expand_node(node_id: str):
    """Fetches immediate neighbors of a specific node safely."""
    logger.info(f"Expanding node: {node_id}")
    query = """
    MATCH (n)-[r]-(m)
    WHERE elementId(n) = $node_id
    RETURN n, r, m
    LIMIT 100
    """
    nodes_dict = {}
    links = []
    
    try:
        # We wrap the database call in a try block so it can't crash the server
        from services.neo4j_service import driver # Ensure driver is imported!
        
        with driver.session() as session:
            result = session.run(query, node_id=node_id)
            for record in result:
                n, r, m = record["n"], record["r"], record["m"]
                if n.element_id not in nodes_dict:
                    nodes_dict[n.element_id] = {"id": n.element_id, "label": list(n.labels)[0], "properties": dict(n)}
                if m.element_id not in nodes_dict:
                    nodes_dict[m.element_id] = {"id": m.element_id, "label": list(m.labels)[0], "properties": dict(m)}
                links.append({"source": n.element_id, "target": m.element_id, "label": r.type})
                
        return {"nodes": list(nodes_dict.values()), "links": links}
        
    except Exception as e:
        # 1. Log the ACTUAL error to your Python terminal
        logger.error(f"Graph Expansion Error for {node_id}: {str(e)}")
        # 2. Return a proper 500 error to React, which keeps CORS headers intact
        raise HTTPException(status_code=500, detail="Database failed to expand this node.")
