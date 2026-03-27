import os
import re
import logging

import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted, ServiceUnavailable
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger("uvicorn.error")

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel('models/gemini-2.5-flash-lite')


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
2. OPTIONAL EXPANSION: If the user asks for the *full* flow, billing, or deliveries, extend the path using OPTIONAL MATCH:
   OPTIONAL MATCH path_ext = (so)-[:HAS_DELIVERY]->(od:OutboundDelivery)-[:BILLED_IN]->(bd:BillingDocument)<-[:PAID_BY]-(pay:Payment)
3. ALWAYS return the 'path' variable so the UI can draw the lines. (If using path_ext, return path, path_ext).
4. ALWAYS append 'LIMIT 15' to prevent browser DOM crashes.
5. EXACT IDs: If searching by an exact ID, use {{id: 'X'}}.
6. FUZZY SEARCH: Always use case-insensitive CONTAINS. Example: WHERE toLower(p.description) CONTAINS toLower('Blanc')
7. STATUS CODES: "Complete" means WHERE so.status = 'C'. "Open" or "Pending" means WHERE so.status IN ['A', 'B'].
8. BROKEN FLOWS: To trace broken/incomplete flows, use OPTIONAL MATCH for deliveries/billing and add WHERE od IS NULL OR bd IS NULL.

Examples:
User: "Show me the flow for sales order 740506"
Cypher: MATCH path = (c:Customer)-[:PLACED]-(so:SalesOrder {{id: '740506'}})-[:HAS_ITEM]-(soi:SalesOrderItem)-[:FOR_PRODUCT]-(p:Product) RETURN path LIMIT 15

User: "Trace all complete orders over 15000"
Cypher: MATCH path = (c:Customer)-[:PLACED]-(so:SalesOrder)-[:HAS_ITEM]-(soi:SalesOrderItem)-[:FOR_PRODUCT]-(p:Product) WHERE so.status = 'C' AND toFloat(so.amount) > 15000 RETURN path LIMIT 15
"""

# Agent 2: The Analytics Specialist
PROMPT_ANALYTICS = f"""
You are an Enterprise Graph Data Scientist. Your ONLY job is to write Cypher for math, aggregations, counts, and filtering.
Schema: {GRAPH_SCHEMA}

CRITICAL RULES:
1. When aggregating, NEVER just return string IDs (like c.id). You MUST return the actual Node objects (e.g., RETURN p AS Product, c AS Customer) so our backend can extract their internal IDs and auto-inject them.
2. ALWAYS use toFloat() for amounts/costs and toInteger() for quantities.
3. ALWAYS use ORDER BY and LIMIT 15.
4. FUZZY SEARCH: Always use case-insensitive CONTAINS for text.
5. STATUS CODES: "Complete" means WHERE so.status = 'C'. "Open" or "Pending" means WHERE so.status IN ['A', 'B'].
6. BROKEN FLOWS: If asked for broken/incomplete flows, find SalesOrders missing a delivery, or Deliveries missing a billing document using OPTIONAL MATCH and IS NULL.

Examples:
User: "Which products are associated with the highest number of billing documents?"
Cypher: MATCH (p:Product)<-[:FOR_PRODUCT]-(soi:SalesOrderItem)<-[:HAS_ITEM]-(so:SalesOrder)-[:HAS_DELIVERY]-(od:OutboundDelivery)-[:BILLED_IN]-(bd:BillingDocument) RETURN p AS Product, count(DISTINCT bd) as BillingCount ORDER BY count(DISTINCT bd) DESC LIMIT 15

User: "Find customers with the most orders where individual product cost is below 700."
Cypher: MATCH (c:Customer)-[:PLACED]-(so:SalesOrder)-[:HAS_ITEM]-(soi:SalesOrderItem)-[:FOR_PRODUCT]-(p:Product) WHERE toFloat(soi.amount) < 700 RETURN c AS Customer, count(DISTINCT so) as OrderCount ORDER BY count(DISTINCT so) DESC LIMIT 15

User: "Identify sales orders that have broken or incomplete flows"
Cypher: MATCH (so:SalesOrder) OPTIONAL MATCH (so)-[:HAS_DELIVERY]->(od:OutboundDelivery) OPTIONAL MATCH (od)-[:BILLED_IN]->(bd:BillingDocument) WHERE od IS NULL OR bd IS NULL RETURN so AS SalesOrder, count(so) as IssueCount ORDER BY IssueCount DESC LIMIT 15
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


def clean_cypher(text: str) -> str:
    text = re.sub(r"```cypher\n?", "", text)
    text = re.sub(r"```\n?", "", text)
    return text.strip()

