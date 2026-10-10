# Phase 7 – Hardening

- [x] Test suites beside every module (435 tests; the official Schematron and UBL schema tests run when `PINT_AE_RESOURCES_DIR` and `UBL_XSD_DIR` are set)
- [x] Idempotent patches; `bench migrate` twice runs cleanly
- [ ] Non-UAE company unaffected on shared bench: tested for Sales Invoice validation and the company check only; add tests for the other hooks (purchase, items, parties, the e-invoice pipeline and the VAT return)
- [x] Documentation: architecture and configuration cover every phase
- [x] User guide (docs/UAE_COMPLIANCE_USER_GUIDE.md)
- [x] CI linter and dependency check green on every merged PR; Semgrep with the Frappe rules clean locally
- [ ] Run `pip-audit` locally (only CI's dependency check has run)
- [ ] UAT with a real UAE company
- [ ] Open point: confirm with the FTA or a tax adviser where the value of a supplier's reverse charge sale is reported on the VAT 201 (the app leaves it out of every box; see docs/UAE_VERIFICATION.md sections 7 and 8)
