# Configuration

## UAE Compliance Settings (Single)
- **VAT Accounts** (one row per company): Output VAT account (required), Input VAT account, Excise Tax account, Filing Frequency (Quarterly Stagger 1/2/3 or Monthly).
- **Thresholds (AED):** simplified tax invoice 10,000; mandatory registration 375,000; voluntary 187,500.
- **Identifier validation:** `TRN Pattern` (default `^100[0-9]{12}$`) and `TIN Pattern` (default `^1[0-9]{9}$`). The FTA publishes no official TRN format or checksum, so these are editable. Spaces and hyphens are stripped before matching.

## Master data
- `UAE TRN` / `UAE TIN` fields on Company, Customer and Supplier; Arabic names; Address emirate and designated zone.
- **UAE Designated Zone** is seeded from secondary sources and is admin-editable; re-verify against the FTA legislation page.
- **VAT Category** on Item, Item Tax Template and item rows (Standard Rated / Zero Rated / Exempt / Out of Scope; blank means defaulted later).
- Item Tax Template has a **Fetch VAT Accounts** button that adds the company's Output/Input accounts.

## ERPNext's built-in UAE localization
Its custom fields (`is_zero_rated`, `is_exempt`, `vat_emirate`, `company_trn`, `reverse_charge`, ...) are hidden with Property Setters, which apply site-wide. Data is kept. On install and migrate, existing data is migrated: Item flags to VAT Category, UAE VAT Settings accounts to UAE Compliance Settings (liability = Output, asset = Input; ambiguous cases are logged in Error Log), TRN, Arabic names, emirate, tourist refunds and reverse-charge flags. Submitted documents' item rows are never modified.

## VAT 201 return
Create a **UAE VAT Return** for the company and period, then **Generate Return**. It fills boxes 1a-1g, 2-11 and the net figures (boxes 12-14); tick **Request a Refund** for box 15. Standard rated sales need a VAT Emirate on the invoice. **Mark as Filed** locks the return. **Download FAF** produces the FTA Audit File for the period. The **UAE VAT Sales Register** and **UAE VAT Purchase Register** list the invoices behind each box.
