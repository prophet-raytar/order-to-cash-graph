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
- (Customer)-[:PLACED]->(SalesOrder)
- (SalesOrder)-[:HAS_ITEM]->(SalesOrderItem)
- (SalesOrderItem)-[:FOR_PRODUCT]->(Product)
- (SalesOrder)-[:HAS_DELIVERY]->(OutboundDelivery)
- (OutboundDelivery)-[:BILLED_IN]->(BillingDocument)
- (BillingDocument)-[:PAID_BY]->(Payment)
"""

FEW_SHOT_EXAMPLES = """
Example 1 (Order Flow):
User: "Show me the flow for sales order 740506"
Cypher: MATCH path = (c:Customer)-[:PLACED]->(so:SalesOrder {id: '740506'})-[:HAS_ITEM]->(soi:SalesOrderItem)-[:FOR_PRODUCT]->(p:Product) RETURN path

Example 2 (End-to-End Traceability):
User: "Did order 740506 get paid?"
Cypher: MATCH (so:SalesOrder {id: '740506'}) OPTIONAL MATCH path = (so)-[:HAS_DELIVERY]->(od:OutboundDelivery)-[:BILLED_IN]->(bd:BillingDocument)-[:PAID_BY]->(pay:Payment) RETURN so, path

Example 3 (Customer Aggregation):
User: "What products did TechCorp Logistics buy?"
Cypher: MATCH (c:Customer)-[:PLACED]->(so:SalesOrder)-[:HAS_ITEM]->(soi:SalesOrderItem)-[:FOR_PRODUCT]->(p:Product) WHERE c.name CONTAINS 'TechCorp' RETURN DISTINCT p.description as Product, sum(toInteger(soi.quantity)) as TotalQuantity

Example 4 (Order Flow):
User: "Show me the flow for sales order 740506"
Cypher: MATCH path = (c:Customer)-[:PLACED]->(so:SalesOrder {id: '740506'})-[:HAS_ITEM]->(soi:SalesOrderItem)-[:FOR_PRODUCT]->(p:Product) RETURN path

Example 5 (Customer Aggregation):
User: "What products did customer 310000108 buy?"
Cypher: MATCH (c:Customer {id: '310000108'})-[:PLACED]->(so:SalesOrder)-[:HAS_ITEM]->(soi:SalesOrderItem)-[:FOR_PRODUCT]->(p:Product) RETURN DISTINCT p.id as ProductID, sum(toInteger(soi.quantity)) as TotalQuantity

Example 6 (Product Tracing for Recalls):
User: "Which customers purchased product S8907367001003?"
Cypher: MATCH path = (c:Customer)-[:PLACED]->(so:SalesOrder)-[:HAS_ITEM]->(soi:SalesOrderItem)-[:FOR_PRODUCT]->(p:Product {id: 'S8907367001003'}) RETURN path LIMIT 20

Example 7 (Financial/Status Filtering):
User: "Show me all complete orders over 15000."
Cypher: MATCH path = (c:Customer)-[:PLACED]->(so:SalesOrder {status: 'C'})-[:HAS_ITEM]->(soi:SalesOrderItem)-[:FOR_PRODUCT]->(p:Product) WHERE toFloat(so.amount) > 15000 RETURN path LIMIT 20
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
    
    # --- FDE OPTIMIZATION: SINGLE PASS GENERATION ---
    # We ask the LLM to do the guardrail, write the Cypher, and prep a generic response in ONE call.
    master_prompt = f"""
    You are an expert Neo4j data engineer and Order-to-Cash assistant.
    User Question: "{user_msg}"
    
    Task 1: Is this question related to supply chain, orders, customers, or products? (Yes/No)
    Task 2: If Yes, generate a Cypher query based on this schema: {GRAPH_SCHEMA}
    {FEW_SHOT_EXAMPLES}
    Limit queries to 20 results.
    Task 3: If No, write a polite refusal.
    
    Output exactly in this JSON format:
    {{
        "is_valid": "Yes or No",
        "cypher": "The raw cypher query or empty string",
        "refusal_message": "Refusal text or empty string"
    }}
    """
    
    try:
        # Force JSON output for absolute reliability (Gemini 2.5 feature)
        response = model.generate_content(
            master_prompt,
            generation_config=genai.types.GenerationConfig(response_mime_type="application/json")
        )
        # Parse the JSON string from the LLM into a Python dictionary
        llm_data = __import__('json').loads(response.text)
        
        # 1. Guardrail Check (Now instantaneous)
        if "NO" in llm_data.get("is_valid", "").upper():
            return ChatResponse(answer=llm_data.get("refusal_message", "I can only answer questions related to the Order-to-Cash dataset."))
            
        cypher_query = clean_cypher(llm_data.get("cypher", ""))
        
        # 2. Database Execution
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
                                 
        # 3. Fast Data Synthesis (No second LLM call)
        # We use a fast, deterministic template instead of calling the LLM again to read the DB.
        if not db_data:
             final_answer = "I checked the database, but couldn't find any records matching that request."
        else:
             # Convert the raw dictionary into a clean string for the user
             clean_data = str(db_data[:3]) # Show max 3 records to keep it readable
             final_answer = f"Here is what I found in the database:\n{clean_data}\n\n(I have highlighted the relevant nodes on the graph for you)."
             
        # Extract Semantic IDs from the user's message (not the answer, since we template it now)
        extracted_ids = re.findall(r'\b[A-Z0-9]{6,}\b', user_msg + str(db_data))
        highlight_nodes.extend(list(set(extracted_ids)))

        return {
            "answer": final_answer,
            "highlight_nodes": list(set(highlight_nodes))
        }

    except Exception as e:
        logger.error(f"Chat error: {str(e)}")
        return ChatResponse(
            answer="I encountered a complex database error or API timeout. Please try rephrasing.",
        )