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
