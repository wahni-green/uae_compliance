# Configuration

## UAE Compliance Settings (Single)
- **VAT Accounts** (one row per company): Output VAT account (required), Input VAT account, Excise Tax account, Filing Frequency (Quarterly Stagger 1/2/3 or Monthly).
- **Thresholds (AED):** simplified tax invoice 10,000; mandatory registration 375,000; voluntary 187,500.
- **Cash Payment Limit for Input VAT** (AED, empty or 0 = off): Executive Regulation Art 54(3), added by Cabinet Decision 149/2026, makes input VAT non-recoverable on a supply above an amount set by the Minister of Finance that is paid in cash. The amount had not been published on 10 October 2026, so it is a setting: enter it when it is, and until then the rule is off. A Purchase Invoice counts as paid in cash when it is paid on the invoice itself, or by a submitted Payment Entry, with a Mode of Payment of type Cash, or when it is marked **Cash Payment Intended** (the regulation covers a payment intended to be made in cash); the supply's value (the invoice total) is compared with the limit, not the cash part, as the regulation refers to the value of the supply. The VAT return reads this when it is generated, so a cash payment made later changes the return: a draft return then has to be generated again. A payment already reported in a filed return is not revisited.
- **Identifier validation:** `TRN Pattern` (default `^1[0-9]{12}03$`, the format the PINT AE Schematron checks: 15 digits, starting with 1 and ending with 03) and `TIN Pattern` (default `^1[0-9]{9}$`). The FTA publishes no checksum, and the patterns are editable. Spaces and hyphens are stripped before matching.

## Master data
- `UAE TRN` / `UAE TIN` fields on Company, Customer and Supplier; Arabic names; Address emirate and designated zone.
- **UAE Designated Zone** is seeded from secondary sources and is admin-editable; re-verify against the FTA legislation page.
- **VAT Category** on Item, Item Tax Template and item rows (Standard Rated / Zero Rated / Exempt / Out of Scope; blank means defaulted later).
- Item Tax Template has a **Fetch VAT Accounts** button that adds the company's Output/Input accounts.
- **UAE Exemption Reason** is the list of VAT exemption reason codes (IBT-186). It starts with the four codes of the specification, and finance maintains it: nothing already edited is overwritten on migrate. The **VAT Exemption Reason** is a Link to it on the Item Tax Template, the Item and the item rows. An exempt row takes the reason of its Item Tax Template, else of its Item, and an exempt row without one cannot be submitted.
- **UOM:** the **UN/ECE Code** (`uae_uncefact_code`) is the unit code sent with each line. Migrate fills the blank codes of the units Nos, Unit, Kg, Gram, Litre, Meter, Box, Pair, Hour, Day, Month and Pkt; any other unit needs its code entered, or an e-invoice with that unit cannot be submitted. There is no fallback to a piece (H87).
- **Customer:** the **Buyer Category** (B2B, B2G or B2C; B2C is out of scope for e-invoicing). A Trade License needs its issuing authority, a Passport its issuing country, and a Legal Registration ID its type. The form and the server both enforce these.
- **Address:** the **Emirate** is required when the country is United Arab Emirates.
- **Company:** a company that sends e-invoices needs its Legal Registration Type, and for a Trade License its issuing authority. This is checked when the company is saved and when an invoice is submitted.
- The report **UAE Master Data Issues** lists customers and addresses saved before these rules that break them, and addresses whose country is another spelling of the UAE (such as "UAE"). It changes nothing.

## ERPNext's built-in UAE localization
Its custom fields (`is_zero_rated`, `is_exempt`, `vat_emirate`, `company_trn`, `reverse_charge`, ...) are hidden with Property Setters, which apply site-wide. Data is kept. On install and migrate, existing data is migrated: Item flags to VAT Category, UAE VAT Settings accounts to UAE Compliance Settings (liability = Output, asset = Input; ambiguous cases are logged in Error Log), TRN, Arabic names, emirate, tourist refunds and reverse-charge flags. Submitted documents' item rows are never modified.

## VAT 201 return
Create a **UAE VAT Return** for the company and period, then **Generate Return**. It fills boxes 1a-1g, 2-11 and the net figures (boxes 12-14); tick **Request a Refund** for box 15. Standard rated sales need a VAT Emirate on the invoice. **Mark as Filed** locks the return. **Download FAF** produces the FTA Audit File for the period. The **UAE VAT Sales Register** and **UAE VAT Purchase Register** list the invoices behind each box.

## E-invoicing
Open **UAE E-Invoice Settings** and add a row per company: tick **Enabled**, choose the **Provider** and **Environment** (Sandbox or Production), set **E-Invoice From** (invoices dated earlier are not sent), and fill in the provider's connection fields. **Retry Limit** (default 5) applies to all companies. **Block Cancellation After an E-Invoice Was Sent** (off by default) refuses to cancel any invoice whose sending was attempted, including a rejected one, so that a credit note is issued instead. **Exclude Sales Within the VAT Group** leaves out sales to a customer that is an internal customer (Represents Company) of another member of the invoicing company's UAE Tax Group, up to the date in **Exclude Until** (31 December 2028 for 24 months from 1 January 2027). **Require HSN/SAC Code on Items** is on by default. The company needs its **UAE TIN** (the Peppol endpoint, 10 digits), TRN and **Legal Registration** (type and ID: Trade License with its issuing authority, Emirates ID, Passport with its issuing country, or Cabinet Decision); customers that are businesses need their TIN, or are sent to the predefined endpoint for buyers not on the network. Invoices to individuals and to customers whose Buyer Category is B2C are not e-invoiced.

Each Sales Invoice records the result on submission: **E-Invoice Applicable**, and **Why Not Applicable** when it is not (start date, exclusion, B2C or VAT group). The invoice also needs a **Customer Address**. A charge in the taxes table that is not VAT (freight) cannot be sent, and the invoice is refused: enter it as an item row. A discount on the whole invoice is sent, spread into the item rows. A Sales Taxes and Charges Template that charges 0% VAT cannot be combined with an item whose Item Tax Template raises the rate.

**Rounding:** the site's Rounding Method (System Settings) should be Commercial Rounding. Banker's Rounding can make the VAT differ by 0.01 from the network's figure. The app warns and does not change the setting.

**Cancellation workflow:** a workflow action such as "Request for cancelation" is part of the site, not of this app. To hide it once an e-invoice exists, add the condition `not doc.uae_einvoice_status` to its transition.

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

### ClearTax
| Field | Value |
|---|---|
| Provider | ClearTax |
| Endpoint URL | the API base, for example `https://api-sandbox.mea.cleartax.com` (production: `https://api.mea.cleartax.com`) |
| Client ID | not used |
| Client Secret | the API client's secret, from the ClearTax portal |
| Extra Configuration | optional JSON: `trn` and `branch` (sent as `x-clear-trn` and `x-clear-branch`; leave them out unless ClearTax asks, as a TRN that does not match is refused with a bare 403), `inbound_days` (default 30) and `timeout` in seconds (default 60) |

The company's UAE TIN is the taxpayer. ClearTax gives one access token per client secret and a new one revokes the old, so companies on the same account share it, and **no other system may create a token for the same client secret** (an integration that does so signs this one out; the app renews its token once when that happens). The sandbox allows 10 token requests an hour. The client secret may also be restricted to allowed IP addresses in the portal.

A document number can be sent once on the sandbox account tested: ClearTax keeps a rejected document and blocks its number. The app therefore never sends a rejected number again, with any provider: the user cancels the rejected invoice and amends it (a new number).

### Mock
Provider `Mock` talks to nobody. Extra Configuration `{"behavior": "clear"}` clears documents over successive status checks. Set `behavior` to `reject` to reject documents, or to `timeout` to simulate a timeout on submission. For development and tests only.

## Schemes and other documents
- **UAE VAT Adjustment:** bad debt relief and other non-transaction adjustments that appear in the adjustment column of the return.
- **UAE Capital Asset:** assets of AED 5,000,000 or more whose input VAT is adjusted over 5 years (10 for buildings).
- **UAE Excise Rate:** excise rates by category; **UAE Tax Group:** the members and representative of a VAT group.
- **Print formats:** UAE Tax Invoice, UAE Simplified Tax Invoice and UAE Tax Credit Note. VAT is shown in AED on foreign-currency documents. QR codes (setting **Show QR Code**) are not printed for e-invoicing companies, as the e-invoice replaces them.
- **Product Bundle > Principal Component:** names the component whose VAT treatment a composite supply (an inseparable bundle) takes. The bundle item must carry that VAT Category, Item Tax Template and rate; a warning shows when its category differs.
