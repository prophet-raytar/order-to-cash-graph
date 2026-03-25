import json
import os
import glob
from neo4j import GraphDatabase

# --- ADD YOUR CREDENTIALS HERE ---
NEO4J_URI = "neo4j+s://e3ef4d8f.databases.neo4j.io"
NEO4J_USER = "e3ef4d8f"
NEO4J_PASSWORD = "VgCAdH0mO6sviu1qCg1uRmQfEWZDKuhuzs9mjsbhZuw"

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

def read_jsonl(file_path):
    data = []
    if not os.path.exists(file_path):
        return data
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                data.append(json.loads(line))
    return data

def ingest_sales_orders(tx, headers_batch):
    query = """
    UNWIND $batch AS row
    MERGE (c:Customer {id: row.soldToParty})
    MERGE (so:SalesOrder {id: row.salesOrder})
    SET so.date = row.creationDate,
        so.amount = toFloat(row.totalNetAmount),
        so.currency = row.transactionCurrency,
        so.status = row.overallDeliveryStatus
    MERGE (c)-[:PLACED]->(so)
    """
    tx.run(query, batch=headers_batch)

def ingest_sales_items(tx, items_batch):
    query = """
    UNWIND $batch AS row
    MATCH (so:SalesOrder {id: row.salesOrder})
    WITH so, row, row.salesOrder + '_' + row.salesOrderItem AS uniqueItemId
    MERGE (soi:SalesOrderItem {id: uniqueItemId})
    SET soi.itemNumber = row.salesOrderItem,
        soi.quantity = toFloat(row.requestedQuantity),
        soi.amount = toFloat(row.netAmount),
        soi.plant = row.productionPlant
    MERGE (p:Product {id: row.material})
    MERGE (so)-[:HAS_ITEM]->(soi)
    MERGE (soi)-[:FOR_PRODUCT]->(p)
    """
    tx.run(query, batch=items_batch)

def run_ingestion():
    base_data_path = "C:/Users/chingi/Downloads/job dataset/data" 
    
    # 1. Ingest Headers
    print("Reading Sales Order Headers...")
    headers_folder = os.path.join(base_data_path, "sales_order_headers")
    header_files = glob.glob(os.path.join(headers_folder, "*.jsonl"))
    
    if not header_files:
        print(f"WARNING: Could not find any .jsonl files in {headers_folder}")
        
    for file_path in header_files:
        print(f"Processing {os.path.basename(file_path)}...")
        headers_data = read_jsonl(file_path)
        if headers_data:
            with driver.session() as session:
                session.execute_write(ingest_sales_orders, headers_data)
    print("All Headers Ingested successfully.\n")

    # 2. Ingest Items
    print("Reading Sales Order Items...")
    items_folder = os.path.join(base_data_path, "sales_order_items")
    item_files = glob.glob(os.path.join(items_folder, "*.jsonl"))
    
    if not item_files:
        print(f"WARNING: Could not find any .jsonl files in {items_folder}")

    for file_path in item_files:
        print(f"Processing {os.path.basename(file_path)}...")
        items_data = read_jsonl(file_path)
        if items_data:
            with driver.session() as session:
                session.execute_write(ingest_sales_items, items_data)
    print("All Items Ingested successfully.")

# THIS IS THE TRIGGER BLOCK THAT MIGHT HAVE BEEN MISSING
if __name__ == "__main__":
    print("Starting Data Ingestion to Neo4j...")
    run_ingestion()
    driver.close()
    print("Finished!")