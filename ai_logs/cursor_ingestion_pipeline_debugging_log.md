# Ingestion pipeline phase 2 enrichment
_Exported on 3/25/2026 at 06:45:16 GMT+5:30 from Cursor (2.6.21)_

---

**User**

Please review @backend/ingest.py. I need to build Phase 2 of our ingestion pipeline to enrich the existing graph nodes with readable metadata so our UI displays real company and product names instead of just ID numbers.

Create a new file called backend/enrich.py. It should use the exact same Neo4j driver connection, batching logic, and glob loop structure as the first script.

Write two new ingestion functions:

enrich_customers: Read JSONL files from the data/ folder (find the file containing customer/business partner data). Write a Cypher query to MATCH existing Customer nodes by their id, and SET properties like their name, city, and country.

enrich_products: Read JSONL files from the data/ folder (find the file containing product data). Write a Cypher query to MATCH existing Product nodes by their id, and SET properties like their description and category.

Include a if __name__ == "__main__": block to run both functions.

---

**Cursor**


Reviewing `ingest.py` and scanning the data folder for customer and product JSONL files.




Sampling JSONL structure for business partners, addresses, and products to map fields for enrichment.




Implementing `enrich.py`: matching `ingest.py`'s driver and paths; using `business_partners` and `business_partner_addresses` for customers; using `products` and `product_descriptions` (EN) for products so graph IDs align with `material` / `soldToParty`.




Hardening enrichment: replacing `nullif` (may be unavailable or behave oddly) with Python-side normalization so empty strings don't overwrite names and Cypher stays compatible.




## Brief review of `ingest.py`

- **Neo4j setup**: Single module-level `GraphDatabase.driver` with fixed URI and auth matches what `enrich.py` copies.
- **Flow**: `read_jsonl` → `glob` per subfolder → for each file, `session.execute_write(fn, whole_file_list)` — no chunking; whole file is one transaction callback.
- **Graph model**: `Customer.id` = `soldToParty`; `Product.id` = `material` from line items — aligns with `business_partners.businessPartner` / `products.product` (same material number as in your sample data, e.g. `S8907367001003`).
- **Risk**: Secrets are committed in source; consider env vars (out of scope unless you ask).

---

## `backend/enrich.py`

New file added with the **same** `NEO4J_*` constants, `driver`, `read_jsonl`, **same** `base_data_path`, and the same **glob → per-file → `execute_write`** pattern as `ingest.py`.

| Function | Data sources (under your `data` tree) | Cypher idea |
|----------|----------------------------------------|-------------|
| **`enrich_customers`** | `business_partners/*.jsonl` then `business_partner_addresses/*.jsonl` | `MATCH (c:Customer {id: row.businessPartner})` → `SET` `name` from partner fields; then `city` / `country` from addresses (addresses **deduped** per partner, preferring rows with a city). |
| **`enrich_products`** | `products/*.jsonl` then `product_descriptions/*.jsonl` | `MATCH (p:Product {id: row.product})` → `SET` `category` from `productGroup`; `description` from `productDescription` where `language == "EN"`. |

Helpers normalize empty strings so you do not wipe good values; property updates use `coalesce(new, existing)` where it matters.

**`if __name__ == "__main__"`** calls `run_enrichment()` (`enrich_customers()` then `enrich_products()`), then `driver.close()`.

Run from the `backend` folder (with your Python environment that has `neo4j` installed):

```bash
python enrich.py
```

Python was not available on the PATH in this environment, so I could not execute it here; syntax/lint check on the file is clean.

**Note:** Customer **city/country** only exist in `business_partner_addresses`, not in `business_partners`, so both folders are used inside `enrich_customers` so the UI can show location as well as name. **Product text** comes from `product_descriptions` (EN) plus **category** from the `products` master — both map to the same `product` id as `Product.id` in the graph.

---

**User**

I want to build the ultimate Phase 3 ontology expansion script for my Neo4j Order-to-Cash graph. Please deeply review @backend/ingest.py and use the exact same driver connection, chunking logic (batch size of 1000), and glob loop structure.

Create a new file called backend/expand.py. Write three highly optimized ingestion functions using UNWIND $batch AS row:

ingest_deliveries: Read outbound_delivery_headers.jsonl from the data/ folder. Write a Cypher query to MERGE an OutboundDelivery node (by its ID). Then, MATCH the corresponding SalesOrder node (infer the foreign key, it is usually salesOrder or referenceDocument), and MERGE a relationship: (SalesOrder)-[:HAS_DELIVERY]->(OutboundDelivery).

ingest_billing: Read billing_document_headers.jsonl. MERGE a BillingDocument node. MATCH the corresponding OutboundDelivery or SalesOrder, and MERGE a [:BILLED_IN] relationship to the BillingDocument.

ingest_payments: Read payments_accounts_receivable.jsonl. MERGE a Payment node. MATCH the BillingDocument (usually via billingDocument or reference), and MERGE a [:PAID_BY] relationship.

FDE Constraints:

Use MERGE for all node and relationship creations to ensure idempotency (no duplicates if run twice).

Ensure all properties (dates, amounts) are carried over cleanly.

Include explicit print() statements tracking the batch progress so the terminal isn't silent.

Include an if __name__ == '__main__': block that runs all three functions sequentially and safely closes the driver.

---

**Cursor**


Reviewing `ingest.py` and sampling JSONL schemas for deliveries, billing, and payments to map IDs and foreign keys.




Tracing links in line-item files and searching for reference fields:




Implementing `expand.py`: outbound headers lack sales-order IDs — building a delivery→sales-order map from `outbound_delivery_items`. Resolving billing links from `billing_document_items`. Resolving payment→billing via `invoiceReference`, `journal_entry_items_accounts_receivable.referenceDocument`, or billing headers keyed by `(companyCode, fiscalYear, accountingDocument)`.




Renaming transaction callbacks vs public `ingest_*` entry points per your spec, and hardening `toFloat` for null values.




Resolving the naming conflict: making `ingest_deliveries`, `ingest_billing`, and `ingest_payments` the public pipeline entry points (matching `__main__`), and renaming Tx callbacks to `_ingest_*_tx`.




Here’s what was added and how it lines up with your data and `ingest.py`.

### `ingest.py` vs your Phase 3 script
- **Driver / URI / auth**: Mirrored on `expand.py` (same pattern as `ingest.py`).
- **Glob + per-file processing**: Same idea as `sales_order_headers` / `sales_order_items`: `glob("…/folder/*.jsonl")`, `read_jsonl`, then write.
- **Batching**: `ingest.py` sends **whole files** in one `execute_write`. You asked for **1000-row batches**, so `expand.py` uses `BATCH_SIZE = 1000` and `chunks()` before each `execute_write`.

### `backend/expand.py` behavior

1. **`ingest_deliveries()`**  
   - Reads `outbound_delivery_headers/*.jsonl`, **MERGE** `OutboundDelivery` on `deliveryDocument`, copies header fields (dates, statuses, shipping point, JSON for time objects).  
   - **Sales order link**: Headers don’t carry the SO; your **items** file maps `referenceSdDocument` → sales order. The script builds `deliveryDocument → salesOrder` from `outbound_delivery_items/*.jsonl`, then **`MERGE (so)-[:HAS_DELIVERY]->(od)`** when `salesOrder` is known.

2. **`ingest_billing()`**  
   - Reads `billing_document_headers/*.jsonl`, **MERGE** `BillingDocument` on `billingDocument`, sets amounts (`toFloat` when present), dates, currency, company, fiscal year, `accountingDocument`, `soldToParty`, etc.  
   - **Link to delivery or order**: `billing_document_headers` doesn’t include the SD reference; **`billing_document_items`** has `referenceSdDocument` (delivery `807…` in your sample). The script takes the first reference per billing doc, then **MERGE** `(OutboundDelivery)-[:BILLED_IN]->(BillingDocument)` if that id exists; otherwise **`(SalesOrder)-[:BILLED_IN]->(BillingDocument)`**.

3. **`ingest_payments()`**  
   - **MERGE** `Payment` on `company|fiscalYear|accountingDocument|item`.  
   - **PAID_BY** billing: resolves `billingDocumentId` in order: `invoiceReference` (if present), else `journal_entry_items_accounts_receivable` **`referenceDocument`** (aligned with your journal rows, e.g. `90504219`), else **`billing_document_headers`** keyed by `(companyCode, fiscalYear, accountingDocument)` (e.g. `9400000220`).  
   - **`MERGE (Payment)-[:PAID_BY]->(BillingDocument)`** when a billing id is resolved.

UNWIND batch writers are implemented as **`_ingest_deliveries_tx`**, **`_ingest_billing_tx`**, **`_ingest_payments_tx`** so the public **`ingest_deliveries` / `ingest_billing` / `ingest_payments`** functions can run the glob + logging + 1000-size batches without clashing with the `(tx, batch)` Neo4j callback shape.

**`if __name__ == "__main__"`** prints the data path, runs those three in order, then **`driver.close()`** in a **`finally`** block.

**Note:** Linking relies on these extra folders under the same `BASE_DATA_PATH` as `ingest.py`: `outbound_delivery_items`, `billing_document_items`, `journal_entry_items_accounts_receivable`, and billing headers (already used for payments). Without them, nodes would still load, but many relationships would be missing.

---

**User**

Verify these issues exist and fix them:

Bug 1:
Database credentials are hardcoded directly in the source code instead of being loaded from environment variables. This exposes sensitive authentication credentials to anyone with access to the repository, creating a security vulnerability. The `main.py` file correctly uses `os.getenv()` to load these from environment variables—`expand.py` and `enrich.py` should follow the same pattern.

Bug 2:
The Neo4j driver is not guaranteed to close if an exception occurs during enrichment. If `run_enrichment()` raises an exception, the `driver.close()` call at line 226 is skipped, causing a resource leak. The `expand.py` module correctly handles this with a try-finally block, which should be applied here as well.

 @order-to-cash-graph/backend/expand.py:6-9 @order-to-cash-graph/backend/enrich.py:6-9 @order-to-cash-graph/backend/enrich.py:222-227 

---

**Cursor**


Updating `enrich.py` and `expand.py` to load Neo4j settings via `load_dotenv()` and `os.getenv()` like `main.py`, and wrapping `enrich.py`'s `__main__` in `try`/`finally`.





**Bug 1 — confirmed.** `enrich.py` and `expand.py` used literal `NEO4J_*` strings. They now mirror `main.py`: `load_dotenv()` then `os.getenv("NEO4J_URI")`, `NEO4J_USER`, `NEO4J_PASSWORD`. Run the scripts from a directory where `.env` is visible (same as the API), or export those variables in the shell.

**Bug 2 — confirmed.** `enrich.py` called `driver.close()` only after a successful `run_enrichment()`. It now uses:

```python
try:
    run_enrichment()
    print("Finished!")
finally:
    driver.close()
```

`expand.py` already used `try`/`finally` around the pipeline; only credentials were updated there.

Your `.gitignore` already excludes `.env`, so secrets can live there without being committed. `backend/ingest.py` still embeds credentials if you want that aligned later.

---

**User**

Verify this issue exists and fix it:

The Neo4j driver is not guaranteed to close if an exception occurs during enrichment. If `run_enrichment()` raises an exception, the `driver.close()` call at line 226 is skipped, causing a resource leak. The `expand.py` module correctly handles this with a try-finally block, which should be applied here as well. @order-to-cash-graph/backend/enrich.py:222-227 

---

**Cursor**


This is **already fixed** in your current `enrich.py`. The `__main__` block uses `try`/`finally` so `driver.close()` runs even when `run_enrichment()` raises:

```225:231:c:\Users\chingi\Desktop\order-to-cash-graph\backend\enrich.py
if __name__ == "__main__":
    print("Starting Phase 2 graph enrichment...")
    try:
        run_enrichment()
        print("Finished!")
    finally:
        driver.close()
```

No further change is required for this leak scenario. If you also want a “Driver closed.” log like `expand.py`, say so and we can add it.

