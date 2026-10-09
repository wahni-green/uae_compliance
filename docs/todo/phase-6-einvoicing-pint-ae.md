# Phase 6 – E-invoicing (PINT AE)

- [ ] Confirm official PINT AE spec, XSD, Schematron and FTA/MoF timelines
- [ ] DocTypes: UAE E-Invoice Settings (provider, credentials, environment), UAE E-Invoice Log
- [ ] Status lifecycle on Sales Invoice (Draft -> ... -> FTA Cleared)
- [ ] `einvoice/pint_ae_builder.py`: UBL 2.1, CustomizationID `urn:peppol:pint:billing-1@ae-1`, tax category mapping S/Z/E/G/O/AE
- [ ] Credit notes (type 381), line-level VAT in AED
- [ ] `einvoice/validators.py`: XSD + Schematron
- [ ] `einvoice/asp_client.py` abstract base: submit (idempotency key), get_status, fetch_inbound, credit/cancel, validate_credentials; normalized status enum and error model
- [ ] Provider registry + per-company provider selection in UAE E-Invoice Settings (credentials as Password fields, sandbox/production)
- [ ] Mock/sandbox adapter (`asp_clients/mock.py`) used for tests; real adapters added later per provider, no schema changes
- [ ] Retries and correlation IDs handled in the shared layer, not in adapters
- [ ] Scheduler status polling (`scheduler_events`)
- [ ] Inbound handling for Purchase Invoices
- [ ] XML retention and permissions
- [ ] Tests with sample documents

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
