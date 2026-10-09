# UAE Compliance (VAT) – Implementation Plan

> Status: approved plan, no code written yet. Research dated 2026-10-09; secondary sources, verify against FTA/MoF before coding.

## Context
`uae_compliance` is an empty Frappe app skeleton (single "Initialize App" commit). It must implement UAE VAT for ERPNext v15.112, following the structure of `oman_compliance` (the rewrite; `oman_vat` is the legacy app and is NOT the template). Decisions made with the user:
- **Replace ERPNext's built-in UAE regional model** with an own model (own settings, row-level `vat_category`, own VAT return doctype). ERPNext's regional fields (`is_zero_rated`, `company_trn`, `vat_emirate`, `reverse_charge`, UAE VAT 201 report) stay untouched but are ignored; a migration reads `UAE VAT Settings`.
- **Scope:** everything incl. profit margin, partial exemption/apportionment, capital assets, bad-debt relief, tax groups, excise.
- **E-invoicing:** include PINT AE XML generation plus pluggable ASP client.

## UAE VAT – key rules the app must encode
- **Law:** Federal Decree-Law 8/2017; Executive Regulation Cabinet Decision 52/2017 as amended (notably Cabinet Decision 100/2024, effective 15 Nov 2024: supply of multiple components, margin scheme, zero-rating of exports/international transport, documentation).
- **Rates/categories:** 5% standard; 0% zero-rated (exports, intl transport, certain education/health, precious metals investment, first sale of residential, crude oil/gas); exempt (financial services, residential lease/resale, bare land, local passenger transport); out of scope. Excise is separate (50% / 100% items).
- **TRN:** 15 digits; seller TRN mandatory on tax invoice.
- **Tax invoice:** "Tax Invoice" title, supplier name/address/TRN, customer name/address (and TRN if registered), unique number, issue date and supply date, line description/qty/unit price/discount/taxable amount/rate/VAT, VAT in **AED** even for foreign currency invoices, totals. Simplified invoice allowed under AED 10,000 (customer details optional). Tax credit note within 14 days of the adjusting event (Art. 61/70).
- **Reverse charge (RCM):** imports of services; goods/services from designated-zone suppliers; specified domestic cases (e.g. crude oil, scrap metal – to be confirmed against current FTA lists). Self-account output and input.
- **Designated Zones:** deemed outside UAE for goods only when customs conditions are met (Cabinet Decision 59/2017); transfers between zones out of scope; mainland buyer from a zone supplier applies RCM.
- **Place of supply / emirate:** standard-rated sales are reported per emirate (Abu Dhabi, Dubai, Sharjah, Ajman, UAQ, RAK, Fujairah).
- **VAT 201 return** (per FTA form): Sales boxes 1a–1g (emirate-wise standard rated: amount, VAT, adjustment), 2 (tourist refunds), 3 (reverse-charge supplies), 4 (zero-rated), 5 (exempt), 6 (goods imports), 7 (import adjustments), 8 (totals); Expenses box 9 (standard-rated expenses), 10 (RCM), 11 (totals); Net: 12 total due, 13 total recoverable, 14 payable, 15 refund request. Also profit-margin and GCC sections. Filing: quarterly (turnover < AED 150M) or monthly, due the 28th of the following month; staggered quarter options.
- **Registration thresholds:** mandatory AED 375,000, voluntary AED 187,500.
- **E-invoicing:** Peppol 5-corner model; **PINT AE** (UBL 2.1, CustomizationID `urn:peppol:pint:billing-1@ae-1`); XSD + Schematron validation; ~51 mandatory fields for tax invoice (49 commercial); line-level VAT in AED; tax category codes S, Z, E, G (export), O (outside scope), AE (reverse charge) plus margin-scheme/free-zone/deemed flags; invoice type 380, credit note 381; sender via Accredited Service Provider which signs and reports to FTA. Timeline: pilot 1 Jul 2026; mandatory 1 Jan 2027 (revenue ≥ AED 50M), 1 Jul 2027 (others), 1 Oct 2027 (government); penalties up to AED 5,000/month. **To be re-verified against FTA/MoF primary sources before coding** (the research was from secondary sources; rates, thresholds and the e-invoice field list must be checked against official PINT AE spec and Ministerial Decisions).

## Target structure (mirrors oman_compliance)
```
uae_compliance/uae_compliance/            hooks.py install.py uninstall.py exceptions.py modules.txt patches.txt
  patches/check_version_compatibility.py  patches/v1/…
  tests/__init__.py                       before_tests + helpers (UAE test company, AED)
  uae_compliance/                         module dir "UAE Compliance"
    constants/{custom_fields,emirates,designated_zones,tax_categories,gcc_countries}.py
    setup/__init__.py                     create_custom_fields, create_designated_zones, create_emirates, set_default_settings_currency
    client_scripts/item_tax_template.js, sales_invoice.js …
    doctype/uae_compliance_settings (Single) · uae_compliance_vat_account (child) · uae_designated_zone · uae_trn
            uae_vat_return · uae_vat_return_box · uae_einvoice_settings · uae_einvoice_log
    overrides/{company,party,transaction,sales_invoice,purchase_invoice,item_tax_template,payment_entry?}.py (+ test_*.py)
    print_format/{_shared/macros, uae_tax_invoice, uae_simplified_tax_invoice, uae_tax_credit_note}
    report/{uae_vat_sales_register, uae_vat_purchase_register, uae_vat_audit}/
    utils/{company,currency,trn,vat_category,tax_account,qr_code,migration}.py
    utils/vat_return/{__init__,totals,backfill}.py + sections/{standard_rated_by_emirate,tourist_refunds,reverse_charge_sales,zero_rated,exempt,imports,input_vat,margin_scheme,adjustments}.py
    einvoice/{pint_ae_builder,validators,asp_client(base),asp_clients/<provider>,status}.py   (replaces oman's empty api_classes)
```
Reused conventions from oman_compliance: `CUSTOM_FIELDS` dict applied via `create_custom_fields(..., ignore_validate=True)` from `after_install` and idempotent `patches.txt` entries with `#N` bump; `is_uae_company()` gate (Company.country == "United Arab Emirates") at the top of every hook; `item_wise_tax_detail` parsing filtered to the company's Output/Input VAT accounts; leading-blank `vat_category` Select so Frappe doesn't default it; Filed returns immutable via `for_update` lock; stale-check `generated_for_*` fields on the return; `before_install`/`before_migrate` version check; hooks `required_apps = ["frappe/erpnext"]`; ruff/pre-commit/CI as in oman_compliance (`.github/workflows`, `.claude/` hooks optional). Fields prefixed `uae_` (e.g. `uae_trn`) to avoid colliding with ERPNext regional's `company_trn`, `is_zero_rated`, `reverse_charge`.

## Naming collisions & ERPNext regional cleanup (added after review)
Frappe DocType names are global per site/bench, so none of ours may reuse an existing name:
- ERPNext already ships `UAE VAT Settings` and `UAE VAT Account` (erpnext/regional/doctype) → ours are **UAE Compliance Settings** and **UAE Compliance VAT Account**.
- `oman_compliance` on this bench already defines `Designated Zone` and `TRN` → ours are **UAE Designated Zone** and **UAE TRN**. Return child table is **UAE VAT Return Box** (not "Detail"); `UAE VAT Return` has no clash. Rule: every new DocType, report, print format and custom-field name is `UAE …`/`uae_…`-prefixed; a unit test asserts no DocType name is defined by another installed app.
- **Hide ERPNext's UAE fields** so users aren't confused: Property Setters (`hidden=1`, applied from `setup/__init__.py::hide_erpnext_uae_fields()` on install and a patch, idempotent) on Item `is_zero_rated`, `is_exempt`, `tax_code`; Purchase docs `company_trn`, `recoverable_standard_rated_expenses`, `reverse_charge`, `recoverable_reverse_charge`; Sales docs `company_trn`, `vat_emirate`, `tourist_tax_return`; item-row `tax_code`, `tax_rate`, `tax_amount`, `total_amount`; Address `emirate`/`vat_section`/`permit_no` as applicable; also hide the ERPNext `UAE VAT Settings` workspace link/report (`UAE VAT 201`) via Workspace/Report disable if safe. Field list to be confirmed against `erpnext/regional/united_arab_emirates/setup.py` at implementation. Caveat: property setters are site-wide, so this applies to every company on the site; document it. Because ERPNext's regional `update_itemised_tax_data`/RCM grand-total hooks stay active for UAE companies, Phase 2 must verify they do not double-handle RCM (they key off its own `reverse_charge` field, which stays empty).

## Item migration patch (added after review)
`patches/v1/migrate_item_vat_flags.py` (listed in `[post_model_sync]`, idempotent, dry-run/`company` arg like Oman's `migrate_legacy_item_vat_flags`):
- Items with `is_zero_rated=1` → `Zero Rated`, `is_exempt=1` → `Exempt` (both set → log and skip for manual review).
- Applied at **Item Tax Template** level (via `uae_vat_category`, matching templates named in ERPNext's `UAE VAT Zero`/`UAE VAT Exempted`/`UAE VAT 5%`) and as a default on Item (new field `uae_vat_category`) so new documents pick it up.
- Optional backfill for **draft** transactions' item rows; submitted documents are never modified (historic returns keep their original basis), and the VAT return derives category from the row's `uae_vat_category`, falling back to Item Tax Template then to the legacy flags for pre-migration invoices.
- Also migrates `UAE VAT Settings`/`UAE VAT Account` rows → `UAE Compliance Settings`, `company_trn`/`tax_id` → `uae_trn`, `vat_emirate` → row-level emirate, `tourist_tax_return`, and `reverse_charge` Y → `is_reverse_charge`. Summary printed and errors via `frappe.log_error`.

## Verification status (2026-10-09)
Primary-source check done: see [UAE_VERIFICATION.md](UAE_VERIFICATION.md). **Where it conflicts with the rules summarised above, the verification doc wins** (notably: capital assets 5 years for non-buildings; no 14-day credit-note rule; tax category `G` does not exist in PINT AE; no QR on e-invoices; simplified invoices not allowed for e-invoicing registrants; sweetened-drinks excise now volumetric; CD 149/2026 effective 1 Oct 2026).

## Decisions log
- v1 includes everything (Phases 0-6 in full, incl. advanced schemes and PINT AE); no release split.
- Site-wide hiding of ERPNext UAE fields via Property Setters is accepted.
- E-invoicing is provider-agnostic with multiple ASP adapters (see below).

- Box 1 of the VAT 201 keeps the 1a-1g lettering (1a Abu Dhabi, 1b Dubai, 1c Sharjah, 1d Ajman, 1e Umm Al Quwain, 1f Ras Al Khaimah, 1g Fujairah); labels live in a constants table, not hard-coded in logic.
- Designated zones: seed the current list from secondary sources (excl. Dubai Textile City, Al Quoz), admin-editable, flagged for re-verification.
- Penalties (late filing/payment): not computed in v1; show due dates and warnings only.
- Filing period: per-company setting (stagger S1-S4, S4 monthly); no AED 150M auto-rule.
- TRN: configurable regex, default `^100\d{12}$`, no checksum; separate 10-digit TIN field for Peppol.
- Repo: commit docs on `develop`, copy oman_compliance CI workflows and `.claude` hooks in Phase 0, then start Phase 0.

## Phases
0. **Foundation:** pyproject deps (`pyqrcode`, `pypng`, `lxml`), hooks skeleton, install/uninstall, version check, constants, CI + linter, docs (PLAN/ARCHITECTURE/CONFIGURATION md like Oman). Country gate util.
1. **Master data & settings:** custom fields (Company/Customer/Supplier `uae_trn` + Peppol ID, Arabic names, Address `emirate` + `designated_zone`, item-row `vat_category`/`vat_emirate`/RCM flags, Item Tax Template `vat_category` + "Fetch VAT Accounts" button); `UAE VAT Settings` (one Output/Input account pair per company, thresholds 10,000 simplified, 375,000/187,500 registration, filing frequency/stagger, excise accounts); UAE Designated Zone seed list; TRN validation (15 digits, numeric; check-digit rule if confirmed); migration from ERPNext `UAE VAT Settings`/`is_zero_rated`/`is_exempt` flags.
2. **Transaction logic:** `set_vat_category_defaults` (template → designated-zone address → emirate default); sales invoice validation (zero/exempt/OOS rows must carry no VAT, mixed-category same-item check, export detection, simplified flag, emirate required for standard-rated, AED amount); purchase invoice (RCM requires Output+Input rows, GCC/import/zone-supplier flags, postponed import VAT, non-recoverable/blocked input e.g. entertainment, apportionment); credit-note 14-day warning; tax-group handling.
3. **Print formats & QR:** Tax Invoice (AR/EN), Simplified Tax Invoice, Tax Credit/Debit Note; AED VAT disclosure for foreign currency; QR payload for non-e-invoice interim.
4. **VAT 201 return:** `UAE VAT Return` doctype generating boxes 1a–15 (+ margin scheme, GCC sections), emirate split, adjustment columns from returns, Generate/Mark as Filed, period validation (monthly/quarterly/stagger); registers and VAT audit report (invoice-level, ideally also FTA VAT audit file (FAF) export).
5. **Advanced schemes:** profit margin scheme, partial exemption (input apportionment, annual adjustment), capital asset scheme (10-year adjustment for ≥ AED 5M assets), bad-debt relief, tourist refund (box 2), excise tax.
6. **E-invoicing (PINT AE):** `UAE E-Invoice Settings` (ASP provider, credentials, environment), status doctype/log with the 7-state lifecycle (Draft → … → FTA Cleared) on Sales Invoice, XML builder (UBL 2.1, tax category mapping S/Z/E/G/O/AE from `vat_category`), XSD + Schematron validation, provider-agnostic `asp_client` base with idempotent submit, retries and scheduler-driven status polling (`scheduler_events`), inbound handling for Purchase Invoices, credit notes (381), XML retention, permissions.
7. **Hardening:** tests beside each module (pattern of oman test helpers incl. `_without_broken_third_party_hooks`), patches, docs, UAT with a real UAE company.

## E-invoicing provider strategy (decided)
Provider-agnostic. Multiple ASPs will be integrated, so Phase 6 builds an adapter framework, not a single integration:
- Abstract `ASPClient` interface (`einvoice/asp_client.py`): `submit(xml, idempotency_key)`, `get_status(ref)`, `fetch_inbound()`, `cancel/credit`, `validate_credentials()`; normalized status enum and error model shared by all adapters.
- Registry keyed by provider name; each adapter lives in `einvoice/asp_clients/<provider>.py` and is selected per company via UAE E-Invoice Settings (provider Select/Link, per-provider credential fields stored as Password fields, sandbox/production).
- PINT AE XML building, validation and the status lifecycle are provider-independent; only transport, auth and response mapping live in adapters.
- A mock/sandbox adapter ships first so the pipeline and tests need no real provider. Real adapters are added later without schema changes.

## Verification
- `bench --site <site> install-app uae_compliance` then `bench migrate` twice (idempotent); confirm custom fields and seeds exist.
- `bench --site <site> set-config allow_tests true && bench run-tests --app uae_compliance` (no server-test CI workflow; tests run locally).
- Manual: create UAE company (AED) → sales invoices across standard/zero/exempt/RCM/zone cases → generate `UAE VAT Return` and reconcile against ERPNext's built-in UAE VAT 201 on the same data; print the tax invoice; generate and validate a PINT AE XML against official XSD/Schematron.
- Confirm a non-UAE company on the same bench is unaffected (country gate).

## Open items to resolve before Phase 1
- Verify thresholds, 15-digit TRN rules, RCM domestic cases and e-invoice field list against FTA/MoF primary sources.
- ~~Pick the first ASP~~ Decided: provider-agnostic; multiple ASPs will be integrated over time (see Phase 6).
- Confirm 5M capital-asset and tourist-refund (Planet scheme) specifics.

## Sources
Research (web):
- [UAE e-invoicing mandate 2026: readiness, ASP, PINT AE (Avalara)](https://www.avalara.com/blog/en/europe/2026/03/uae-e-invoicing-mandate-2026-readiness-asp-pint-ae.html)
- [UAE electronic invoicing guidelines, Feb 2026 (Alvarez & Marsal)](https://www.alvarezandmarsal.com/thought-leadership/middle-east-tax-alert-uae-uae-electronic-invoicing-guidelines-february-2026-regulatory-clarifications-and-technical-implementation-framework)
- [UAE FTA e-invoicing: what your accounting system must support (Wafeq)](https://www.wafeq.com/en-ae/tax-and-reporting/uae-fta-e-invoicing-what-your-accounting-system-must-support-before-the-deadline)
- [Peppol e-invoicing in the UAE 2026-2027 guide (Infinite IT)](https://infinite-it.com/en/blog/peppol-e-invoicing-uae-guide)
- [UAE e-invoicing compliance checklist (Middle East Briefing)](https://www.middleeastbriefing.com/news/uae-e-invoicing-mandate-compliance-checklist/)
- [UAE e-invoicing mandate: timelines, Peppol model (Taxilla)](https://www.taxilla.com/uae-e-invoicing-mandate-peppol-compliance-guide)
- [UAE tax invoice format 2026 (InvoiceDataExtraction)](https://invoicedataextraction.com/blog/uae-vat-invoice-requirements)
- [UAE e-invoicing compliance guide (Aiverix)](https://aiverix.ae/guides/e-invoicing-compliance-guide)
- [UAE e-invoicing FAQs (Edify)](https://edifylearnings.com/faq-uae-einvoice)
- [How to file VAT return in the UAE (Zoho)](https://www.zoho.com/ae/books/vat/guides/vat-return.html)
- [File VAT returns UAE (Tally)](https://help.tallysolutions.com/docs/te9rel66/Tax_International/GCC_VAT/file_uae_vat_returns.htm)
- [VAT return UAE (ClearTax)](https://www.cleartax.com/ae/vat-return-uae)
- [Executive Regulation amendments (PwC)](https://pwc.com/m1/en/services/tax/me-tax-legal-news/2024/uae-vat-executive-regulation-amendments.html)
- [Recent amendment to UAE VAT Executive Regulation (Crowe)](https://www.crowe.com/ae/news/what-is-the-recent-amendment-to-uae-vat)
- [UAE guidance on recent amendment to VAT regulation (KPMG)](https://kpmg.com/us/en/taxnewsflash/news/2025/03/tnf-uae-guidance-on-recent-amendment-to-vat-regulation.html)
- [MoF announces amendments to Executive Regulations (WAM)](https://www.wam.ae/en/article/b5j3otl-ministry-finance-announces-amendments-executive)
- [Andersen UAE Indirect Tax Insights Q1 2025](https://ae.andersen.com/insights/Andersen UAE Indirect Tax Insights Q1 2025.pdf)
- [Designated Zones VAT Guide (u.ae)](https://u.ae/-/media/Documents-2023/Designated-Zones-VAT-Guide.ashx)
- [Designated zones VAT guide (PwC)](https://www.pwc.com/m1/en/tax/documents/2018/uae-vat-guide-on-designated-zones.pdf)
- [Designated zones VAT alert (Grant Thornton)](https://www.grantthornton.ae/globalassets/1.-member-firms/uae/pdfs/designated-zones---vat-alert_july-2018.pdf)
- [Reverse charge in the UAE (Wafeq)](https://www.wafeq.com/en-ae/uae-vat-guide/uae-vat-rates/reverse-charge-uae)
- [Tax credit notes in the UAE (Virtuzone)](https://virtuzone.com/blog/tax-credit-note/)
- [Federal Decree-Law No. 8 of 2017 and amendments (MoF)](https://mof.gov.ae/wp-content/uploads/2025/07/Federal-Decree-Law-No.-8-of-2017-and-amendments.pdf)
- [Federal Decree-Law No. 8 of 2017 (UAE MoJ)](https://elaws.moj.gov.ae/UAE-MOJ_LC-En/00_TAXES/UAE-LC-En_2017-08-23_00008_Markait.html?val=EL1)

Local code studied (this bench): `apps/oman_compliance`, `apps/oman_vat`, `apps/erpnext/erpnext/regional/united_arab_emirates`, `apps/erpnext/erpnext/regional/report/uae_vat_201`, `apps/erpnext/erpnext/regional/doctype/uae_vat_settings`.
