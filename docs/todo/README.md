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

## Remaining work (kept in step with the phase checklists)

**To build**
- E-invoice cases: summary, continuous and agent billing invoices, self-billing ([Phase 6](phase-6-einvoicing-pint-ae.md)).
- Inbound e-invoices: create Purchase Invoices from received documents; acknowledge or dispute them ([Phase 6](phase-6-einvoicing-pint-ae.md)).
- **CD 149/2026**, in force since 1 October 2026: margin scheme purchase price rules, composite supply (ER Art 4(6)), input tax and apportionment changes ([Phase 5](phase-5-advanced-schemes.md)).
- Tourist refund: the 90-day limit and the daily cap across invoices ([Phase 5](phase-5-advanced-schemes.md)).
- Smaller gaps: the excise return, 7-year retention for real estate, detection of other e-invoice exclusions.

**To confirm or run**
- Where a supplier reports the value of a reverse charge sale on the VAT 201 ([UAE_VERIFICATION.md](../UAE_VERIFICATION.md) sections 7 and 8).
- The current FAF specification and tax codes; the electronic devices reverse charge text (CD 91/2023).
- A Microvista production run; UAT with a real UAE company.
- Wider tests that non-UAE companies are unaffected; `pip-audit` locally.
