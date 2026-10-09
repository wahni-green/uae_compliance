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
- `einvoice/pint_ae_builder.py` builds the UBL 2.1 XML of a Sales Invoice or return from the invoice, the company and customer (TIN as the Peppol endpoint, TRN, legal registration), their addresses (emirate subdivision codes) and the item rows (VAT category, exemption reason, HS code for goods, service accounting code for services). Supported: standard tax invoices (380) and tax credit notes (381) for standard rated, zero rated and exempt supplies, exports, and foreign-currency documents with their AED figures. Refused with a clear message: reverse charge and out of scope supplies, margin scheme invoices, and a company whose own currency is not AED.
- `einvoice/validators.py` checks the arithmetic, identifiers and conditional rules of the specification in Python. It is not the full Schematron.
- **Validating against the official rules.** The tests can also run the specification's own Schematron and the OASIS UBL schema, which are not bundled: unpack `resources.zip` from https://docs.peppol.eu/poac/ae/pint-ae/ and the `xsd` folder of UBL-2.1.zip, install `saxonche`, and run `UBL_XSD_DIR=<xsd> PINT_AE_RESOURCES_DIR=<resources> bench --site <site> run-tests --app uae_compliance --module uae_compliance.uae_compliance.einvoice.test_pint_ae`. Without them those tests are skipped. This found two mistakes in the first version of the builder (the service accounting code belongs in `AdditionalItemIdentification`, and an exempt category carries no rate), so run it again whenever the builder or the specification version changes.
