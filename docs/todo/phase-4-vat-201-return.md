# Phase 4 – VAT 201 return & reports

- [x] DocTypes: UAE VAT Return, UAE VAT Return Box
- [x] `utils/vat_return/__init__.py::get_invoice_rows()` shared fetch (permission check, excludes out-of-scope)
- [x] Sections: standard-rated by emirate (1a-1g), tourist refunds (2), reverse-charge sales (3), zero-rated (4), exempt (5), imports (6), import adjustments (7), totals (8)
- [x] Expenses: standard-rated (9), reverse charge (10), totals (11); Net: 12-15
- [x] Adjustment columns from return documents
- [x] Period validation: monthly/quarterly/stagger; due date 28th of following month
- [x] Generate, Mark as Filed (immutable, `for_update` lock), stale-check `generated_for_*` fields
- [x] Reports: UAE VAT Sales Register, Purchase Register, VAT Audit (invoice level); FAF export
- [x] Reconcile against ERPNext UAE VAT 201 on same data
- [x] Tests

## From verification (see ../UAE_VERIFICATION.md)
- [x] Box 1 per emirate (lettering a-g to confirm); box 15 is Yes/No; profit margin scheme = Yes/No flag only
- [x] Omit GCC section until confirmed
- [x] Box 2 pre-populated negative; boxes 6/7 from customs/import data
- [x] Period default 3 months, stagger S1-S4; due 28th day after period end, next business day
- [x] FAF export once Appendix 5 obtained; minimum 21 data elements known
- [x] Box 1 emirate order (from 2017 FTA requirements doc): 1a Abu Dhabi, 1b Dubai, 1c Sharjah, 1d Ajman, 1e Umm Al Quwain, 1f Ras Al Khaimah, 1g Fujairah
- [x] Report box 1 by emirate of the fixed establishment most closely connected to the supply (non-established: emirate where supply received) per 2021 VAT Returns Guide
- [x] FAF CSV export: four tables (Company, Supplier listing, Customer listing, GL) per Appendix 5 of the 2017 FTA requirements doc; codes SR/ZR/EX/IG/RC/OA/IA
- [x] Read Appendix 7 of that doc (tax code to return box mapping) before building sections

Notes: credit notes and returns net into the amount and VAT columns of the box they belong to (the form asks for reductions to be included there); the adjustment column stays zero until Phase 5 (bad debt relief, apportionment, capital assets). Box 2 reports the refunded VAT only (negative); the refunded value is not recorded. Box 6 reports imports of goods with postponed VAT, and imports that paid VAT at the border are ordinary purchases in box 9. Box 7 is not generated (zero). Non-standard periods (for example a first period) are allowed with a warning rather than refused. The due date moves to Monday if the 28th day falls on a weekend; public holidays are not considered. The FAF export follows the 2017 FTA layout (four tables in one CSV, separated by a blank line); that is the only layout found and the exact single-file structure is unconfirmed. Tax codes: SR, ZR, EX and RC.
