# Implementation To-Do

Phase checklists for [UAE_COMPLIANCE_PLAN.md](../UAE_COMPLIANCE_PLAN.md). Tick items as they are completed.

- [Phase 0 – Foundation](phase-0-foundation.md)
- [Phase 1 – Master data & settings](phase-1-master-data-settings.md)
- [Phase 2 – Transaction logic](phase-2-transaction-logic.md)
- [Phase 3 – Print formats & QR](phase-3-print-formats-qr.md)
- [Phase 4 – VAT 201 return & reports](phase-4-vat-201-return.md)
- [Phase 5 – Advanced schemes](phase-5-advanced-schemes.md)
- [Phase 6 – E-invoicing (PINT AE)](phase-6-einvoicing-pint-ae.md)
- [Phase 7 – Hardening](phase-7-hardening.md)
- [Phase 8 – Purchase reconciliation](phase-8-purchase-reconciliation.md)
- [Phase 9 – ClearTax ASP adapter](phase-9-cleartax-adapter.md)

## Remaining work (kept in step with the phase checklists)

**To build**
- ClearTax follow-up: inbound documents have not been run against a real received document ([Phase 9](phase-9-cleartax-adapter.md)).
- Self-billing documents (on hold: Microvista issues a type 389 as a standard invoice; [Phase 6](phase-6-einvoicing-pint-ae.md)).
- Inbound e-invoices: create Purchase Invoices from received documents; acknowledge or dispute them (Microvista has no endpoint for it); full Schematron validation ([Phase 6](phase-6-einvoicing-pint-ae.md)).
- **CD 149/2026** (read; [UAE_VERIFICATION.md](../UAE_VERIFICATION.md) section 9): the apportionment changes from the first tax year after 1 October 2027 ([Phase 5](phase-5-advanced-schemes.md)). The cash payment rule is built; enter the Minister's amount in UAE Compliance Settings once it is published.
- The excise return ([Phase 5](phase-5-advanced-schemes.md)).
- Block transactions that would change the VAT 201 figures of a period after it is filed ([Phase 4](phase-4-vat-201-return.md)).
- Filing the VAT 201 directly from ERPNext (submission to the FTA EmaraTax portal) instead of only marking it as filed ([Phase 4](phase-4-vat-201-return.md)).

**To confirm or run**
- Where a supplier reports the value of a reverse charge sale on the VAT 201 ([UAE_VERIFICATION.md](../UAE_VERIFICATION.md) sections 7 and 8).
- The current FAF specification and tax codes; the electronic devices reverse charge text (CD 91/2023).
- A Microvista production run; UAT with a real UAE company.
