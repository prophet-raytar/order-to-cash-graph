import re
import logging

from fastapi import APIRouter

from models.schemas import ChatRequest, ChatResponse
from services.neo4j_service import driver
from services.llm_service import safe_generate_content, clean_cypher, PROMPT_TRACE, PROMPT_ANALYTICS
from google.api_core.exceptions import ResourceExhausted, ServiceUnavailable

router = APIRouter()
logger = logging.getLogger("uvicorn.error")


@router.post("/api/chat", response_model=ChatResponse)
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
        final_answer = None
        
        if not db_data:
             final_answer = "I checked the database, but couldn't find any records matching that specific criteria."
        else:
             synthesis_prompt = f"""
             User Request: "{user_msg}"
             Raw Graph Data: {db_data}
             
             Task: You are an Enterprise Data Formatter. Format the raw data dynamically into a highly readable summary.
             
             RULES:
             1. NO conversational filler (e.g., skip "Here are the results").
             2. NEVER USE MARKDOWN TABLES. Tables break our UI text rendering.
             3. FORMATTING: ALWAYS use a bulleted list. Put EACH entity or rank on a strict NEW LINE using double line breaks (\\n\\n).
                Example format:
                * **Rank 1**: [Product/Customer Name] - [Count]
                * **Rank 2**: [Product/Customer Name] - [Count]
             4. Omit missing data. Never write "N/A".
             """
             try:
                 synthesis_response = safe_generate_content(synthesis_prompt, require_json=False)
                 final_answer = synthesis_response.text + "\n\n*(Relevant nodes have been highlighted on the graph).*"
             except Exception as synth_error:
                 logger.error(f"Synthesis Fallback Triggered: {synth_error}")
                 fallback_lines = ["### Database Results\n"]
                 for idx, record in enumerate(db_data[:10]):
                     fallback_lines.append(f"**Result {idx + 1}**")
                     for key, val in record.items():
                         # Clean up raw dictionaries for the UI
                         if isinstance(val, dict):
                             clean_val = val.get('description', val.get('name', val.get('id', str(val))))
                         else:
                             clean_val = str(val)
                         fallback_lines.append(f"* **{key}**: {clean_val}")
                     fallback_lines.append("\n")
                 final_answer = "\n".join(fallback_lines) + "\n\n*(Relevant nodes have been highlighted on the graph).*"
                 
        # Extract Semantic IDs safely
        extracted_ids = re.findall(r'\b(?=.*\d)[A-Z0-9]{6,}\b', str(db_data))
        valid_ids = [eid for eid in extracted_ids if not eid.isnumeric()]
        highlight_nodes.extend(list(set(valid_ids)))

        if final_answer is None:
            raise RuntimeError("final_answer was not set")

        # --- THE FINAL RETURN STATEMENT ---
        return {
            "answer": final_answer,
            "highlight_nodes": list(set(highlight_nodes)),
            "new_nodes": list(new_nodes_dict.values()),
            "new_links": new_links,
            "cypher_query": cypher_query
        }

    except ResourceExhausted:
        # Catch the 429 cleanly without dumping the massive Google payload
        logger.error("Chat error: Gemini API quota exceeded (429).")
        return ChatResponse(
            answer="⚠️ **System Alert:** The AI token limit for today has been exhausted. Please try again later or check your API billing tier.",
            highlight_nodes=[],
            new_nodes=[],
            new_links=[]
        )
    except Exception as e:
        # Handle all other generic errors
        logger.error(f"Chat error: {str(e)}")
        return ChatResponse(
            answer="I encountered a database error or API timeout. Please try rephrasing your request.",
            highlight_nodes=[],
            new_nodes=[],
            new_links=[]
        )

