# Phase 1 – Master data & settings

- [ ] `constants/custom_fields.py`: `uae_trn` + Peppol ID (Company/Customer/Supplier), Arabic names, Address `emirate` + `designated_zone`
- [ ] Item `uae_vat_category`; item-row `uae_vat_category`/emirate/RCM flags on sales & purchase documents (leading blank Select option)
- [ ] Item Tax Template `uae_vat_category` + "Fetch VAT Accounts" button (`client_scripts/item_tax_template.js`)
- [ ] DocTypes: UAE Compliance Settings (Single), UAE Compliance VAT Account (child), UAE Designated Zone, UAE TRN
- [ ] Settings: one Output/Input account pair per company, thresholds (simplified 10,000; registration 375,000/187,500), filing frequency/stagger, excise accounts
- [ ] Seed UAE Designated Zones (insert-only)
- [ ] TRN validation (15 digits) in `overrides/company.py` and `overrides/party.py`
- [ ] `setup/__init__.py::hide_erpnext_uae_fields()` via Property Setters (field list from `erpnext/regional/united_arab_emirates/setup.py`); hide ERPNext UAE VAT Settings/UAE VAT 201 entries
- [ ] Test asserting no DocType name clashes with other installed apps (ERPNext, oman_compliance)
- [ ] `patches.txt`: idempotent entries with `#N` markers
- [ ] Migration patch `patches/v1/migrate_item_vat_flags.py`: `is_zero_rated`->Zero Rated, `is_exempt`->Exempt (both set: log and skip); Item default + Item Tax Template; optional draft-row backfill; never modify submitted docs
- [ ] Migrate ERPNext UAE VAT Settings/Account, `company_trn`/`tax_id` -> `uae_trn`, `vat_emirate`, `tourist_tax_return`, `reverse_charge`
- [ ] Tests for all of the above

## From verification (see ../UAE_VERIFICATION.md)
- [ ] TRN regex configurable (default `^100\d{12}$`, no checksum); separate TIN (10 digits) field for Peppol/Corporate Tax
- [ ] Designated zone list admin-editable; re-verify against FTA page; removed zones (Dubai Textile City, Al Quoz) not seeded
- [ ] Settings: filing period type from FTA assignment (stagger S1-S4), not derived from AED 150M
