# UAE Compliance

UAE VAT compliance for ERPNext (Frappe v15): VAT categories, emirate-wise VAT 201 return, tax invoices
and credit notes, reverse charge, designated zones, advanced schemes and Peppol PINT AE e-invoicing
through pluggable Accredited Service Providers. Structured like `oman_compliance`.

Status: under development. See [docs/UAE_COMPLIANCE_PLAN.md](docs/UAE_COMPLIANCE_PLAN.md),
[docs/UAE_VERIFICATION.md](docs/UAE_VERIFICATION.md) and the phase checklists in [docs/todo/](docs/todo/).

## Install

```bash
bench get-app <repo-url>
bench --site <site> install-app uae_compliance
```

## Contributing

This app uses `pre-commit` (ruff, eslint, prettier). Run `pre-commit install` in the app directory.

## License

AGPL-3.0
