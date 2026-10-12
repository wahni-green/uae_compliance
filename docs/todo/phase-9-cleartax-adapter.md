# Phase 9 – ClearTax ASP adapter

A second provider next to Microvista, behind the same `ASPClient` interface (see [Phase 6](phase-6-einvoicing-pint-ae.md) and the architecture doc). No schema changes. The provider's documents are kept locally in `asp/cleartax/` (not committed): the API document (v1.0.1, 10 March 2026), the Postman collection and the V5 mapping sheet.

Behaviour below was established against the ClearTax sandbox on 12 Oct 2026, not only from the documents. Where the PDF and the sandbox disagree, the sandbox is followed.

## How ClearTax works
- **Format:** the invoice is sent as Base64 of a PINT AE JSON document, wrapped as `{"documents": [{"documentData", "documentFormat": "JSON", "uniqueIdentifier", "customFields"}], "schema": "CLEAR_UNIFIED_SCHEMA"}`. The JSON is camelCase, with amounts as `{"value", "currencyID"}`. ClearTax fills in `profileID`, `customizationID`, the fixed scheme codes and the AED line totals. It takes the invoice's fields, not the XML, so the adapter uses `OutgoingDocument.model`.
- **Authentication:** a client secret (`x-clear-client-secret`) is exchanged at `/integration/v1/authz/token` for an access token that does not expire (`valid_till` is null). **A new token revokes the previous one immediately**, so the token must be shared by every worker and renewed only after a 401.
- **Headers:** `x-cleartax-auth-token`, `x-clear-tin` (the company TIN) and `x-clear-country-code: AE`. `x-clear-trn` is not needed; a wrong one gives a 403, so it is sent only when configured.
- **Sending:** HTTP 200 with `Success: "true"` (a string) per document means accepted for processing, not valid. Rule failures (`ibr-...`, source `CLEARTAX`) and network failures (for example an unregistered buyer, source `PEPPOL`) appear afterwards in the status. Up to 10 documents per call; each gets its own result.
- **Status** (`GET documents/{id}/status`): `Submitted to exchange network`, then `Delivered to buyer network` / `Delivered to Buyer` (text varies in case), or `Failed`; `ReportingDetails[].Status` is `ACCEPTED` once the FTA has it, `NOT_SUBMITTED` or `WITHDRAWN` on failure. This takes about 10 seconds in the sandbox.
- **Number is single use:** the unique ID is `<TIN>_<number>_<type>_<year>`. Sending a number again, whether the first one was delivered or rejected, answers `300118` ("in progress") with no document ID.

## Mapping to the interface
- [x] `einvoice/asp_clients/cleartax.py`, `@register_provider`, listed in `registry._load_adapters`. Settings: Endpoint URL (the base URL), Client Secret; Extra Configuration `trn`, `branch`, `inbound_days` (default 30), `timeout`. The company's TIN is the `x-clear-tin`
- [x] Token: cached per account (endpoint, secret, TIN) with no expiry, renewed under a lock only after a 401; any 401 or 404 on a known URL means an auth failure (a malformed token gives a 404). `validate_credentials` renews it
- [x] Model to ClearTax JSON (`to_payload`, pure function, tested; the sandbox rejected the mapping sheet's `pricingExchangeRate` and the PDF's object forms, so the names and shapes below are the ones it accepted: `taxExchangeRate`, and lists for `billingReference` and `additionalDocumentReference`; an exempt line carries no VAT amount): parties with `0235:<TIN>` endpoints, `partyTaxScheme` with the TRN, legal entity with the registration type, lines with `classifiedTaxCategory`, `itemPriceExtension` in AED, document and line allowances, `taxTotal` with a tax subtotal per category, `legalMonetaryTotal`, `profileExecutionID` flags, invoice period, principal ID, delivery. Credit notes: `invoiceTypeCode` 381 or 81, `discrepancyResponse.responseCode`, and `billingReference` as a **list** of `{"additionalDocumentReference": {"id", "issueDate"}}` (the PDF's `invoiceDocumentReference` form fails rule ibr-055-ae)
- [x] `submit`: one document per call. The 200 answer with a document ID is `Submitted`. A refusal by a rule seen at once is `ProviderRejectedError` with the rule IDs. `300118` is not a failure: look up the document that is already held (see below) and return its real status. 400/406 (a payload the builder got wrong) is `ProviderRejectedError` with the message; 401 renews the token once; 429, 5xx and timeouts are the retryable errors
- [x] Finding a held document: `GET documents/query?einvoice-type=SALES` for the issue date (a range of at most 7 days, paged) returns `DocumentId`, `DocumentNumber` and `Status` and so gives the reference; `GET documents?einvoice-type=SALES&document-number=` returns the stored invoice JSON (no ID)
- [x] `get_status`: `Submitted to exchange network` -> Submitted; delivered with reporting `ACCEPTED` -> Cleared; delivered without it -> Delivered; `Failed` -> Rejected, with `ErrorDetails` as "rule id: text" and the source (`CLEARTAX` or `PEPPOL`). The text is compared without regard to case
- [x] `fetch_inbound` (written and unit tested from the shape of a stored invoice; **never run against a received document**): `documents/query?einvoice-type=PURCHASE` in windows of 7 days, then `GET documents?einvoice-type=PURCHASE&document-number=` for the invoice JSON, mapped to the keys of `inbound.parse_document`. **Blocked:** not testable without a second sandbox entity (see below)
- [x] Credit and cancel: a sent e-invoice is corrected by a credit note, as for Microvista. No cancel call is documented
- [x] The email endpoint is out of scope; the invoice PDF (`documents/print`, a real PDF in the sandbox) is not needed either
- [ ] Rejected invoices (open): the number is used up at the sandbox account (`300118`), which looks like an ASP account setting and not a rule of the API. Ask ClearTax for the setting that lets a failed number be sent again, as Microvista does; until then a retry of a rejected invoice finds the failed document and is rejected again

## Tests
- [x] Unit tests with recorded responses (token, accepted, `300118`, rule failure, `PEPPOL` failure, each status) and the payload checked against the Postman fixture and the V5 mapping sheet's paths
- [ ] A sandbox script, run only when `CLEARTAX_*` environment variables are set (not added: it was run by hand through the adapter, see below), covering send, status, credit note, a rule failure and the lookup. It uses new numbers each time (a number cannot be reused) and leaves documents in the sandbox
- [x] Every document type the builder supports was sent through the adapter to the sandbox on 12 Oct 2026 (documents generated by the existing tests): 380 standard, 381 credit note, 480 and 81 out of scope, zero rated and exempt mixes, USD, margin scheme (invoice and credit note), reverse charge (invoice and credit note), deemed supply, e-commerce, summary, continuous and agent billing. All were accepted and delivered, with the FTA report `ACCEPTED`
- [x] Builder gap found by the rules, fixed: an **export** invoice now carries the delivery details (ibr-152-ae) and the validators ask for the buyer's and the delivery's state or province (ibr-144-ae). An export sent through the adapter passed the rules (12 Oct 2026). The free trade zone case in the sweep was not a gap: the beneficiary ID is already required by the validators, and the test that sent it had none

## Documentation
- [x] Architecture doc: provider section for ClearTax; configuration doc: its settings and the token rule; verification doc: the sandbox findings above and the questions below
- [x] Remaining work list in [README.md](README.md)

## Questions for ClearTax
1. **Rejected numbers:** after `Failed`, a corrected invoice with the same number is blocked with `300118`. Is there an account setting that allows a failed number to be sent again (Microvista allows it), and can it be turned on for the sandbox and production accounts?
2. **Resend after a delivered invoice:** is `300118` the intended answer (the PDF says `DUP-201`/`DUP-202`), and is there a way to get the existing document ID back from the send call?
3. **Inbound:** how can a sandbox entity receive documents? A send to our own TIN is delivered but never appears in the `PURCHASE` query. Is there an acknowledge or dispute call, a webhook, and a list that returns the full document by ID rather than by (non-unique) number?
4. **Payload:** the PDF's field tables use PascalCase and `invoiceDocumentReference` for the preceding invoice, but the API takes camelCase and `additionalDocumentReference`. Is there a corrected document?
5. **Date limits:** the query range limit is 7 days in the sandbox, and 3 in the PDF. Is the issue date really required to be the current date? The sandbox accepted a past date.
6. **Rules:** a zero-rated line without an exemption reason was accepted although the PDF says it is mandatory. Is that checked in production?
7. **Tokens:** a new token revokes the old one. Can an account have more than one token, and what are the production limits (the PDF gives only the token API's 100 calls an hour)?
8. **Errors:** payload errors come back as HTTP 406 with a Java class name, and a malformed token gives 404. Are these final?
9. **TRN:** is `x-clear-trn` ever required (the PDF says so for status, query and print)?
