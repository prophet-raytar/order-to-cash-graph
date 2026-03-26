import json
import os
import glob
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


def read_jsonl(file_path):
    data = []
    if not os.path.exists(file_path):
        return data
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                data.append(json.loads(line))
    return data


def _dedupe_addresses(rows):
    """Keep one address row per business partner (prefer rows with city populated)."""
    by_bp = {}
    for r in rows:
        bp = r.get("businessPartner")
        if not bp:
            continue
        prev = by_bp.get(bp)

        def score(row):
            return (bool(row.get("cityName")), bool(row.get("country")))

        if prev is None or score(r) > score(prev):
            by_bp[bp] = r
    return list(by_bp.values())


def _normalize_partner_enrichment_rows(batch):
    out = []
    for r in batch:
        bp = r.get("businessPartner")
        if not bp:
            continue
        name = None
        for key in (
            "businessPartnerFullName",
            "businessPartnerName",
            "organizationBpName1",
        ):
            v = r.get(key)
            if v is not None and str(v).strip():
                name = str(v).strip()
                break
        rec = {"businessPartner": str(bp)}
        if name:
            rec["name"] = name
        out.append(rec)
    return out


def _normalize_address_enrichment_rows(batch):
    out = []
    for r in _dedupe_addresses(batch):
        bp = r.get("businessPartner")
        if not bp:
            continue
        rec = {"businessPartner": str(bp)}
        city = r.get("cityName")
        country = r.get("country")
        if city is not None and str(city).strip():
            rec["city"] = str(city).strip()
        if country is not None and str(country).strip():
            rec["country"] = str(country).strip()
        out.append(rec)
    return out


def enrich_customers_from_partners(tx, batch):
    query = """
    UNWIND $batch AS row
    MATCH (c:Customer {id: row.businessPartner})
    SET c.name = coalesce(row.name, c.name)
    """
    tx.run(query, batch=batch)


def enrich_customers_from_addresses(tx, batch):
    query = """
    UNWIND $batch AS row
    MATCH (c:Customer {id: row.businessPartner})
    SET c.city = coalesce(row.city, c.city),
        c.country = coalesce(row.country, c.country)
    """
    tx.run(query, batch=batch)


def enrich_customers():
    base_data_path = "C:/Users/chingi/Downloads/job dataset/data"

    print("Enriching Customers from business partners...")
    partners_folder = os.path.join(base_data_path, "business_partners")
    partner_files = glob.glob(os.path.join(partners_folder, "*.jsonl"))

    if not partner_files:
        print(f"WARNING: Could not find any .jsonl files in {partners_folder}")

    for file_path in partner_files:
        print(f"Processing {os.path.basename(file_path)} (partners)...")
        partners_data = _normalize_partner_enrichment_rows(read_jsonl(file_path))
        if partners_data:
            with driver.session() as session:
                session.execute_write(enrich_customers_from_partners, partners_data)

    print("Enriching Customers from business partner addresses...")
    addresses_folder = os.path.join(base_data_path, "business_partner_addresses")
    address_files = glob.glob(os.path.join(addresses_folder, "*.jsonl"))

    if not address_files:
        print(f"WARNING: Could not find any .jsonl files in {addresses_folder}")

    for file_path in address_files:
        print(f"Processing {os.path.basename(file_path)} (addresses)...")
        raw = read_jsonl(file_path)
        if raw:
            address_rows = _normalize_address_enrichment_rows(raw)
            if address_rows:
                with driver.session() as session:
                    session.execute_write(enrich_customers_from_addresses, address_rows)

    print("Customer enrichment complete.\n")


def enrich_products_master(tx, batch):
    query = """
    UNWIND $batch AS row
    MATCH (p:Product {id: row.product})
    SET p.category = coalesce(row.category, p.category)
    """
    tx.run(query, batch=batch)


def enrich_products_descriptions(tx, batch):
    query = """
    UNWIND $batch AS row
    MATCH (p:Product {id: row.product})
    SET p.description = coalesce(row.description, p.description)
    """
    tx.run(query, batch=batch)


def _normalize_product_master_rows(batch):
    out = []
    for r in batch:
        pid = r.get("product")
        if not pid:
            continue
        rec = {"product": str(pid)}
        pg = r.get("productGroup")
        if pg is not None and str(pg).strip():
            rec["category"] = str(pg).strip()
        out.append(rec)
    return out


def _normalize_product_description_rows(batch):
    out = []
    for r in batch:
        if r.get("language") != "EN":
            continue
        pid = r.get("product")
        if not pid:
            continue
        desc = r.get("productDescription")
        if desc is None or not str(desc).strip():
            continue
        out.append({"product": str(pid), "description": str(desc).strip()})
    return out


def enrich_products():
    base_data_path = "C:/Users/chingi/Downloads/job dataset/data"

    print("Enriching Products from product master...")
    products_folder = os.path.join(base_data_path, "products")
    product_files = glob.glob(os.path.join(products_folder, "*.jsonl"))

    if not product_files:
        print(f"WARNING: Could not find any .jsonl files in {products_folder}")

    for file_path in product_files:
        print(f"Processing {os.path.basename(file_path)} (master)...")
        products_data = _normalize_product_master_rows(read_jsonl(file_path))
        if products_data:
            with driver.session() as session:
                session.execute_write(enrich_products_master, products_data)

    print("Enriching Products from product descriptions...")
    desc_folder = os.path.join(base_data_path, "product_descriptions")
    desc_files = glob.glob(os.path.join(desc_folder, "*.jsonl"))

    if not desc_files:
        print(f"WARNING: Could not find any .jsonl files in {desc_folder}")

    for file_path in desc_files:
        print(f"Processing {os.path.basename(file_path)} (descriptions)...")
        desc_rows = _normalize_product_description_rows(read_jsonl(file_path))
        if desc_rows:
            with driver.session() as session:
                session.execute_write(enrich_products_descriptions, desc_rows)

    print("Product enrichment complete.\n")


def run_enrichment():
    enrich_customers()
    enrich_products()


if __name__ == "__main__":
    print("Starting Phase 2 graph enrichment...")
    try:
        run_enrichment()
        print("Finished!")
    finally:
        driver.close()
