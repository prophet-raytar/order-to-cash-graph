# 🌐 Enterprise Order-to-Cash (O2C) Data Retrieval (GraphRAG) System

**Author:** Rakshit Y. A.
**Role Target:** Forward Deployed Engineer (FDE)

## 📌 Overview
In modern supply chains, the Order-to-Cash (O2C) lifecycle is notoriously fragmented (No surprise). Data sits in siloed tables: Customers, Orders, Deliveries, Billing, and Payments, making it incredibly difficult to trace the blast radius of a delayed shipment or aggregate product analytics without complex, highly latent SQL queries.

This project solves that fragmentation by projecting the O2C dataset into a **Neo4j Graph Ontology** and wrapping it in a **Multi-Agent, LLM-powered Query Interface**. It allows users to ask natural language questions, dynamically generates safe Cypher queries, executes them against the graph, and visually auto-renders the results in a physics-based React UI.

## 🏗️ Architecture & Tech Stack
* **Backend:** Python, FastAPI (Modular MVC Architecture)
* **Database:** Neo4j AuraDB (Cloud)
* **LLM Engine:** Google Gemini (2.5 Flash) via `google-generativeai`
* **Frontend:** React (Vite), Tailwind CSS, `react-force-graph` (D3 Physics)
* **Data Pipeline:** Custom Python ETL scripts with 1,000-row batching and `MERGE` idempotency.

---

## 🧠 Core Architectural Decisions & Trade-offs

### 1. Database Selection: Why Neo4j (Graph) over SQL (Relational)?
A common initial assumption is that standard e-commerce data should live in a relational Postgres/SQL database. For a standard CRUD app, SQL is fine. For this specific analytical use case, SQL is a severe bottleneck.

* **The FDE Failsafe (Index-Free Adjacency):** To answer the prompt *"Trace the full flow of billing document X,"* SQL requires a minimum of 5 expensive `JOIN` operations (`Payments -> Billing -> Deliveries -> Order Items -> Orders -> Customers`). In large datasets, these multi-hop joins result in O(N^k) performance degradation. Neo4j uses Index-Free Adjacency. Tracing a 6-hop supply chain path in Neo4j is an O(1) pointer traversal per hop, making it orders of magnitude faster for traceability.
* **Schema Flexibility:** Real-world O2C flows are messy (e.g., an order is billed without a delivery, or multiple payments hit one invoice). Graph handles structural anomalies naturally without requiring brittle schema migrations.

### 2. LLM Strategy: Multi-Agent Semantic Routing
Relying on a single prompt to handle Natural Language to Database translation is an anti-pattern that leads to hallucinations and dropped tables. This system implements a **Multi-Agent Architecture** (Really, go ahead. Try it out.Throw any stress test at it.Forgive me for being too cocky. I am sleep deprived.):

1. **The Gatekeeper (Semantic Router):** Classifies the user's intent into `TRACE`, `ANALYTICS`, or `REJECT`.
2. **The Guardrails:** If a user asks a general knowledge or creative writing question, the router hits the `REJECT` protocol, explicitly fulfilling the security requirement to restrict output strictly to the O2C domain.
3. **The Specialists:** * The *Trace Agent* uses hardcoded traversal templates to map structural paths.
   * The *Analytics Agent* is strictly tuned for mathematical aggregations (`ORDER BY`, `LIMIT`).

### 3. UI/UX: Auto-Injection & Lazy-Loading (Solving the "Hairball")
The fastest way to crash a browser in Graph Visualization is pulling 5,000 nodes at once (the "Hairball Problem").
* **Lazy-Loading:** The system loads a lightweight initial state (Top 20 orders). Users can dynamically expand nodes via the `/api/expand` endpoint.
* **Auto-Node Injection (Ghost Nodes):** When the LLM queries the database, the backend unpacks complex Neo4j `Path` objects, extracts internal hidden IDs, and sends them to the React frontend. The UI surgically injects these new nodes into the live D3 physics engine without unmounting the existing graph, and mathematically recalculates the camera coordinates to zoom into the requested "blast radius."

---

## 🚀 Future Roadmap (Phase 2 Architecture.....NOTE: I REALLY WILL DO ALL OF THIS. It's interesting stuff :-D)
While the current system is highly resilient, a production deployment would require the following architectural upgrades:

1. **Semantic Hybrid Search (Vector + Graph):** Currently, the system uses fuzzy keyword matching (`toLower(n.name) CONTAINS`). To handle deep semantic queries (e.g., a user typing "sunblock" to find "SPF 50 Sunscreen"), Phase 2 would involve generating text embeddings for all Product and Customer nodes and storing them in a Neo4j Vector Index for hybrid cosine-similarity search.
2. **LLM Response Streaming:**
   Graph analytics queries can take several seconds. To improve perceived latency (UX), the backend should stream token responses via Server-Sent Events (SSE). This requires decoupling the Cypher execution from the final natural language synthesis layer so the UI updates in real-time.
3. **Algorithmic Graph Clustering (Neo4j GDS):**
   Currently, clustering is handled visually by the D3 force-directed physics engine. For true data-science insights, the Neo4j Graph Data Science (GDS) plugin would be utilized to run the Louvain community detection algorithm on the backend, assigning community IDs to nodes for advanced fraud or anomaly detection.

---

## 🗄️ ETL Pipeline (Data Ingestion)
The dataset was ingested using three highly optimized scripts located in `backend/etl_scripts/`:
1. **`ingest.py` (Ontology Base):** Establishes the core `Customer -> Order -> Item -> Product` hierarchy.
2. **`enrich.py` (Metadata):** Normalizes empty strings and injects human-readable descriptions and geodata.
3. **`expand.py` (The Ledger):** Maps the complex foreign-key relationships for Deliveries, Billing, and AR Payments, utilizing 1,000-row batching and `MERGE` logic for safe, idempotent reruns.

---

## 💻 How to Run Locally

### Prerequisites
* Python 3.10+
* Node.js 18+
* A Neo4j AuraDB Instance
* A Google Gemini API Key

### Backend Setup
1. Navigate to `/backend`.
2. Create a virtual environment: `python -m venv venv` and activate it.
3. Install dependencies: `pip install -r requirements.txt`.
4. Create a `.env` file matching `.env.example` with your Neo4j and Gemini credentials.
5. Start the server: `uvicorn main:app --reload`.

### Frontend Setup
1. Navigate to `/frontend`.
2. Install dependencies: `npm install`.
3. Start the Vite development server: `npm run dev`.