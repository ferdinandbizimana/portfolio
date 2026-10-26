# SAP exports: column headers

Column headers of the SAP exports Ferdinand uploads, taken from the files he
provided on 2026-10-23 (headers only; no data is kept in this repository).
Dataset definitions in `backend/app/datasets/definitions.py` must use these
names exactly. Headers are compared ignoring case, spaces and punctuation.

All data comes from spreadsheets exported from SAP and uploaded (or saved in
the shared folder); there is no direct SAP connection.

### G/L line items (stock accounts)

Source: G/L line item export, as used in the variance investigation and expiries workbooks (first 31 columns, before the columns added by hand).

The first column `ID(PLANT&MATERIAL&AMOUNT)` and the columns from `ACTION` onwards are added during the investigation, not by SAP.

`Document Number` · `Assignment` · `Reference` · `Reference Key` · `Document Type` · `Document Date` · `Posting Date` · `Posting Key` · `Quantity` · `Amount in Local Currency` · `Local Currency` · `Profit Center` · `Text` · `Offsetting Account` · `Year/Month` · `Account type` · `Account` · `Cost Center` · `Posting Period` · `Invoice Reference` · `Amount in Doc. Curr.` · `Document Currency` · `Reason Code` · `Eff. Exchange Rate` · `G/L Account` · `WBS Element` · `General Ledger Item` · `Plant` · `Plant Description` · `Material` · `Material Description`

### MB51 – material document list

Source: MB51 export.

`Plant` · `Storage Location` · `Material` · `Material Description` · `Movement Type` · `Batch` · `Quantity` · `Amt.in Loc.Cur.` · `Posting Date` · `Document Date` · `Material Document` · `User Name` · `WBS Element` · `Reference` · `Purchase order` · `Document Header Text` · `Qty in OPUn` · `Qty in order unit` · `Qty in unit of entry` · `Unit of Entry` · `Customer` · `Special Stock` · `Material Doc.Item` · `Activity` · `Movement Type Text` · `Asset` · `Base Unit of Measure` · `Company Code` · `Consumption` · `Cost Center` · `Counter` · `Currency` · `Debit/Credit Ind.` · `Entry Date` · `Ext. Amount in LC` · `Goods Receipt/Issue Slip` · `Item` · `Item automatically created` · `Item number of reservation` · `Material Doc. Year` · `Movement indicator` · `Multiple Acct Assignment` · `Name 1` · `Network` · `Order` · `Order Price Unit` · `Order Unit` · `Original Line Item` · `Reason for Movement` · `Receipt Indicator` · `Reservation` · `Opertn task list no.` · `Sales order` · `Sales Order` · `Sales order item` · `Sales Order Item` · `Sales order schedule` · `Sales Value` · `Sales Value inc. VAT` · `Smart Number` · `Stock Segment` · `Sub-number` · `Supplier` · `Time of Entry` · `Trans. / Event Type` · `Warehouse Document` · `Warehouse Number` · `Valuation Type`

### ZSTOCKREPORT – stock on hand

Source: ZSTOCKREPORT export.

`Material` · `NPC CODE` · `Material Description` · `Plant` · `Storage Location` · `Base Unit of Measure` · `Material Type` · `Material Group` · `Unrestricted` · `Quality Inspection` · `Blocked` · `Batch` · `Expiry Date` · `WBS Element` · `Unit Cost`

### MB5T – stock in transit

Source: MB5T export.

`Supplying Plant` · `Purchasing Document` · `Plant` · `Name 1` · `Material` · `Material Description` · `Item` · `Special Stock` · `Quantity` · `Amt.in Loc.Cur.` · `Currency` · `Base Unit of Measure` · `Order Quantity` · `Order Unit` · `Net Order Value` · `Currency`

### ME2N – purchase orders

Source: ME2N export.

`Purchasing Document` · `Item` · `Purchasing Doc. Type` · `Purch. Doc. Category` · `Purchasing Group` · `PO history/release documentation` · `Document Date` · `Supplier/Supplying Plant` · `Material` · `Short Text` · `Material Group` · `Deletion Indicator` · `Item Category` · `Acct Assignment Cat.` · `Plant` · `Storage Location` · `Order Quantity` · `Order Unit` · `Quantity in SKU` · `Stockkeeping unit` · `Net Price` · `Currency` · `Price Unit` · `Target Quantity` · `Open Target Quantity` · `Still to be delivered (qty)` · `Still to be delivered (value)` · `Still to be invoiced (qty)` · `Still to be invoiced (val.)` · `Purch. Organization` · `Component Consumption History` · `Item Category` · `Req. Tracking Number` · `Outline agreement` · `Princ. Agreement Item` · `Target Value` · `Total open value` · `Open value` · `Released value` · `Qty Released to Date` · `Validity Per. Start` · `Validity Period End` · `Quotation Deadline` · `Origin` · `Collective Number` · `No. of Positions` · `Control indicator` · `Purchasing Info Rec.` · `Package number` · `Release group` · `Release Strategy` · `Release State` · `Release indicator` · `Issuing Storage Loc.` · `Name of Supplier` · `Order Price Unit` · `Tax Code` · `Tax Jurisdiction` · `Net Order Value` · `Incomplete` · `Statistical` · `Notified Quantity` · `Stock Segment` · `Requirement Segment` · `Hierarchy Number` · `External Sort Number` · `Ext.Hierarchy Category` · `Requirement Urgency` · `Reqmt Priority` · `Smart Number` · `PSST Grouping Rule` · `PSST Group` · `Characteristic Value 1` · `Char Desc. 1` · `Characteristic Value 2` · `Char Desc. 2` · `Characteristic Value 3` · `Char Desc. 3` · `Donor Code` · `Program Code` · `Requisitioner` · `Final Approval Date` · `Delivery Date`

### ME2M – purchase orders by material

Source: ME2M export (2026-10-25). Same columns as ME2N, in a different order;
the app reads either one as the purchase order dataset. Used for the creation
date (`Document Date`), the approval date (`Final Approval Date`) and the
required delivery date (`Delivery Date`). There is no approval time column.

`Item` · `Purchasing Doc. Type` · `Purch. Doc. Category` · `Purchasing Group` · `PO history/release documentation` · `Document Date` · `Supplier/Supplying Plant` · `Material Group` · `Deletion Indicator` · `Item Category` · `Acct Assignment Cat.` · `Plant` · `Storage Location` · `Order Quantity` · `Order Unit` · `Net Price` · `Currency` · `Price Unit` · `Still to be delivered (qty)` · `Still to be delivered (value)` · `Still to be invoiced (qty)` · `Still to be invoiced (val.)` · `No. of Positions` · `Purchasing Document` · `Purch. Organization` · `Material` · `Short Text` · `Component Consumption History` · `Item Category` · `Req. Tracking Number` · `Quantity in SKU` · `Stockkeeping unit` · `Outline agreement` · `Princ. Agreement Item` · `Target Value` · `Total open value` · `Open value` · `Released value` · `Target Quantity` · `Open Target Quantity` · `Qty Released to Date` · `Validity Per. Start` · `Validity Period End` · `Quotation Deadline` · `Origin` · `Collective Number` · `Control indicator` · `Purchasing Info Rec.` · `Package number` · `Release group` · `Release Strategy` · `Release State` · `Release indicator` · `Issuing Storage Loc.` · `Name of Supplier` · `Order Price Unit` · `Tax Code` · `Tax Jurisdiction` · `Net Order Value` · `Incomplete` · `Statistical` · `Notified Quantity` · `Stock Segment` · `Requirement Segment` · `Hierarchy Number` · `External Sort Number` · `Ext.Hierarchy Category` · `Requirement Urgency` · `Reqmt Priority` · `Smart Number` · `PSST Grouping Rule` · `PSST Group` · `Characteristic Value 1` · `Char Desc. 1` · `Characteristic Value 2` · `Char Desc. 2` · `Characteristic Value 3` · `Char Desc. 3` · `Donor Code` · `Program Code` · `Requisitioner` · `Final Approval Date` · `Delivery Date`

### VA05 – sales orders (order fill rate)

Source: VA05 export.

`Customer Reference` · `Document Date` · `Sales Document Type` · `Sales Document` · `Sales Document Item` · `Sold-to Party` · `Material` · `Order Quantity (Item)` · `Sales Unit` · `Net Value (Item)` · `Document Currency`

### Outbound deliveries (OBDs)

Source: outbound delivery list.

`Ship-to Party` · `Name ship-to party` · `Delivery` · `Picking Date` · `Transptn Plang Date` · `Goods Issue Date` · `Deliv. date(From/to)` · `Material` · `Item Description` · `Shipping Point/Receiving Pt` · `Delivery Quantity` · `Pick quantity` · `Actual delivery qty` · `Sold-to Party Name` · `Created By` · `Plant` · `Picking Status` · `Sold-to Party` · `Act. Gds Mvmnt Date` · `Goods Movement Sts` · `Goods Movement Sts` · `Goods Issue Time` · `Inverted` · `Number of Packages` · `No. Relevant Items` · `Picked Items Locat.` · `Total Weight` · `Quantity Correction in Adv. SR after GR` · `Counter` · `Customer Ret. Order` · `Purchasing Document` · `Handling Unit` · `Billing block` · `Unit of Weight` · `TO for picking` · `Pick Confirmation` · `Picking Status` · `Ind. dynamic bin` · `Loading Group` · `Loading Date` · `Delivery Type` · `Time of delivery` · `Indicator of Legal Control License` · `Warehouse Number` · `Storage Location` · `Storage Bin` · `Storage Bin` · `Storage Type` · `External Delivery ID` · `Vendor` · `Loading/Unloading Point` · `Delivery Priority` · `Loading Point` · `WM Activity Status` · `WM Activity Status` · `Flag` · `Material Avail. Date` · `Adv. Returns Active` · `Supplier Name` · `Name of partner` · `Forward.agent name` · `Net Weight` · `Sold-to party locat.` · `Supplier Location` · `Location of partner` · `Location of carrier` · `Ship-to Party Locat.` · `Additional partner` · `Role of addit. partner` · `Item` · `Processing Status` · `PSST Group` · `Supplier RMA Number` · `Route` · `Returns PO` · `Requirement Segment` · `Stock Segment` · `Division` · `Forwarding Agent` · `Begin Ext. Exp. Date` · `Begin Ext. Exp. Time` · `Retail Promotion` · `Stock Category` · `Batch` · `In Plant` · `Picking Time` · `Loading Time` · `Staging Area` · `Door for Whse No.` · `Base Unit of Measure` · `Item Category` · `Special Stock` · `Special Stock Number` · `Transp. Plan. Time` · `Reference Document` · `Reference Item` · `SD Document Category` · `Goods Issue Time` · `Advanced Shipping and Receiving Relvnc.` · `Warehouse Execution` · `Freight Order` · `Means of Trans. ID` · `Means-of-Trans. Type` · `Del. loc. time zone` · `Rec. loc. time zone` · `Fixed process. time` · `Tot.processing time` · `Var. processing time` · `Reference Document` · `Reference Item` · `Sales Group` · `Sales Organization` · `Volume Unit` · `Volume` · `Sales Unit` · `Distribution Channel`

### Inbound deliveries

Source: inbound delivery list.

`Delivery` · `Deliv. date(From/to)` · `Vendor` · `Item` · `Item Description` · `Flag` · `Material` · `Loading Group` · `Delivery Type` · `Delivery Priority` · `Shipping Point/Receiving Pt` · `Loading Point` · `Picked Items Locat.` · `Time of delivery` · `Loading Date` · `Goods receipt date` · `Transptn Plang Date` · `Picking Date` · `Loading Time` · `Material Avail. Date` · `Route` · `Goods Issue Time` · `Delivery Quantity` · `Sales Unit` · `Transp. Plan. Time` · `Total Weight` · `Net Weight` · `Picking Time` · `Unit of Weight` · `Volume` · `Act. Gds Mvmnt Date` · `Volume Unit` · `Goods Issue Time` · `Number of Packages` · `Del. loc. time zone` · `Tot.processing time` · `Rec. loc. time zone` · `Fixed process. time` · `Var. processing time` · `Pick quantity` · `Billing block` · `Actual delivery qty` · `Ship-to Party` · `Base Unit of Measure` · `Name ship-to party` · `Ship-to Party Locat.` · `Sold-to Party` · `Sold-to Party Name` · `Sold-to party locat.` · `Forwarding Agent` · `Forward.agent name` · `Location of carrier` · `Supplier Location` · `Role of addit. partner` · `Additional partner` · `Name of partner` · `Location of partner` · `Sales Organization` · `Distribution Channel` · `Division` · `Sales Group` · `Purchasing Document` · `External Delivery ID` · `Created By` · `Handling Unit` · `Means of Trans. ID` · `Putaway status` · `WM Activity Status` · `Goods Movement Sts` · `Total stat. putaway` · `WM Activity Status` · `Pick Confirmation` · `Goods Movement Sts` · `Plant` · `Storage Location` · `Warehouse Number` · `Storage Type` · `Storage Bin` · `Ind. dynamic bin` · `Storage Bin` · `TO for putaway` · `Means-of-Trans. Type` · `In Plant` · `Door for Whse No.` · `Staging Area` · `Processing Status` · `No. Relevant Items` · `Item Category` · `SD Document Category` · `Reference Document` · `Reference Item` · `Batch` · `Special Stock` · `Stock Category` · `Special Stock Number` · `Retail Promotion` · `Freight Order` · `Counter` · `Begin Ext. Exp. Date` · `Begin Ext. Exp. Time` · `Indicator of Legal Control License` · `Returns PO` · `Customer Ret. Order` · `Supplier RMA Number` · `Adv. Returns Active` · `Stock Segment` · `Requirement Segment` · `Advanced Shipping and Receiving Relvnc.` · `Warehouse Execution` · `Quantity Correction in Adv. SR after GR` · `Loading/Unloading Point` · `Inverted` · `Reference Document` · `Reference Item` · `PSST Group` · `Supplier Name`

### EWM inbound deliveries

Source: EWM warehouse monitor, inbound deliveries.

`Blocked (Overall)` · `Document` · `Item Number` · `Item Category` · `Purchase Order` · `Purchase Order Item` · `Stock Reference Doc.` · `Product` · `Product Description` · `Batch` · `Quantity` · `Unit of Measure` · `Stock Type` · `Stor. Bin GM Posting` · `Putaway Status` · `Goods Receipt Status` · `Unloading` · `GR Date (Actual)` · `Putaway Date (Act.)` · `Item Cat. Descr.` · `Item Type` · `Item Type Descr.` · `Generated Manually` · `ASN` · `RMA Number` · `Manufacturing Order` · `Maintenance Order` · `Reservation Number` · `Recipient Location` · `Mer. Distr. Process` · `Valuation Quantity` · `Valuation Unit` · `Requirement Segment` · `Stock Segment` · `Vendor Product` · `Vendor Batch` · `Ctry/Reg. of Origin` · `Blocked: ERP Error` · `Party Entitled to Dispose` · `Owner` · `Stock Usage` · `Supply Area` · `Priority Points` · `Warehouse Door` · `Unloading Point` · `Staging Area Group` · `Staging Area` · `Staging Bay` · `Repl. Strategy` · `Storage Type` · `Storage Section` · `Storage Bin` · `Storage Bin Type` · `Bin Specification` · `Activity Area` · `Document Category` · `Planned GR Date` · `Planned Time of GR` · `Whse Process Type` · `GR Time (Actual)` · `Unloadg Date (Plan.)` · `Unloadg Time (Plan.)` · `Unloadg Date (Act.)` · `Unloadg Time (Act.)` · `Putaway Date (Plan.)` · `Putaway Time (Plan.)` · `Putaway Time (Act.)` · `Process Code` · `LE Delivery` · `ERP Document Item` · `Type` · `Sales Order Item` · `Field Logistics Process Status` · `Packaging Spec.` · `WIP Number` · `Kanban ID` · `JIT Call Number`

### EWM warehouse tasks (all movements for products)

Source: EWM warehouse monitor, warehouse tasks.

`Document` · `Whse Process Category Desc.` · `Source Storage Bin` · `Destination Bin` · `Product` · `Product Description` · `Batch` · `Src Trgt Qty BUoM` · `Act. Qty Dest. BUoM` · `Exact Destination Quantity in BUoM` · `Warehouse Task Status` · `Warehouse Task` · `Whse Proc. Category` · `Shelf Life Expiration Date` · `Stock Type` · `Descr. of Stock Type` · `Stock Reference Doc.` · `Goods Receipt Date` · `Created By` · `Created On` · `Created At` · `Confirmed By` · `Confirmation Date` · `Confirmation Time` · `WT Item` · `Source Storage Type` · `Source Stor. Section` · `External Process Step` · `Activity` · `Storage Process` · `Executing Resource` · `Movement Reason` · `Exception Code` · `Start Date` · `Start Time` · `HU Warehouse Task` · `Whse Process Type` · `Dest. Diff. Qty BUoM` · `Type` · `Sales Order Item` · `Document Category` · `Usage` · `Owner` · `Partner Role` · `Party Entitled to Dispose` · `Partner Role` · `Base Unit of Measure` · `Base Unit of Measure` · `Src Trgt Qty AUoM` · `Act Dest Qty Alt UoM` · `Diff. Qty in Alt.Un` · `Alt. Unit of Measure` · `Actual Quantity VUM` · `Valuation Unit` · `Valuation Measured` · `Difference Qty VUM` · `Exact CW Qty Diff.` · `Combination Group` · `Handling Unit Type` · `Hazard Rating 1` · `Hazard Rating 2` · `Loading Weight` · `Weight Unit` · `Loading Volume` · `Volume Unit` · `Capacity Consumption` · `Plnd Proc. Time WT` · `Time Unit` · `Inventory on Putaway Planned` · `Putaway PI Performed` · `Low Stock Check Planned` · `Low Stock Check Performed` · `GR Processing Time` · `Ctry/Reg. of Origin` · `Haz. Sub. Strg-Rel.` · `Inspection ID Type` · `Quality Inspection` · `Target Stock ID` · `Source Logical Pos. of HU` · `Source Resource` · `Internal Source TU` · `Source Transportation Unit` · `Source Carrier` · `Source Location Type` · `Source Handling Unit` · `Retention Quantity` · `Dest. Storage Type` · `Dest. Stor. Section` · `Dest. Logical Pos. of HU` · `Handling Unit Position` · `Dest.Resource` · `Int. Destination TU` · `Destination TU` · `Destination Carrier` · `Dest. Location Type` · `Dest. Handling Unit` · `Original Dest. Bin`

### EWM physical inventory documents

Source: EWM physical inventory documents.

`Physical Inventory Status` · `Phys. Inventory Doc.` · `Storage Bin` · `Stock Reference Doc.` · `Item` · `Product` · `Product Description` · `Batch` · `No. Ref. Phys. Inventory Doc.` · `Book Quantity` · `Base Unit of Measure` · `Counted Quantity` · `Difference Quantity` · `Warehouse Order` · `Shelf Life Expiration Date` · `Counter` · `Count Date` · `Document Year` · `Absolute Difference Quantity` · `Inventory Blocking Ind.` · `Freeze Book Inventory` · `Stor. Bin Empty` · `Physical Inventory Procedure` · `Activity Area` · `Reason` · `Reason Description` · `Priority` · `Priority Description` · `Stock Reference Doc.` · `Storage Section` · `Stock Type` · `Changed By` · `Created On` · `Posting Date` · `Created By` · `Activation Date` · `Storage Type` · `Desc. Stock Type` · `Warehouse Task` · `Reference` · `Type` · `Type Description` · `Ctry/Reg. of Origin` · `Country/Region Name` · `Quality Inspection` · `Stock Segment` · `DocYr of Ref. Phys. Inv. Doc.` · `Ref. Phys. Inv. Doc. Item No.`

### OX10 – plants

Source: OX10 export.

`Plant` · `Name 1` · `Name 2` · `Street and House No.` · `PO Box` · `Postal Code` · `City` · `Country/Region Key` · `Country/Region Name` · `Region` · `Description` · `County Code` · `Description` · `City Code` · `Description` · `Address` · `Language Key` · `Name` · `Factory Calendar` · `Text` · `Tax Jurisdiction`

### Spot check template

Source: spot check template.

`Storage Bin` · `Product` · `Product Description` · `Stock Type` · `Batch` · `Incoming Qty AUoM` · `Outgoing Qty AUoM` · `Avail. Qty in AUoM` · `Qty AUoM` · `Stock Reference Doc.` · `Shelf Life Expiration Date` · `ON HAND Quantity` · `VARIANCE` · `Cause of Variance If Any` · `Correction status`

