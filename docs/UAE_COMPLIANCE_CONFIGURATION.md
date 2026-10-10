# Configuration

## UAE Compliance Settings (Single)
- **VAT Accounts** (one row per company): Output VAT account (required), Input VAT account, Excise Tax account, Filing Frequency (Quarterly Stagger 1/2/3 or Monthly).
- **Thresholds (AED):** simplified tax invoice 10,000; mandatory registration 375,000; voluntary 187,500.
- **Identifier validation:** `TRN Pattern` (default `^1[0-9]{12}03$`, the format the PINT AE Schematron checks: 15 digits, starting with 1 and ending with 03) and `TIN Pattern` (default `^1[0-9]{9}$`). The FTA publishes no checksum, and the patterns are editable. Spaces and hyphens are stripped before matching.

## Master data
- `UAE TRN` / `UAE TIN` fields on Company, Customer and Supplier; Arabic names; Address emirate and designated zone.
- **UAE Designated Zone** is seeded from secondary sources and is admin-editable; re-verify against the FTA legislation page.
- **VAT Category** on Item, Item Tax Template and item rows (Standard Rated / Zero Rated / Exempt / Out of Scope; blank means defaulted later).
- Item Tax Template has a **Fetch VAT Accounts** button that adds the company's Output/Input accounts.

## ERPNext's built-in UAE localization
Its custom fields (`is_zero_rated`, `is_exempt`, `vat_emirate`, `company_trn`, `reverse_charge`, ...) are hidden with Property Setters, which apply site-wide. Data is kept. On install and migrate, existing data is migrated: Item flags to VAT Category, UAE VAT Settings accounts to UAE Compliance Settings (liability = Output, asset = Input; ambiguous cases are logged in Error Log), TRN, Arabic names, emirate, tourist refunds and reverse-charge flags. Submitted documents' item rows are never modified.

## VAT 201 return
Create a **UAE VAT Return** for the company and period, then **Generate Return**. It fills boxes 1a-1g, 2-11 and the net figures (boxes 12-14); tick **Request a Refund** for box 15. Standard rated sales need a VAT Emirate on the invoice. **Mark as Filed** locks the return. **Download FAF** produces the FTA Audit File for the period. The **UAE VAT Sales Register** and **UAE VAT Purchase Register** list the invoices behind each box.

## E-invoicing
Open **UAE E-Invoice Settings** and add a row per company: tick **Enabled**, choose the **Provider** and **Environment** (Sandbox or Production), set **E-Invoice From** (invoices dated earlier are not sent), and fill in the provider's connection fields. **Retry Limit** (default 5) applies to all companies. The company needs its **UAE TIN** (the Peppol endpoint, 10 digits), TRN and **Legal Registration** (type and ID: Trade License with its issuing authority, Emirates ID, Passport with its issuing country, or Cabinet Decision); customers that are businesses need their TIN, or are sent to the predefined endpoint for buyers not on the network. Invoices to individuals are not e-invoiced.

Each invoice shows its e-invoice status; the **UAE E-Invoice Log** holds the XML, the provider's response, errors and attempts, and has **Retry** and **Check Status** buttons. Changing a company's provider or environment does not move existing logs: they keep using the ones they were created under, so finish or retry them before switching.

### Microvista
| Field | Value |
|---|---|
| Provider | Microvista |
| Endpoint URL | the API base URL of the environment |
| Client ID | the API secret (`x-apiSecret`) |
| Client Secret | the secret key (`x-secretKey`) |
| Extra Configuration | JSON: `{"client_code": "<code>"}`; optional `version` (default `v1`), `inbound_days` (how far back received invoices are listed, default 30) and `timeout` in seconds (default 60) |

The company's UAE TIN is the taxpayer. `client_code` is required; a missing one is reported before any call. Use the sandbox until a document has been sent, polled to Cleared and checked in Microvista's portal.

### Mock
Provider `Mock` talks to nobody. Extra Configuration `{"behavior": "clear"}` clears documents over successive status checks. Set `behavior` to `reject` to reject documents, or to `timeout` to simulate a timeout on submission. For development and tests only.

## Schemes and other documents
- **UAE VAT Adjustment:** bad debt relief and other non-transaction adjustments that appear in the adjustment column of the return.
- **UAE Capital Asset:** assets of AED 5,000,000 or more whose input VAT is adjusted over 5 years (10 for buildings).
- **UAE Excise Rate:** excise rates by category; **UAE Tax Group:** the members and representative of a VAT group.
- **Print formats:** UAE Tax Invoice, UAE Simplified Tax Invoice and UAE Tax Credit Note. VAT is shown in AED on foreign-currency documents. QR codes (setting **Show QR Code**) are not printed for e-invoicing companies, as the e-invoice replaces them.
