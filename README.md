# UAE Compliance

UAE VAT and e-invoicing for ERPNext, for companies registered in the United Arab Emirates.

The app only acts on a company whose country is United Arab Emirates, so other companies on the
same site are not affected.

## What it does

- **VAT categories** (Standard Rated, Zero Rated, Exempt, Out of Scope) on Item Tax Templates and on the rows of sales and purchase documents.
- **VAT 201 return:** boxes 1a-1g (by emirate) to 15, generated from the invoices. Includes the FTA Audit File (FAF), a sales register and a purchase register.
- **Tax invoices, simplified tax invoices and tax credit notes**, in English and Arabic, with the VAT in AED for foreign currency invoices.
- **Reverse charge, designated zones, tax groups,** and the **schemes**: profit margin, partial exemption, capital assets, bad debt relief, tourist refund and excise tax.
- **E-invoicing (PINT AE):** builds the invoice as UBL 2.1 XML, checks it, and sends it through an Accredited Service Provider. Supported providers are Microvista and ClearTax, and there is a Mock provider for tests. Includes the status and retry log, and the reconciliation of purchases with received e-invoices.
- **Master data checks** that stop an invoice the network would reject: company, customer and address details, exemption reasons, UN/ECE unit codes. A report lists existing records that break the rules.

## Requirements

- Frappe and ERPNext, version 15 or later.
- Python 3.10 or later.
- For e-invoicing: an account with Microvista or ClearTax, and the company's TIN, TRN and legal registration.

## Install

```bash
bench get-app https://github.com/wahni-green/uae_compliance
bench --site <site> install-app uae_compliance
bench --site <site> migrate
```

Run `bench migrate` again after each update. It creates the custom fields and fills the starting data (designated zones, excise rates, exemption reasons, unit codes).

## First steps

1. Open **UAE Compliance Settings** and add a row for your company with its VAT accounts and filing frequency.
2. Fill in the **UAE Compliance** tab of the Company: TRN, TIN, legal registration and address with its emirate.
3. Give each Item Tax Template a **VAT Category**.
4. To send e-invoices, add the company to **UAE E-Invoice Settings**.

The [user guide](docs/UAE_COMPLIANCE_USER_GUIDE.md) describes each step in full.

## Documentation

| Guide | For |
|---|---|
| [User guide](docs/UAE_COMPLIANCE_USER_GUIDE.md) | Accountants and finance users: daily work, the VAT return, e-invoicing, and what to do when something looks wrong. |
| [Configuration](docs/UAE_COMPLIANCE_CONFIGURATION.md) | Administrators: every setting, the master data, and the e-invoice providers. |
| [Architecture](docs/UAE_COMPLIANCE_ARCHITECTURE.md) | Developers: how the app is built, the sending pipeline, and the providers. |
| [Verification](docs/UAE_VERIFICATION.md) | The legal sources the rules were checked against. Where it differs from the plan, this wins. |
| [Plan](docs/UAE_COMPLIANCE_PLAN.md) | The original scope and design decisions. |
| [To-do lists](docs/todo/README.md) | The phase checklists and the work that remains. |

## Development

```bash
bench --site <site> set-config allow_tests true
bench --site <site> run-tests --app uae_compliance
```

The tests need a site with Frappe, ERPNext and this app installed. Some e-invoice tests run the
official PINT AE Schematron and are skipped unless it is set up (see the architecture guide).

The app uses `pre-commit` (ruff, eslint, prettier). Run `pre-commit install` in the app directory.
Pull requests are reviewed by the OCR workflow in `.github/workflows/ocr-review.yml`.

## License

AGPL-3.0
