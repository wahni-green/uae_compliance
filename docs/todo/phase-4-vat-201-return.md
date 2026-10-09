# Phase 4 – VAT 201 return & reports

- [ ] DocTypes: UAE VAT Return, UAE VAT Return Box
- [ ] `utils/vat_return/__init__.py::get_invoice_rows()` shared fetch (permission check, excludes out-of-scope)
- [ ] Sections: standard-rated by emirate (1a-1g), tourist refunds (2), reverse-charge sales (3), zero-rated (4), exempt (5), imports (6), import adjustments (7), totals (8)
- [ ] Expenses: standard-rated (9), reverse charge (10), totals (11); Net: 12-15
- [ ] Adjustment columns from return documents
- [ ] Period validation: monthly/quarterly/stagger; due date 28th of following month
- [ ] Generate, Mark as Filed (immutable, `for_update` lock), stale-check `generated_for_*` fields
- [ ] Reports: UAE VAT Sales Register, Purchase Register, VAT Audit (invoice level); FAF export
- [ ] Reconcile against ERPNext UAE VAT 201 on same data
- [ ] Tests

## From verification (see ../UAE_VERIFICATION.md)
- [ ] Box 1 per emirate (lettering a-g to confirm); box 15 is Yes/No; profit margin scheme = Yes/No flag only
- [ ] Omit GCC section until confirmed
- [ ] Box 2 pre-populated negative; boxes 6/7 from customs/import data
- [ ] Period default 3 months, stagger S1-S4; due 28th day after period end, next business day
- [ ] FAF export once Appendix 5 obtained; minimum 21 data elements known
- [ ] Box 1 emirate order (from 2017 FTA requirements doc): 1a Abu Dhabi, 1b Dubai, 1c Sharjah, 1d Ajman, 1e Umm Al Quwain, 1f Ras Al Khaimah, 1g Fujairah
- [ ] Report box 1 by emirate of the fixed establishment most closely connected to the supply (non-established: emirate where supply received) per 2021 VAT Returns Guide
- [ ] FAF CSV export: four tables (Company, Supplier listing, Customer listing, GL) per Appendix 5 of the 2017 FTA requirements doc; codes SR/ZR/EX/IG/RC/OA/IA
- [ ] Read Appendix 7 of that doc (tax code to return box mapping) before building sections
