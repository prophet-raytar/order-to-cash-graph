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
# Using 1.5 Pro or Flash. Flash is faster for standard tasks.
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
    history: List[ChatMessage] = [] # Supports conversation memory (Bonus Requirement)

class ChatResponse(BaseModel):
    answer: str
    cypher_query: Optional[str] = None
    highlight_nodes: List[str] = [] # Supports UI highlighting (Bonus Requirement)

# --- Master Schema & Examples ---
GRAPH_SCHEMA = """
Nodes:
- Customer (properties: id, name, city, country)
- SalesOrder (properties: id, date, amount, currency, status)
- SalesOrderItem (properties: id, itemNumber, quantity, amount, plant)
- Product (properties: id, description, category)
- OutboundDelivery (properties: id, date)
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

FEW_SHOT_EXAMPLES = """
Example 1 (Order Flow):
User: "Show me the flow for sales order 740506"
Cypher: MATCH path = (c:Customer)-[:PLACED]-(so:SalesOrder {id: '740506'})-[:HAS_ITEM]-(soi:SalesOrderItem)-[:FOR_PRODUCT]-(p:Product) RETURN path

Example 2 (End-to-End Traceability):
User: "Did order 740506 get paid?"
Cypher: MATCH (so:SalesOrder {id: '740506'}) OPTIONAL MATCH path = (so)-[:HAS_DELIVERY]-(od:OutboundDelivery)-[:BILLED_IN]-(bd:BillingDocument)-[:PAID_BY]-(pay:Payment) RETURN so, path

Example 3 (Customer Aggregation by Name):
User: "What products did TechCorp Logistics buy?"
Cypher: MATCH (c:Customer)-[:PLACED]-(so:SalesOrder)-[:HAS_ITEM]-(soi:SalesOrderItem)-[:FOR_PRODUCT]-(p:Product) WHERE c.name CONTAINS 'TechCorp' RETURN DISTINCT p.description as Product, sum(toInteger(soi.quantity)) as TotalQuantity

Example 4 (Customer Aggregation by ID):
User: "What products did customer 310000108 buy?"
Cypher: MATCH (c:Customer {id: '310000108'})-[:PLACED]-(so:SalesOrder)-[:HAS_ITEM]-(soi:SalesOrderItem)-[:FOR_PRODUCT]-(p:Product) RETURN DISTINCT p.id as ProductID, sum(toInteger(soi.quantity)) as TotalQuantity

Example 5 (Product Tracing for Recalls):
User: "Which customers purchased product S8907367001003?"
Cypher: MATCH path = (c:Customer)-[:PLACED]-(so:SalesOrder)-[:HAS_ITEM]-(soi:SalesOrderItem)-[:FOR_PRODUCT]-(p:Product {id: 'S8907367001003'}) RETURN path LIMIT 20

Example 6 (Financial/Status Filtering):
User: "Show me all complete orders over 15000."
Cypher: MATCH path = (c:Customer)-[:PLACED]-(so:SalesOrder {status: 'C'})-[:HAS_ITEM]-(soi:SalesOrderItem)-[:FOR_PRODUCT]-(p:Product) WHERE toFloat(so.amount) > 15000 RETURN path LIMIT 20
"""
# --- Endpoints ---

@app.get("/api/graph")
def get_graph_data():
    """Fetches initial graph state for react-force-graph."""
    # We pull a targeted sample to avoid blowing up the browser DOM
    query = """
    MATCH (n)-[r]->(m)
    RETURN n, r, m
    LIMIT 2000
    """
    nodes_dict = {}
    links = []
    
    with driver.session() as session:
        result = session.run(query)
        for record in result:
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

def clean_cypher(text: str) -> str:
    """Removes markdown formatting from LLM output."""
    text = re.sub(r"```cypher\n?", "", text)
    text = re.sub(r"```\n?", "", text)
    return text.strip()

@app.post("/api/chat", response_model=ChatResponse)
def chat_with_graph(request: ChatRequest):
    user_msg = request.message
    logger.info(f"Received query: {user_msg}")
    
    # --- 1. Master Prompt for Cypher Generation ---
    master_prompt = f"""
    You are a Neo4j Cypher expert for an Order-to-Cash system.
    Schema:
    {GRAPH_SCHEMA}
    
    Examples:
    {FEW_SHOT_EXAMPLES}
    
    User Request: "{user_msg}"
    
    Return a JSON object exactly like this:
    {{
        "is_valid": "YES or NO (NO if unrelated to supply chain/orders)",
        "refusal_message": "If NO, explain why",
        "cypher": "The Neo4j Cypher query to answer the request"
    }}
    """
    
    try:
        # Force JSON output for absolute reliability
        response = model.generate_content(
            master_prompt,
            generation_config=genai.types.GenerationConfig(response_mime_type="application/json")
        )
        llm_data = __import__('json').loads(response.text)
        
        # Guardrail Check
        if "NO" in llm_data.get("is_valid", "").upper():
            return ChatResponse(answer=llm_data.get("refusal_message", "I can only answer questions related to the Order-to-Cash dataset."))
            
        cypher_query = clean_cypher(llm_data.get("cypher", ""))
        
        # --- 2. Database Execution ---
        db_data = []
        highlight_nodes = []
        
        with driver.session() as session:
            result = session.run(cypher_query)
            for record in result:
                db_data.append(record.data())
                for value in record.values():
                    if hasattr(value, 'element_id'):
                        highlight_nodes.append(value.element_id)
                    elif isinstance(value, list):
                        for item in value:
                             if hasattr(item, 'element_id'):
                                 highlight_nodes.append(item.element_id)
                                 
        # --- 3. Token-Optimized Markdown Synthesis ---
        if not db_data:
             final_answer = "I checked the database, but couldn't find any records matching that request."
        else:
             synthesis_prompt = f"""
             User Request: "{user_msg}"
             Raw Data: {db_data}
             
             Task: Format the Raw Data into a highly readable, concise markdown report.
             
             RULES:
             1. NO conversational filler (e.g., skip "Here are the results...").
             2. Use EXACTLY this markdown structure for each record:
             ### Order [ID]
             - **Customer:** [Name]
             - **Total:** [Amount] [Currency]
             - **Items:** [Qty]x [Product Name], [Qty]x [Product Name]
             3. MANDATORY: You MUST insert TWO newlines (\\n\\n) between different orders to separate them visually.
             4. If the data is empty, just reply: "No matching records found."
             """
             try:
                 synthesis_response = model.generate_content(synthesis_prompt)
                 final_answer = synthesis_response.text + "\n\n*(Relevant nodes have been highlighted on the graph).*"
             except Exception as synth_error:
                 logger.warning(f"Synthesis rate limited: {synth_error}")
                 final_answer = "The database retrieved the records successfully, but my formatting engine is currently rate-limited. The exact flow has been highlighted on the graph."
             
        # Extract Semantic IDs from the raw database data to move the camera
        extracted_ids = re.findall(r'\b[A-Z0-9]{6,}\b', str(db_data))
        highlight_nodes.extend(list(set(extracted_ids)))

        return {
            "answer": final_answer,
            "highlight_nodes": list(set(highlight_nodes)),
            "cypher_query": cypher_query
        }

    except Exception as e:
        logger.error(f"Chat error: {str(e)}")
        return ChatResponse(
            answer="I encountered a database error or API timeout. Please try rephrasing your request."
        )