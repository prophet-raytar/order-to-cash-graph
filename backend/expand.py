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

BASE_DATA_PATH = "C:/Users/chingi/Downloads/job dataset/data"

BATCH_SIZE = 1000


def read_jsonl(file_path):
    data = []
    if not os.path.exists(file_path):
        return data
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                data.append(json.loads(line))
    return data


def chunks(items, size):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _json_or_none(value):
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    return value


def load_delivery_to_sales_order(base_data_path):
    """Map deliveryDocument -> referenceSdDocument (sales order) from line items."""
    result = {}
    folder = os.path.join(base_data_path, "outbound_delivery_items")
    for file_path in glob.glob(os.path.join(folder, "*.jsonl")):
        for row in read_jsonl(file_path):
            dd = row.get("deliveryDocument")
            ref = row.get("referenceSdDocument")
            if dd and ref and str(dd) not in result:
                result[str(dd)] = str(ref)
    return result


def load_billing_to_reference_sd(base_data_path):
    """Map billingDocument -> referenceSdDocument (delivery or SD doc) from line items."""
    result = {}
    folder = os.path.join(base_data_path, "billing_document_items")
    for file_path in glob.glob(os.path.join(folder, "*.jsonl")):
        for row in read_jsonl(file_path):
            bd = row.get("billingDocument")
            ref = row.get("referenceSdDocument")
            if bd and ref and str(bd) not in result:
                result[str(bd)] = str(ref)
    return result


def load_journal_ar_to_billing_doc(base_data_path):
    """Map (company, fy, accounting doc, item) -> referenceDocument (billing doc id)."""
    result = {}
    folder = os.path.join(base_data_path, "journal_entry_items_accounts_receivable")
    for file_path in glob.glob(os.path.join(folder, "*.jsonl")):
        for row in read_jsonl(file_path):
            cc = row.get("companyCode")
            fy = row.get("fiscalYear")
            ad = row.get("accountingDocument")
            item = row.get("accountingDocumentItem")
            ref = row.get("referenceDocument")
            if cc and fy and ad and ref is not None and str(ref).strip() != "":
                key = (cc, fy, str(ad), str(item) if item is not None else "")
                if key not in result:
                    result[key] = str(ref).strip()
    return result


def load_billing_header_by_accounting(base_data_path):
    """Map (companyCode, fiscalYear, accountingDocument) -> billingDocument id."""
    result = {}
    folder = os.path.join(base_data_path, "billing_document_headers")
    for file_path in glob.glob(os.path.join(folder, "*.jsonl")):
        for row in read_jsonl(file_path):
            cc = row.get("companyCode")
            fy = row.get("fiscalYear")
            acc = row.get("accountingDocument")
            bd = row.get("billingDocument")
            if cc and fy and acc and bd:
                result[(cc, fy, str(acc))] = str(bd)
    return result


def enrich_outbound_header_row(row, delivery_to_so):
    dd = row.get("deliveryDocument")
    if not dd:
        return None
    so = delivery_to_so.get(str(dd))
    out = {
        "deliveryDocument": str(dd),
        "salesOrder": so,
        "creationDate": row.get("creationDate"),
        "actualGoodsMovementDate": row.get("actualGoodsMovementDate"),
        "lastChangeDate": row.get("lastChangeDate"),
        "shippingPoint": row.get("shippingPoint"),
        "deliveryBlockReason": row.get("deliveryBlockReason"),
        "hdrGeneralIncompletionStatus": row.get("hdrGeneralIncompletionStatus"),
        "headerBillingBlockReason": row.get("headerBillingBlockReason"),
        "overallGoodsMovementStatus": row.get("overallGoodsMovementStatus"),
        "overallPickingStatus": row.get("overallPickingStatus"),
        "overallProofOfDeliveryStatus": row.get("overallProofOfDeliveryStatus"),
        "creationTimeJson": _json_or_none(row.get("creationTime")),
        "actualGoodsMovementTimeJson": _json_or_none(row.get("actualGoodsMovementTime")),
    }
    return out


def enrich_billing_header_row(row, billing_to_ref):
    bd = row.get("billingDocument")
    if not bd:
        return None
    ref = billing_to_ref.get(str(bd))
    out = {
        "billingDocument": str(bd),
        "referenceSdDocument": ref,
        "billingDocumentType": row.get("billingDocumentType"),
        "creationDate": row.get("creationDate"),
        "creationTimeJson": _json_or_none(row.get("creationTime")),
        "lastChangeDateTime": row.get("lastChangeDateTime"),
        "billingDocumentDate": row.get("billingDocumentDate"),
        "billingDocumentIsCancelled": row.get("billingDocumentIsCancelled"),
        "cancelledBillingDocument": row.get("cancelledBillingDocument"),
        "totalNetAmount": row.get("totalNetAmount"),
        "transactionCurrency": row.get("transactionCurrency"),
        "companyCode": row.get("companyCode"),
        "fiscalYear": row.get("fiscalYear"),
        "accountingDocument": row.get("accountingDocument"),
        "soldToParty": row.get("soldToParty"),
    }
    return out


def payment_row_id(row):
    cc = row.get("companyCode")
    fy = row.get("fiscalYear")
    ad = row.get("accountingDocument")
    item = row.get("accountingDocumentItem")
    if not all([cc, fy, ad, item is not None and str(item) != ""]):
        return None
    return f"{cc}|{fy}|{ad}|{item}"


def resolve_billing_for_payment(row, journal_map, billing_by_accounting):
    inv = row.get("invoiceReference")
    if inv is not None and str(inv).strip() != "":
        return str(inv).strip()
    key_j = (
        row.get("companyCode"),
        row.get("fiscalYear"),
        row.get("accountingDocument"),
        str(row.get("accountingDocumentItem", "")),
    )
    if key_j in journal_map:
        return journal_map[key_j]
    key_a = (row.get("companyCode"), row.get("fiscalYear"), row.get("accountingDocument"))
    if key_a in billing_by_accounting:
        return billing_by_accounting[key_a]
    return None


def enrich_payment_row(row, journal_map, billing_by_accounting):
    pid = payment_row_id(row)
    if not pid:
        return None
    bd_id = resolve_billing_for_payment(row, journal_map, billing_by_accounting)
    return {
        "paymentId": pid,
        "billingDocumentId": bd_id,
        "companyCode": row.get("companyCode"),
        "fiscalYear": row.get("fiscalYear"),
        "accountingDocument": row.get("accountingDocument"),
        "accountingDocumentItem": row.get("accountingDocumentItem"),
        "clearingDate": row.get("clearingDate"),
        "clearingAccountingDocument": row.get("clearingAccountingDocument"),
        "clearingDocFiscalYear": row.get("clearingDocFiscalYear"),
        "amountInTransactionCurrency": row.get("amountInTransactionCurrency"),
        "transactionCurrency": row.get("transactionCurrency"),
        "amountInCompanyCodeCurrency": row.get("amountInCompanyCodeCurrency"),
        "companyCodeCurrency": row.get("companyCodeCurrency"),
        "customer": row.get("customer"),
        "invoiceReference": row.get("invoiceReference"),
        "invoiceReferenceFiscalYear": row.get("invoiceReferenceFiscalYear"),
        "salesDocument": row.get("salesDocument"),
        "salesDocumentItem": row.get("salesDocumentItem"),
        "postingDate": row.get("postingDate"),
        "documentDate": row.get("documentDate"),
        "assignmentReference": row.get("assignmentReference"),
        "glAccount": row.get("glAccount"),
        "financialAccountType": row.get("financialAccountType"),
        "profitCenter": row.get("profitCenter"),
        "costCenter": row.get("costCenter"),
    }


def _ingest_deliveries_tx(tx, batch):
    query = """
    UNWIND $batch AS row
    MERGE (od:OutboundDelivery {id: row.deliveryDocument})
    SET od.creationDate = row.creationDate,
        od.actualGoodsMovementDate = row.actualGoodsMovementDate,
        od.lastChangeDate = row.lastChangeDate,
        od.shippingPoint = row.shippingPoint,
        od.deliveryBlockReason = row.deliveryBlockReason,
        od.hdrGeneralIncompletionStatus = row.hdrGeneralIncompletionStatus,
        od.headerBillingBlockReason = row.headerBillingBlockReason,
        od.overallGoodsMovementStatus = row.overallGoodsMovementStatus,
        od.overallPickingStatus = row.overallPickingStatus,
        od.overallProofOfDeliveryStatus = row.overallProofOfDeliveryStatus,
        od.creationTimeJson = row.creationTimeJson,
        od.actualGoodsMovementTimeJson = row.actualGoodsMovementTimeJson
    WITH od, row
    WHERE row.salesOrder IS NOT NULL
    MATCH (so:SalesOrder {id: row.salesOrder})
    MERGE (so)-[:HAS_DELIVERY]->(od)
    """
    tx.run(query, batch=batch)


def _ingest_billing_tx(tx, batch):
    query = """
    UNWIND $batch AS row
    MERGE (bd:BillingDocument {id: row.billingDocument})
    SET bd.billingDocumentType = row.billingDocumentType,
        bd.creationDate = row.creationDate,
        bd.creationTimeJson = row.creationTimeJson,
        bd.lastChangeDateTime = row.lastChangeDateTime,
        bd.billingDocumentDate = row.billingDocumentDate,
        bd.billingDocumentIsCancelled = row.billingDocumentIsCancelled,
        bd.cancelledBillingDocument = row.cancelledBillingDocument,
        bd.totalNetAmount = CASE
            WHEN row.totalNetAmount IS NULL THEN null
            ELSE toFloat(row.totalNetAmount)
        END,
        bd.transactionCurrency = row.transactionCurrency,
        bd.companyCode = row.companyCode,
        bd.fiscalYear = row.fiscalYear,
        bd.accountingDocument = row.accountingDocument,
        bd.soldToParty = row.soldToParty
    WITH bd, row
    WHERE row.referenceSdDocument IS NOT NULL
    OPTIONAL MATCH (od:OutboundDelivery {id: row.referenceSdDocument})
    OPTIONAL MATCH (so:SalesOrder {id: row.referenceSdDocument})
    FOREACH (_ IN CASE WHEN od IS NOT NULL THEN [1] ELSE [] END |
        MERGE (od)-[:BILLED_IN]->(bd)
    )
    FOREACH (_ IN CASE WHEN od IS NULL AND so IS NOT NULL THEN [1] ELSE [] END |
        MERGE (so)-[:BILLED_IN]->(bd)
    )
    """
    tx.run(query, batch=batch)


def _ingest_payments_tx(tx, batch):
    query = """
    UNWIND $batch AS row
    MERGE (pay:Payment {id: row.paymentId})
    SET pay.companyCode = row.companyCode,
        pay.fiscalYear = row.fiscalYear,
        pay.accountingDocument = row.accountingDocument,
        pay.accountingDocumentItem = row.accountingDocumentItem,
        pay.clearingDate = row.clearingDate,
        pay.clearingAccountingDocument = row.clearingAccountingDocument,
        pay.clearingDocFiscalYear = row.clearingDocFiscalYear,
        pay.amountInTransactionCurrency = CASE
            WHEN row.amountInTransactionCurrency IS NULL THEN null
            ELSE toFloat(row.amountInTransactionCurrency)
        END,
        pay.transactionCurrency = row.transactionCurrency,
        pay.amountInCompanyCodeCurrency = CASE
            WHEN row.amountInCompanyCodeCurrency IS NULL THEN null
            ELSE toFloat(row.amountInCompanyCodeCurrency)
        END,
        pay.companyCodeCurrency = row.companyCodeCurrency,
        pay.customer = row.customer,
        pay.invoiceReference = row.invoiceReference,
        pay.invoiceReferenceFiscalYear = row.invoiceReferenceFiscalYear,
        pay.salesDocument = row.salesDocument,
        pay.salesDocumentItem = row.salesDocumentItem,
        pay.postingDate = row.postingDate,
        pay.documentDate = row.documentDate,
        pay.assignmentReference = row.assignmentReference,
        pay.glAccount = row.glAccount,
        pay.financialAccountType = row.financialAccountType,
        pay.profitCenter = row.profitCenter,
        pay.costCenter = row.costCenter
    WITH pay, row
    WHERE row.billingDocumentId IS NOT NULL
    MATCH (bd:BillingDocument {id: row.billingDocumentId})
    MERGE (pay)-[:PAID_BY]->(bd)
    """
    tx.run(query, batch=batch)


def ingest_deliveries(base_data_path=None):
    base_data_path = base_data_path or BASE_DATA_PATH
    print("Phase 3a — Outbound deliveries")
    delivery_to_so = load_delivery_to_sales_order(base_data_path)
    folder = os.path.join(base_data_path, "outbound_delivery_headers")
    files = glob.glob(os.path.join(folder, "*.jsonl"))
    if not files:
        print(f"WARNING: No .jsonl files in {folder}")
        return
    for file_path in sorted(files):
        base = os.path.basename(file_path)
        raw = read_jsonl(file_path)
        rows = [enrich_outbound_header_row(r, delivery_to_so) for r in raw]
        rows = [r for r in rows if r is not None]
        total = len(rows)
        if total == 0:
            print(f"  {base}: skipped (empty)")
            continue
        n_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
        print(f"  {base}: {total} rows in {n_batches} batch(es)")
        for bi, batch in enumerate(chunks(rows, BATCH_SIZE)):
            print(
                f"    batch {bi + 1}/{n_batches} "
                f"(rows {bi * BATCH_SIZE + 1}–{min((bi + 1) * BATCH_SIZE, total)} of {total})"
            )
            with driver.session() as session:
                session.execute_write(_ingest_deliveries_tx, batch)
    print("Deliveries done.\n")


def ingest_billing(base_data_path=None):
    base_data_path = base_data_path or BASE_DATA_PATH
    print("Phase 3b — Billing documents")
    billing_to_ref = load_billing_to_reference_sd(base_data_path)
    folder = os.path.join(base_data_path, "billing_document_headers")
    files = glob.glob(os.path.join(folder, "*.jsonl"))
    if not files:
        print(f"WARNING: No .jsonl files in {folder}")
        return
    for file_path in sorted(files):
        base = os.path.basename(file_path)
        raw = read_jsonl(file_path)
        rows = [enrich_billing_header_row(r, billing_to_ref) for r in raw]
        rows = [r for r in rows if r is not None]
        total = len(rows)
        if total == 0:
            print(f"  {base}: skipped (empty)")
            continue
        n_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
        print(f"  {base}: {total} rows in {n_batches} batch(es)")
        for bi, batch in enumerate(chunks(rows, BATCH_SIZE)):
            print(
                f"    batch {bi + 1}/{n_batches} "
                f"(rows {bi * BATCH_SIZE + 1}–{min((bi + 1) * BATCH_SIZE, total)} of {total})"
            )
            with driver.session() as session:
                session.execute_write(_ingest_billing_tx, batch)
    print("Billing done.\n")


def ingest_payments(base_data_path=None):
    base_data_path = base_data_path or BASE_DATA_PATH
    print("Phase 3c — Payments (AR)")
    journal_map = load_journal_ar_to_billing_doc(base_data_path)
    billing_by_acc = load_billing_header_by_accounting(base_data_path)
    folder = os.path.join(base_data_path, "payments_accounts_receivable")
    files = glob.glob(os.path.join(folder, "*.jsonl"))
    if not files:
        print(f"WARNING: No .jsonl files in {folder}")
        return
    for file_path in sorted(files):
        base = os.path.basename(file_path)
        raw = read_jsonl(file_path)
        rows = [enrich_payment_row(r, journal_map, billing_by_acc) for r in raw]
        rows = [r for r in rows if r is not None]
        total = len(rows)
        if total == 0:
            print(f"  {base}: skipped (empty)")
            continue
        n_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
        print(f"  {base}: {total} rows in {n_batches} batch(es)")
        for bi, batch in enumerate(chunks(rows, BATCH_SIZE)):
            print(
                f"    batch {bi + 1}/{n_batches} "
                f"(rows {bi * BATCH_SIZE + 1}–{min((bi + 1) * BATCH_SIZE, total)} of {total})"
            )
            with driver.session() as session:
                session.execute_write(_ingest_payments_tx, batch)
    print("Payments done.\n")


if __name__ == "__main__":
    print("Starting Phase 3 ontology expansion (Neo4j)...")
    print(f"Data path: {BASE_DATA_PATH}\n")
    try:
        ingest_deliveries()
        ingest_billing()
        ingest_payments()
    finally:
        driver.close()
        print("Driver closed. Finished.")
