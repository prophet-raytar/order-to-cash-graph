import os
import re
import logging
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from neo4j import GraphDatabase
from dotenv import load_dotenv
import google.generativeai as genai
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from google.api_core.exceptions import ResourceExhausted, ServiceUnavailable

# --- Setup & Configuration ---
load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

try:
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    driver.verify_connectivity()
    logger.info("Successfully connected to Neo4j.")
except Exception as e:
    logger.error(f"Failed to connect to Neo4j: {e}")

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel('models/gemini-2.5-flash')

app = FastAPI(title="Order-to-Cash Graph API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Models ---
class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    message: str
    history: List[ChatMessage] = []

class ChatResponse(BaseModel):
    answer: str
    cypher_query: Optional[str] = None
    highlight_nodes: List[str] = []
    new_nodes: List[Dict[str, Any]] = []  
    new_links: List[Dict[str, Any]] = []  

# --- System Prompts (Multi-Agent Architecture) ---
GRAPH_SCHEMA = """
Nodes:
- Customer (properties: id, name, city, country)
- SalesOrder (properties: id, date, amount, currency, status)
- SalesOrderItem (properties: id, itemNumber, quantity, amount, plant)
- Product (properties: id, description, category)
- OutboundDelivery (properties: id, date, status)
- BillingDocument (properties: id, amount, date)
- Payment (properties: id, amount, clearingDate)

Relationships:
- (Customer)-[:PLACED]-(SalesOrder)
- (SalesOrder)-[:HAS_ITEM]-(SalesOrderItem)
- (SalesOrderItem)-[:FOR_PRODUCT]-(Product)
- (SalesOrder)-[:HAS_DELIVERY]-(OutboundDelivery)
- (OutboundDelivery)-[:BILLED_IN]-(BillingDocument)
- (BillingDocument)-[:PAID_BY]-(Payment)
"""

# Agent 1: The Trace Specialist
PROMPT_TRACE = f"""
You are an Enterprise Graph Trace Specialist. Your ONLY job is to write Cypher to map structural supply chain paths.
Schema: {GRAPH_SCHEMA}

CRITICAL RULES:
1. ALWAYS use this base traversal: MATCH path = (c:Customer)-[:PLACED]-(so:SalesOrder)-[:HAS_ITEM]-(soi:SalesOrderItem)-[:FOR_PRODUCT]-(p:Product)
2. ALWAYS return the 'path' variable so the UI can draw the lines.
3. ALWAYS append 'LIMIT 15' to prevent browser DOM crashes.
4. EXACT IDs: If searching by an exact ID (like an order number), use {{id: 'X'}}.
5. FUZZY SEARCH (TEXT): If the user provides a product description, customer name, or city, NEVER use exact property matching. ALWAYS use case-insensitive CONTAINS.
   Example: WHERE toLower(p.description) CONTAINS toLower('Blanc')

Examples:
User: "Show me the flow for sales order 740506"
Cypher: MATCH path = (c:Customer)-[:PLACED]-(so:SalesOrder {{id: '740506'}})-[:HAS_ITEM]-(soi:SalesOrderItem)-[:FOR_PRODUCT]-(p:Product) RETURN path LIMIT 15

User: "Which customers purchased BLANC deodorant?"
Cypher: MATCH path = (c:Customer)-[:PLACED]-(so:SalesOrder)-[:HAS_ITEM]-(soi:SalesOrderItem)-[:FOR_PRODUCT]-(p:Product) WHERE toLower(p.description) CONTAINS toLower('blanc') RETURN path LIMIT 15
"""

# Agent 2: The Analytics Specialist
PROMPT_ANALYTICS = f"""
You are an Enterprise Graph Data Scientist. Your ONLY job is to write Cypher for math, aggregations, counts, and filtering.
Schema: {GRAPH_SCHEMA}

CRITICAL RULES:
CRITICAL RULES:
1. When aggregating, NEVER just return string IDs (like c.id). You MUST return the actual Node objects (e.g., RETURN p AS Product, c AS Customer) so our backend can extract their internal IDs and auto-inject them.
2. ALWAYS use toFloat() for amounts/costs and toInteger() for quantities.
3. ALWAYS use ORDER BY and LIMIT 15.
4. FUZZY SEARCH (TEXT): If filtering by product name, customer name, or category, NEVER use exact matching. ALWAYS use case-insensitive CONTAINS.
   Example: WHERE toLower(p.description) CONTAINS toLower('blanc')

Examples:
User: "Which products are associated with the highest number of billing documents?"
Cypher: MATCH (p:Product)<-[:FOR_PRODUCT]-(soi:SalesOrderItem)<-[:HAS_ITEM]-(so:SalesOrder)-[:HAS_DELIVERY]-(od:OutboundDelivery)-[:BILLED_IN]-(bd:BillingDocument) RETURN p.id as ProductID, p.description as Product, count(DISTINCT bd) as BillingCount ORDER BY count(DISTINCT bd) DESC LIMIT 15

User: "Find customers with the most orders where individual product cost is below 700."
Cypher: MATCH (c:Customer)-[:PLACED]-(so:SalesOrder)-[:HAS_ITEM]-(soi:SalesOrderItem)-[:FOR_PRODUCT]-(p:Product) WHERE toFloat(soi.amount) < 700 RETURN c.id as CustomerID, c.name as CustomerName, count(DISTINCT so) as OrderCount ORDER BY count(DISTINCT so) DESC LIMIT 15
"""

# --- Resilient LLM Helper ---
@retry(
    wait=wait_exponential(multiplier=1, min=2, max=10), 
    stop=stop_after_attempt(3),
    retry=retry_if_exception_type((ResourceExhausted, ServiceUnavailable)),
    reraise=True
)
def safe_generate_content(prompt: str, require_json: bool = False):
    logger.info("Calling LLM API...")
    if require_json:
        return model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(response_mime_type="application/json")
        )
    return model.generate_content(prompt)

# --- Endpoints ---
@app.get("/api/graph")
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

@app.get("/api/expand/{node_id}")
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

def clean_cypher(text: str) -> str:
    text = re.sub(r"```cypher\n?", "", text)
    text = re.sub(r"```\n?", "", text)
    return text.strip()

@app.post("/api/chat", response_model=ChatResponse)
def chat_with_graph(request: ChatRequest):
    user_msg = request.message
    logger.info(f"Received query: {user_msg}")
    
    try:
        # --- PHASE 1: SEMANTIC ROUTING ---
        router_prompt = f"""
        Analyze this user request for a Supply Chain Graph Database.
        If the request is asking for aggregations, highest/lowest, math, counting, or leaderboards -> Reply exactly "ANALYTICS"
        If the request is asking for a specific order flow, tracking an item, or finding direct connections -> Reply exactly "TRACE"
        If it has nothing to do with supply chains, orders, or customers -> Reply exactly "REJECT"
        
        Request: "{user_msg}"
        """
        intent_response = safe_generate_content(router_prompt, require_json=False)
        intent = intent_response.text.strip().upper()
        logger.info(f"Router classified intent as: {intent}")
        
        if "REJECT" in intent:
            return ChatResponse(answer="I can only answer questions related to the Order-to-Cash dataset.")
            
        # --- PHASE 2: DYNAMIC DISPATCH ---
        if "ANALYTICS" in intent:
            active_prompt = PROMPT_ANALYTICS
        else:
            active_prompt = PROMPT_TRACE
            
        payload_prompt = active_prompt + f"""
        User Request: "{user_msg}"
        
        Return a JSON object exactly like this:
        {{
            "cypher": "The Neo4j Cypher query to execute"
        }}
        """
        
        response = safe_generate_content(payload_prompt, require_json=True)
        llm_data = __import__('json').loads(response.text)
        cypher_query = clean_cypher(llm_data.get("cypher", ""))
        
        # --- PHASE 3: DATABASE EXECUTION & AUTO-INJECTION ---
        db_data = []
        highlight_nodes = []
        new_nodes_dict = {}
        new_links = []
        
        with driver.session() as session:
            result = session.run(cypher_query)
            for record in result:
                db_data.append(record.data())
                for value in record.values():
                    # 1. Is it a Path?
                    if hasattr(value, 'nodes') and hasattr(value, 'relationships'):
                        for n in value.nodes:
                            highlight_nodes.append(n.element_id)
                            new_nodes_dict[n.element_id] = {"id": n.element_id, "label": list(n.labels)[0], "properties": dict(n)}
                        for r in value.relationships:
                            new_links.append({"source": r.start_node.element_id, "target": r.end_node.element_id, "label": r.type})
                    # 2. Is it a single Node?
                    elif hasattr(value, 'element_id'):
                        highlight_nodes.append(value.element_id)
                        new_nodes_dict[value.element_id] = {"id": value.element_id, "label": list(value.labels)[0], "properties": dict(value)}
                    # 3. Is it a List of nodes?
                    elif isinstance(value, list):
                        for item in value:
                             if hasattr(item, 'element_id'):
                                 highlight_nodes.append(item.element_id)
                                 new_nodes_dict[item.element_id] = {"id": item.element_id, "label": list(item.labels)[0], "properties": dict(item)}

        # --- PHASE 4: ADAPTIVE SYNTHESIS ---
        if not db_data:
             final_answer = "I checked the database, but couldn't find any records matching that specific criteria."
        else:
             synthesis_prompt = f"""
             User Request: "{user_msg}"
             Raw Graph Data: {db_data}
             
             Task: You are an Enterprise Data Formatter. Format the raw data dynamically.
             
             RULES:
             1. NO conversational filler (e.g., skip "Here are the results").
             2. ADAPTIVE FORMATTING:
                - IF Analytics/Leaderboard: ALWAYS format as a Markdown Table with columns (Rank | Product | Count).
                - IF Specific Orders/Traces: ALWAYS put EACH entity on a strict NEW LINE using bullet points.
             3. CRITICAL: You MUST use proper markdown line breaks (\\n) between every row or item so they do not clump together.
             4. Omit missing data. Never write "N/A".
             """
             try:
                 synthesis_response = safe_generate_content(synthesis_prompt, require_json=False)
                 final_answer = synthesis_response.text + "\n\n*(Relevant nodes have been highlighted on the graph).*"
             except Exception as synth_error:
                 logger.error(f"Synthesis Fallback Triggered: {synth_error}")
                 fallback_lines = ["### Database Results (Auto-Formatted)\n"]
                 for idx, record in enumerate(db_data[:10]):
                     fallback_lines.append(f"**Result {idx + 1}**")
                     for key, val in record.items():
                         clean_val = dict(val) if hasattr(val, 'items') else str(val)
                         fallback_lines.append(f"- **{key}**: `{clean_val}`")
                     fallback_lines.append("\n---\n")
                 final_answer = "\n".join(fallback_lines)
                 
        # Extract Semantic IDs safely
        extracted_ids = re.findall(r'\b(?=.*\d)[A-Z0-9]{6,}\b', str(db_data))
        valid_ids = [eid for eid in extracted_ids if not eid.isnumeric()]
        highlight_nodes.extend(list(set(valid_ids)))

        # --- THE FINAL RETURN STATEMENT ---
        return {
            "answer": final_answer,
            "highlight_nodes": list(set(highlight_nodes)),
            "new_nodes": list(new_nodes_dict.values()),
            "new_links": new_links,
            "cypher_query": cypher_query
        }

    except Exception as e:
        logger.error(f"Chat error: {str(e)}")
        return ChatResponse(
            answer="I encountered a database error or API timeout. Please try rephrasing your request."
        )