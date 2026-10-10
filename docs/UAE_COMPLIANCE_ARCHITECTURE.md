# Architecture

Mirrors `oman_compliance`. See [UAE_COMPLIANCE_PLAN.md](UAE_COMPLIANCE_PLAN.md) for the target tree.

- **Country gate:** every hook starts with `utils/company.py::is_uae_company(company)`, so non-UAE
  companies on the same bench are unaffected.
- **Naming:** all DocTypes, reports, print formats and custom fields are `UAE ...` / `uae_...` prefixed;
  ERPNext (`UAE VAT Settings`, `UAE VAT Account`) and `oman_compliance` (`Designated Zone`, `TRN`) already
  own other names.
- **Setup:** `install.after_install` and idempotent `patches.txt` entries both call
  `setup/__init__.py` functions. `constants/custom_fields.py` holds the custom-field definitions.
- **Constants:** `constants/emirates.py` (Box 1 1a-1g order), `tax_categories.py` (VAT categories and
  PINT AE codes), `gcc_countries.py`.
- **Version check:** `patches/check_version_compatibility.py` runs on install and migrate (Frappe >= 15).
- **Tests:** `tests/__init__.py::before_tests` bootstraps a UAE (AED) test company on an empty site.

## E-invoicing (PINT AE)
- `einvoice/pint_ae_builder.py` builds the UBL 2.1 XML of a Sales Invoice or return from the invoice, the company and customer (TIN as the Peppol endpoint, TRN, legal registration), their addresses (emirate subdivision codes) and the item rows (VAT category, exemption reason, HS code for goods, service accounting code for services). Supported: standard tax invoices (380) and tax credit notes (381) for standard rated, zero rated and exempt supplies, exports, and foreign-currency documents with their AED figures. Out of scope lines (category O, no rate) and the transaction types free trade zone beneficiary, deemed supply and e-commerce are supported. A document whose lines are all exempt or out of scope is issued as an out of scope invoice (480) or credit note (81), as the specification requires (rules ibr-151-ae and ibr-122-ae); a deemed supply cannot be one. Reverse charge supplies by the supplier (category AE, rate 5% with no VAT, the type of goods and the item's GTIN) are supported for oil, natural gas, pure hydrocarbons, electronic devices and precious metals and stones; metal scrap has no code in the specification and is refused. Profit margin scheme invoices are sent in category N ("standard rate additional VAT"): every line is the price (the net amount plus the VAT on its margin), no VAT is stated, and the document carries the margin transaction type; the rules allow no other category on such a document. Refused with a clear message: and a company whose own currency is not AED. Summary, continuous, agent billing and self-billing documents are not produced.
- `einvoice/validators.py` checks the arithmetic, identifiers and conditional rules of the specification in Python. It is not the full Schematron.
- **Validating against the official rules.** The tests can also run the specification's own Schematron and the OASIS UBL schema, which are not bundled: unpack `resources.zip` from https://docs.peppol.eu/poac/ae/pint-ae/ and the `xsd` folder of UBL-2.1.zip, install `saxonche`, and run `UBL_XSD_DIR=<xsd> PINT_AE_RESOURCES_DIR=<resources> bench --site <site> run-tests --app uae_compliance --module uae_compliance.uae_compliance.einvoice.test_pint_ae`. Without them those tests are skipped. This found two mistakes in the first version of the builder (the service accounting code belongs in `AdditionalItemIdentification`, and an exempt category carries no rate), so run it again whenever the builder or the specification version changes.

## Sending pipeline (`einvoice/pipeline.py`)
- On submission of an in-scope Sales Invoice (`before_submit` validates, `on_submit` queues) a **UAE E-Invoice Log** is created, the XML is built and checked, and the log is `Generated` or `Invalid`. In scope means: the company has an enabled row in UAE E-Invoice Settings, the invoice is dated on or after its start date, and the customer is not an individual.
- `submit_log` sends a `Generated` log to the company's provider. It takes a row lock on the log, so the queued job, the scheduler and a manual retry never send the same document twice. The log's `idempotency_key` is kept after a timeout (the provider may hold the document) and renewed only after a definite refusal.
- A transient failure (`ServiceProviderError`) is retried with exponential backoff up to the settings' retry limit, then the log is `Failed`. A `ProviderRejectedError` is final (`Rejected`).
- `process_pending` runs every 5 minutes: it sends logs that are due (new logs are due at once, so a lost job is picked up) and polls `Submitted`/`Delivered` logs, the least recently checked first. Status goes `Submitted` -> `Delivered` -> `Cleared` (reported to the FTA).
- Cancelling an invoice is refused once it has been sent, and while the outcome of an attempt is unknown; an unsent invoice's log is closed as `Invalid`. A sent invoice is corrected with a credit note.
- A log is kept for 5 years from the invoice date, or from clearance if later, and cannot be deleted before then.
- A log cannot be sent or polled with a different provider or environment from the ones it was created under. For an unsent log, changed settings use up send attempts until the retry limit marks it `Failed`, and it then needs a manual **Retry** once the original settings are restored. Polling of a sent log simply keeps waiting.

## Providers (`einvoice/asp_client.py`, `registry.py`, `asp_clients/`)
Providers are adapters of `ASPClient` registered with `@register_provider` and listed in `registry._load_adapters`. An adapter gets the invoice as PINT AE XML and as a plain-data model (`OutgoingDocument.xml` / `.model`), so providers whose API takes fields instead of a document need no second builder. The shared layer owns retries, idempotency, polling and retention; adapters only translate. Included: `Mock` (development and tests) and `Microvista`.

**Microvista** takes the invoice as JSON, builds and checks the PINT AE document itself, sends it over Peppol and reports it to the FTA. Status codes map as: delivered and reported to the FTA -> Cleared; delivered to the buyer only -> Delivered; failed codes -> Rejected, with the rule IDs and texts it reports. A number that already exists is looked up and its real status taken instead of failing, because that is what a retry after a lost response looks like. Tokens are cached per account for five minutes.

To add a provider: subclass `ASPClient`, implement `submit`, `get_status`, `fetch_inbound` and `validate_credentials`, register it, and add it to `_load_adapters`. No schema changes are needed.

## Inbound (`einvoice/inbound.py`)
`receive(company)` asks the provider for documents it holds for the company's TIN and logs each new one as an inbound **UAE E-Invoice Log**. A document may arrive as XML or as a model. One that cannot be read, has an invalid date, is addressed to someone else, or (when it arrives as a model) lacks required fields, is logged as `Invalid` with the reason and never stops the others. XML is not checked for missing fields beyond what parsing needs, so `Delivered` does not mean the document was validated against the specification. The sender is matched to a Supplier by TIN, then TRN. Creating Purchase Invoices from these logs is not built.

## VAT 201 and schemes (`utils/vat_return/`)
`get_invoice_rows` reads the company's submitted invoice rows once; `sections/*` derive each box from them. Credit notes net into the amount and VAT columns; the adjustment column holds only non-transaction adjustments (UAE VAT Adjustment). Schemes: partial exemption (`apportionment.py`, annual adjustment), capital assets (UAE Capital Asset), bad debt relief, profit margin, tourist refunds, excise (UAE Excise Rate) and tax groups (`group.py`; one return for the group's representative). A sale under the reverse charge is left out of every box, as the supplier does not report the tax (docs/UAE_VERIFICATION.md section 8); this is a conservative reading, as no primary source says where the value belongs. A Filed return is locked, and a return generated before its data changed is flagged stale.
