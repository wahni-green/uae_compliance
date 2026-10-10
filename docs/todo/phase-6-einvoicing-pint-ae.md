# Phase 6 – E-invoicing (PINT AE)

- [ ] Confirm official PINT AE spec, XSD, Schematron and FTA/MoF timelines
- [x] DocTypes: UAE E-Invoice Settings (provider, credentials, environment), UAE E-Invoice Log
- [x] Status lifecycle on Sales Invoice (Draft -> ... -> FTA Cleared)
- [x] `einvoice/pint_ae_builder.py`: UBL 2.1, CustomizationID `urn:peppol:pint:billing-1@ae-1`, tax category mapping S/Z/E
- [ ] Tax categories O (out of scope) and AE (reverse charge) are refused for now; there is no `G` in PINT AE
- [x] Credit notes (type 381), line-level VAT in AED
- [x] `einvoice/validators.py`: Python checks of the rules; the official XSD and Schematron run in the tests when supplied
- [x] `einvoice/asp_client.py` abstract base: submit (idempotency key), get_status, fetch_inbound, credit/cancel, validate_credentials; normalized status enum and error model
- [x] Provider registry + per-company provider selection in UAE E-Invoice Settings (credentials as Password fields, sandbox/production)
- [x] Mock/sandbox adapter (`asp_clients/mock.py`) used for tests; real adapters added later per provider, no schema changes
- [x] Retries and correlation IDs handled in the shared layer, not in adapters
- [x] Scheduler status polling (`scheduler_events`)
- [x] Inbound handling: documents received through the provider are logged (PR 6c); creating Purchase Invoices from them is not built
- [x] XML retention and permissions
- [x] Tests with sample documents (and the official Schematron/XSD when supplied)

## From verification (see ../UAE_VERIFICATION.md)
- [ ] Pin PINT-AE v1.0.4; load code lists and Schematron from resources.zip; XSD from OASIS UBL 2.1
- [ ] Tax category codes S, E, O, AE, Z, N (N for margin; check Greek vs Latin N); no `G`
- [ ] Transaction-type flags in ProfileExecutionID (FTZ, deemed, margin, summary, continuous, agent, e-commerce, export)
- [ ] Invoice types 380/480, credit notes 381/81; TaxCurrencyCode AED + `aedtotal-incl-vat` document reference
- [ ] Participant ID `0235:<TIN>` with predefined endpoints 9900000097/98/99; legal registration ID type (TL/EID/PAS/CD)
- [ ] Support self-billing CustomizationID
- [ ] No QR code; retain XML 5 years (7 real estate)
- [ ] Exclusions: B2C, exempt financial services, imports under RCM, etc.

## PR 6a: PINT AE XML builder and validators
- [x] Pin PINT-AE v1.0.4: builder follows the official samples; checked against the official Schematron and the OASIS UBL 2.1 schema (not bundled; see the architecture doc)
- [x] Tax category codes S, Z, E (no `G`; N for the margin scheme is not produced yet, so margin invoices are refused)
- [x] ProfileExecutionID flags for the margin scheme and exports; the other flags are not produced
- [x] Invoice 380 and credit note 381; TaxCurrencyCode AED, exchange rate and `aedtotal-incl-vat` reference for foreign currency
- [x] Participant ID `0235:<TIN>` with predefined endpoints 9900000098 (buyer not on the network) and 9900000099 (export); legal registration ID with type (TL, EID, PAS, CD) on Company and Customer
- [x] No QR code on the e-invoice
- [x] `UAE VAT` TRN default pattern now follows the specification (15 digits, starting with 1 and ending with 03)
- [ ] Self-billing, summary, continuous, agent billing, deemed supply, free trade zone beneficiary, reverse charge and out of scope documents

## PR 6b: provider framework and sending pipeline
- **UAE E-Invoice Settings** (one row per company: provider, environment, "E-Invoice From" date, endpoint, client ID, client secret as a Password, extra JSON configuration) and **UAE E-Invoice Log** (one per document: status, provider reference, idempotency key, attempts, next attempt, the XML, the provider's response, errors, retention date).
- **Providers:** adapters subclass `ASPClient` (submit an `OutgoingDocument` with an idempotency key, get status, fetch inbound, validate credentials). A document carries the PINT AE XML and the same invoice as a plain-data model (`PintAEBuilder.build_all`), because some providers (Microvista, for one) take the invoice's fields as JSON instead of an XML document, register with `@register_provider`, and are listed in `einvoice/registry.py`. The Mock adapter (behaviours `clear`, `reject`, `timeout`) is the only one so far. A real adapter is one file plus one line in the registry.
- **Statuses:** Pending, Generated, Invalid, Submitted, Delivered, Cleared (terminal success: reported to the FTA), Rejected, Failed.
- **Flow:** before submission an in-scope invoice is built and checked, and an invoice that would be invalid is not issued (one the builder does not support yet is issued and logged as Invalid). On submission the log is created and the send is queued; the scheduler (every five minutes) sends what is due, retries transient failures with backoff (1, 2, 4 ... minutes, up to the attempt limit) and polls sent documents until Cleared or Rejected. A provider's refusal is final; a manual **Retry** rebuilds the XML from the invoice as it is now.
- **Scope:** companies with e-invoicing enabled, invoices dated on or after "E-Invoice From", and customers that are not individuals (B2C is out of scope).
- **A sent e-invoice cannot be cancelled**; a credit note corrects it. The log cannot be deleted before its retention date (five years from the invoice date, extended to five years from clearance).
- Still open: inbound handling (PR 6c), `UAE VAT` reconciliation of e-invoice status in reports.

## PR 6c: inbound documents
- The scheduler fetches what each enabled company's provider holds for it (`ASPClient.fetch_inbound`) and logs each new document (by provider reference) as an Inbound UAE E-Invoice Log: number, UUID, type, date, sender name and TIN, currency, total, and the XML, kept for five years. The sender is matched to a Supplier by TIN, then by TRN. A document that cannot be read, or that is addressed to another TIN or TRN, is logged as Invalid with the reason.
- Not built: turning a received invoice into a Purchase Invoice (it needs a mapping of the sender's lines to items and accounts), acknowledging or disputing a received document, and validating the sender's document against the specification.

## Providers
- [x] Microvista adapter (PR 6d), verified against its sandbox: submit, duplicate recovery, polling to Cleared. Credit notes and inbound listing not yet exercised live.
- [ ] Credit-note payload shape and the inbound listing against the sandbox, then production
