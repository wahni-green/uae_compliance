# Phase 1 – Master data & settings

- [x] `constants/custom_fields.py`: `uae_trn` + Peppol ID (Company/Customer/Supplier), Arabic names, Address `emirate` + `designated_zone`
- [x] Item `uae_vat_category`; item-row `uae_vat_category`/emirate/RCM flags on sales & purchase documents (leading blank Select option)
- [x] Item Tax Template `uae_vat_category` + "Fetch VAT Accounts" button (`client_scripts/item_tax_template.js`)
- [x] DocTypes: UAE Compliance Settings (Single), UAE Compliance VAT Account (child), UAE Designated Zone, UAE TRN
- [x] Settings: one Output/Input account pair per company, thresholds (simplified 10,000; registration 375,000/187,500), filing frequency/stagger, excise accounts
- [x] Seed UAE Designated Zones (insert-only)
- [x] TRN validation (15 digits) in `overrides/company.py` and `overrides/party.py`
- [x] `setup/__init__.py::hide_erpnext_uae_fields()` (also re-applied on Company update, since ERPNext creates its UAE fields when a UAE company is created) via Property Setters (field list from `erpnext/regional/united_arab_emirates/setup.py`); hide ERPNext UAE VAT Settings/UAE VAT 201 entries
- [x] Test asserting no DocType name clashes with other installed apps (ERPNext, oman_compliance)
- [x] `patches.txt`: idempotent entries with `#N` markers
- [x] Migration patch `patches/v1/migrate_item_vat_flags.py`: `is_zero_rated`->Zero Rated, `is_exempt`->Exempt (both set: log and skip); Item default + Item Tax Template; optional draft-row backfill; never modify submitted docs
- [x] Migrate ERPNext UAE VAT Settings/Account, `company_trn`/`tax_id` -> `uae_trn`, `vat_emirate`, `tourist_tax_return`, `reverse_charge`
- [x] Tests for all of the above

## From verification (see ../UAE_VERIFICATION.md)
- [x] TRN regex configurable (default `^100\d{12}$`, no checksum); separate TIN (10 digits) field for Peppol/Corporate Tax
- [x] Designated zone list admin-editable; re-verify against FTA page; removed zones (Dubai Textile City, Al Quoz) not seeded
- [x] Settings: filing period type from FTA assignment (stagger S1-S4), not derived from AED 150M

Notes: ERPNext's UAE VAT 201 report/workspace link is left visible (useful for reconciliation). Emirate is stored at document header level (`uae_emirate` on Sales Order/Delivery Note/Sales Invoice, fetched from the company address), not per item row.
