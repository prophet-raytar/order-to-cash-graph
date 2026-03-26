from fastapi import APIRouter

from services.neo4j_service import driver

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
    """Fetches immediate neighbors of a specific node."""
    query = """
    MATCH (n)-[r]-(m)
    WHERE elementId(n) = $node_id
    RETURN n, r, m
    LIMIT 100
    """
    nodes_dict = {}
    links = []
    
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

