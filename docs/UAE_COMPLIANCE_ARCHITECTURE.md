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
