"""All dataset definitions.

Real SAP datasets are added in Phase 5 once Ferdinand has provided the exact
headers of each export. Until then only the demo dataset exists; its columns
are invented on purpose and it is clearly marked as a demo.
"""

from app.datasets import ColumnSpec, DatasetSpec, register

DEMO_STOCK_BALANCE = register(
    DatasetSpec(
        key="demo_stock_balance",
        title="Demo: stock balance (fake data)",
        description=(
            "A made-up stock list used to demonstrate and test the analysis engine. "
            "It is not an SAP export."
        ),
        columns=(
            ColumnSpec("Plant", "text", description="Plant code"),
            ColumnSpec("Material", "text", description="Material number"),
            ColumnSpec("Material Description", "text", required=False),
            ColumnSpec("Quantity", "number"),
            ColumnSpec("Value", "number", description="Stock value in RWF"),
        ),
        sheet_hints=("Stock",),
        demo=True,
    )
)


# --- SAP exports used by the analyses (headers from docs/sap-exports.md) ---------

GL_STOCK_LINES = register(
    DatasetSpec(
        key="gl_stock_lines",
        title="G/L line items (stock accounts)",
        description=(
            "G/L account line items of the stock accounts, up to the period end. "
            "Their total per plant, material and WBS is the closing stock."
        ),
        columns=(
            ColumnSpec("Plant", "text"),
            ColumnSpec("Material", "text"),
            ColumnSpec("WBS Element", "text"),
            ColumnSpec("Quantity", "number"),
            ColumnSpec("Amount in Local Currency", "number", description="RWF"),
            ColumnSpec("G/L Account", "text", required=False),
            ColumnSpec("Year/Month", "text", required=False),
            ColumnSpec("Material Description", "text", required=False),
            ColumnSpec("Document Number", "text", required=False),
            ColumnSpec("Posting Key", "text", required=False),
            ColumnSpec("Document Type", "text", required=False),
        ),
        sheet_hints=("Stock 1", "Stock2"),
    )
)

MB51_MATERIAL_DOCUMENTS = register(
    DatasetSpec(
        key="mb51_material_documents",
        title="MB51 material documents",
        description=(
            "Material document lines (MB51). Used for the expired stock scrapped at "
            "Finance level; quantities and amounts of issues are negative."
        ),
        columns=(
            ColumnSpec("Plant", "text"),
            ColumnSpec("Material", "text"),
            ColumnSpec("Movement Type", "text"),
            ColumnSpec("Quantity", "number"),
            ColumnSpec("Amt.in Loc.Cur.", "number", description="RWF"),
            ColumnSpec("WBS Element", "text"),
            ColumnSpec("Material Description", "text", required=False),
            ColumnSpec("Storage Location", "text", required=False),
            ColumnSpec("Batch", "text", required=False),
            ColumnSpec("Posting Date", "text", required=False),
            ColumnSpec("Material Document", "text", required=False),
            ColumnSpec("Movement Type Text", "text", required=False),
            ColumnSpec("Base Unit of Measure", "text", required=False),
            ColumnSpec("Purchase order", "text", required=False),
            ColumnSpec("Reference", "text", required=False),
        ),
        sheet_hints=("Details for scrapping",),
    )
)

OX10_PLANTS = register(
    DatasetSpec(
        key="ox10_plants",
        title="OX10 plants",
        description="Plant list (OX10). The plant code and name are used.",
        columns=(
            ColumnSpec("Plant", "text"),
            ColumnSpec("Name 1", "text", description="Plant name"),
            ColumnSpec("Name 2", "text", required=False),
            ColumnSpec("City", "text", required=False),
            ColumnSpec("Factory Calendar", "text", required=False),
        ),
    )
)

RBC_PREVIOUS_REPORT = register(
    DatasetSpec(
        key="rbc_previous_report",
        title="RBC report data (previous quarter)",
        description=(
            'The data sheet of the previous RBC report (sheet "CPDS Report"): its '
            "closing stock is this quarter's opening, and it gives each material's "
            "category. Reports made by this application contain the same sheet."
        ),
        columns=(
            ColumnSpec("Valuation Area", "text", description="Plant"),
            ColumnSpec("Material", "text"),
            ColumnSpec("WBS", "text"),
            ColumnSpec("Category", "text"),
            ColumnSpec("Closing Stock", "number"),
            ColumnSpec("Closing Value", "number", description="RWF"),
            ColumnSpec("Material Description", "text", required=False),
            ColumnSpec("Base Unit of Measure", "text", required=False),
            ColumnSpec("From Date", "text", required=False),
            ColumnSpec("To Date", "text", required=False),
            ColumnSpec("Opening Stock", "number", required=False),
            ColumnSpec("Opening Value", "number", required=False),
        ),
        sheet_hints=("CPDS Report",),
    )
)

RBC_ITEM_CATEGORIES = register(
    DatasetSpec(
        key="rbc_item_categories",
        title="RBC item category list",
        description='Category of each SAP material (sheet "ITEM Category" of the RBC report).',
        columns=(
            ColumnSpec("SAP MATERIAL", "text"),
            ColumnSpec("Category", "text"),
            ColumnSpec("Product description", "text", required=False),
        ),
        sheet_hints=("ITEM Category",),
    )
)


RBC_MATERIAL_CATEGORIES = register(
    DatasetSpec(
        key="rbc_material_categories",
        title="RBC report lines with programme (category)",
        description=(
            "Any data sheet of an RBC report that gives the programme (category) of each "
            'material on each plant and WBS, e.g. "CPDS Report" or the quarter\'s data sheet.'
        ),
        columns=(
            ColumnSpec("Valuation Area", "text", description="Plant"),
            ColumnSpec("Material", "text"),
            ColumnSpec("WBS", "text"),
            ColumnSpec("Category", "text"),
        ),
        sheet_hints=("CPDS Report", "Data"),
    )
)

CLOSING_VS_COUNTED = register(
    DatasetSpec(
        key="closing_vs_counted",
        title="Closing vs counted stock (reconciliation)",
        description=(
            'Sheet "Closing vs Counted branches" of the year-end stock reconciliation: '
            "closing stock posted in Finance and counted stock per plant and material, with "
            "the reason for each difference."
        ),
        columns=(
            ColumnSpec("ValA", "text", description="Plant (valuation area)"),
            ColumnSpec("Material", "text"),
            ColumnSpec("Sum of Closing Stock Posted In Finance", "number"),
            ColumnSpec("Sum of Closing Value Posted In Finance", "number", description="RWF"),
            ColumnSpec("Counted Quantities", "number"),
            ColumnSpec("Counted Value", "number", description="RWF"),
            ColumnSpec("Diff Between Counted Value and Closing Value", "number"),
            ColumnSpec("Reasons for differences where Applicable", "text"),
            ColumnSpec("ID", "text", required=False),
            ColumnSpec("Description", "text", required=False),
            ColumnSpec("Unit cost", "number", required=False),
        ),
        sheet_hints=("Closing vs Counted branches",),
    )
)

WEEKLY_STOCK_MONITORING = register(
    DatasetSpec(
        key="weekly_stock_monitoring",
        title="Weekly stock monitoring (programme sheet)",
        description=(
            "A programme sheet of the compiled weekly report on stock monitoring: stock at "
            "the RMS central warehouse, branches and SDPs, and the average monthly "
            "consumption (AMC). Column names differ a little between sheets; each spelling "
            "is listed."
        ),
        columns=(
            ColumnSpec("Product code", "text", aliases=("CODE",)),
            ColumnSpec("Product description", "text"),
            ColumnSpec("RMS central warehouse", "text", aliases=("RMS HQ",)),
            ColumnSpec("RMS Branches", "text"),
            ColumnSpec("SDPs", "text"),
            ColumnSpec(
                "AMC",
                "text",
                aliases=("Average Monthly consumption", "Average Monthly distribution"),
            ),
            # On the LAB sheet "Product Code" is the platform and "code" the product code.
            ColumnSpec("code", "text", required=False),
            ColumnSpec("Unit of measure (Pack Size)", "text", required=False),
            ColumnSpec("Total", "text", required=False),
            ColumnSpec(
                "MOS at National Level",
                "text",
                required=False,
                aliases=("MoS AT NATIONAL LEVEL", "MOS atNational Level"),
            ),
            ColumnSpec("ALERT", "text", required=False, aliases=("ALERT AT NATIONAL LEVEL",)),
        ),
    )
)

GL_VARIANCE_LINES = register(
    DatasetSpec(
        key="gl_variance_lines",
        title="Count variance lines (G/L, with investigation)",
        description=(
            "G/L line items of the stock adjustments posted after a physical count "
            "(inventory difference accounts), with the investigation columns ACTION, "
            "REASON and Final Validation Status."
        ),
        columns=(
            ColumnSpec("Plant", "text"),
            ColumnSpec("Material", "text"),
            ColumnSpec("Amount in Local Currency", "number", description="RWF"),
            ColumnSpec("Final Validation Status", "text"),
            ColumnSpec("WBS Element", "text"),
            # Header as exported uses a minus sign; matching ignores punctuation.
            ColumnSpec("Stock Variance (RWF): + excess / - missing", "number", required=False),
            ColumnSpec("Material Description", "text", required=False),
            ColumnSpec("Plant Description", "text", required=False),
            ColumnSpec("Quantity", "number", required=False),
            ColumnSpec("Document Number", "text", required=False),
            ColumnSpec("Posting Date", "text", required=False),
            ColumnSpec("G/L Account", "text", required=False),
            ColumnSpec("ACTION", "text", required=False),
            ColumnSpec("REASON", "text", required=False),
            ColumnSpec("AMOUNT MOVED TO RETAINED EARNINGS", "number", required=False),
            # Added when the lines are grouped by hand (as in the count findings report).
            ColumnSpec("Root cause", "text", required=False),
            ColumnSpec("Action category", "text", required=False),
        ),
        sheet_hints=("sheet to use", "Variance Lines"),
    )
)

FINAL_CLOSING_BY_WBS = register(
    DatasetSpec(
        key="final_closing_by_wbs",
        title="Final closing stock per item and WBS",
        description=(
            "Final closing stock (after expired stock scrapped) per plant, material and "
            'WBS: sheet "Closing by ID and WBS" of the closing-stock-by-WBS workbook made '
            'by this application, or sheet "Item Detail by WBS" of the physical '
            "inventory count findings workbook."
        ),
        columns=(
            ColumnSpec("Plant", "text"),
            ColumnSpec("Material", "text"),
            ColumnSpec("WBS", "text", aliases=("WBS element",)),
            ColumnSpec("Final Value", "number", aliases=("Final closing value",)),
            ColumnSpec("Final Qty", "number", required=False, aliases=("Final closing qty",)),
            ColumnSpec("Plant Name", "text", required=False),
            ColumnSpec("Material Description", "text", required=False),
        ),
        sheet_hints=("Closing by ID and WBS", "Item Detail by WBS"),
    )
)


# --- Other SAP exports: recognised on upload, used by later analyses -------------
# Only a few distinctive columns are listed; all headers are in docs/sap-exports.md.


def _recognised(key: str, title: str, description: str, columns: tuple[str, ...]) -> DatasetSpec:
    return register(
        DatasetSpec(
            key=key,
            title=title,
            description=description,
            columns=tuple(ColumnSpec(name, "text") for name in columns),
        )
    )


ZSTOCKREPORT = register(
    DatasetSpec(
        key="zstockreport",
        title="ZSTOCKREPORT stock on hand",
        description=(
            "Stock on hand by plant, storage location, batch and WBS, with expiry date, "
            "unit cost and the national product code (NPC CODE)."
        ),
        columns=(
            ColumnSpec("Material", "text"),
            ColumnSpec("NPC CODE", "text"),
            ColumnSpec("Plant", "text"),
            ColumnSpec("Unrestricted", "number"),
            ColumnSpec("Quality Inspection", "number"),
            ColumnSpec("Blocked", "number"),
            ColumnSpec("WBS Element", "text"),
            ColumnSpec("Unit Cost", "number", description="RWF"),
            ColumnSpec("Material Description", "text", required=False),
            ColumnSpec("Storage Location", "text", required=False),
            ColumnSpec("Batch", "text", required=False),
            ColumnSpec("Expiry Date", "text", required=False),
            ColumnSpec("Base Unit of Measure", "text", required=False),
            ColumnSpec("Material Type", "text", required=False),
            ColumnSpec("Material Group", "text", required=False),
        ),
    )
)
MB5T_STOCK_IN_TRANSIT = register(
    DatasetSpec(
        key="mb5t_stock_in_transit",
        title="MB5T stock in transit",
        description="Stock in transit between plants (MB5T), per stock transport order.",
        columns=(
            ColumnSpec("Supplying Plant", "text"),
            ColumnSpec("Purchasing Document", "text"),
            ColumnSpec("Plant", "text"),
            ColumnSpec("Material", "text"),
            ColumnSpec("Quantity", "number"),
            ColumnSpec("Amt.in Loc.Cur.", "number", description="RWF"),
            ColumnSpec("Name 1", "text", required=False),
            ColumnSpec("Material Description", "text", required=False),
            ColumnSpec("Item", "text", required=False),
            ColumnSpec("Base Unit of Measure", "text", required=False),
        ),
    )
)
ME2N_PURCHASE_ORDERS = _recognised(
    "me2n_purchase_orders",
    "ME2N purchase orders",
    "Purchase order items (ME2N).",
    (
        "Purchasing Document",
        "Item",
        "Document Date",
        "Material",
        "Plant",
        "Order Quantity",
        "Still to be delivered (qty)",
        "Net Order Value",
    ),
)
VA05_SALES_ORDERS = register(
    DatasetSpec(
        key="va05_sales_orders",
        title="VA05 sales orders",
        description="Sales order items (VA05), for the order fill rate.",
        columns=(
            ColumnSpec("Sales Document", "text"),
            ColumnSpec("Sales Document Item", "text"),
            ColumnSpec("Document Date", "date"),
            ColumnSpec("Sold-to Party", "text"),
            ColumnSpec("Material", "text"),
            ColumnSpec("Order Quantity (Item)", "number"),
            ColumnSpec("Net Value (Item)", "number"),
            ColumnSpec("Customer Reference", "text", required=False),
            ColumnSpec("Sales Document Type", "text", required=False),
            ColumnSpec("Sales Unit", "text", required=False),
        ),
    )
)
OUTBOUND_DELIVERIES = register(
    DatasetSpec(
        key="outbound_deliveries",
        title="Outbound deliveries",
        description=(
            "Outbound delivery items (OBDs): delivered quantity, goods issue date and the "
            "sales order or STO each delivery refers to."
        ),
        columns=(
            ColumnSpec("Delivery", "text"),
            ColumnSpec("Material", "text"),
            ColumnSpec("Plant", "text"),
            ColumnSpec("Delivery Quantity", "number"),
            ColumnSpec("Reference Document", "text"),
            ColumnSpec("Reference Item", "text", required=False),
            ColumnSpec("Actual delivery qty", "number", required=False),
            ColumnSpec("Act. Gds Mvmnt Date", "date", required=False),
            ColumnSpec("Goods Issue Date", "date", required=False),
            ColumnSpec("Ship-to Party", "text", required=False),
            ColumnSpec("Name ship-to party", "text", required=False),
            ColumnSpec("Sold-to Party Name", "text", required=False),
            ColumnSpec("Item Description", "text", required=False),
            ColumnSpec("Purchasing Document", "text", required=False),
            ColumnSpec("Delivery Type", "text", required=False),
        ),
    )
)
INBOUND_DELIVERIES = _recognised(
    "inbound_deliveries",
    "Inbound deliveries",
    "Inbound delivery items.",
    (
        "Delivery",
        "Vendor",
        "Material",
        "Delivery Quantity",
        "Goods receipt date",
        "Purchasing Document",
        "Putaway status",
    ),
)
EWM_INBOUND_DELIVERIES = _recognised(
    "ewm_inbound_deliveries",
    "EWM inbound deliveries",
    "Inbound deliveries in the EWM warehouse monitor.",
    (
        "Document",
        "Item Number",
        "Purchase Order",
        "Product",
        "Quantity",
        "Putaway Status",
        "Goods Receipt Status",
        "GR Date (Actual)",
    ),
)
EWM_WAREHOUSE_TASKS = _recognised(
    "ewm_warehouse_tasks",
    "EWM warehouse tasks",
    "Warehouse tasks for products in the EWM warehouse monitor.",
    (
        "Warehouse Task",
        "Whse Process Category Desc.",
        "Source Storage Bin",
        "Destination Bin",
        "Product",
        "Warehouse Task Status",
        "Confirmation Date",
    ),
)
EWM_PHYSICAL_INVENTORY = _recognised(
    "ewm_physical_inventory",
    "EWM physical inventory documents",
    "Physical inventory document items in EWM: book, counted and difference quantity.",
    (
        "Phys. Inventory Doc.",
        "Storage Bin",
        "Product",
        "Book Quantity",
        "Counted Quantity",
        "Difference Quantity",
        "Count Date",
    ),
)
SPOT_CHECK = _recognised(
    "spot_check",
    "Spot check sheet",
    "Spot check of bins: system quantity, quantity on hand and variance.",
    ("Storage Bin", "Product", "Avail. Qty in AUoM", "ON HAND Quantity", "VARIANCE"),
)
