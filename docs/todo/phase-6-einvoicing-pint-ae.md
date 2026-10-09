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
