# Phase 8 – Purchase reconciliation

Modelled on India Compliance's purchase reconciliation: the supplier-side record is the received e-invoice (an inbound UAE E-Invoice Log), the books side is the Purchase Invoice.

- [x] Taxable and VAT amounts stored on received e-invoices (from the XML, or worked out from the total and the VAT for a provider's list)
- [x] Matching per supplier, rule by rule, each document claimed once: exact (number, date, amounts), suggested (close number and date, or the same number with another date), stored as links
- [x] Mismatch candidates (close number, or the same amounts and date) shown for the user to link, never stored
- [x] Tolerance: AED 1 for the taxable amount and the VAT together (fixed)
- [x] Invoices and credit notes are matched apart; the same currency is required; reverse charge, GCC and import purchases are left out
- [x] Link, unlink, ignore and restore; a cancelled Purchase Invoice releases its e-invoice
- [x] Report **UAE Purchase Reconciliation** with Run Matching and the actions, and an Excel export from the report
- [x] Tests (matching rules, tolerance, actions, report rows, non-UAE company)
- [x] Warning on the UAE VAT Return (when generated and before filing) when Purchase Invoices of the period carry input VAT and have no matching received e-invoice; only for companies that receive e-invoices, and ignored invoices are left out. A warning only, filing is not blocked
- Skipped for now (decided): creating a Purchase Invoice from a received document, upload of supplier data, scheduled matching
