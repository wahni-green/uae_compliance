# Phase 0 – Foundation

- [x] Add dependencies to `pyproject.toml` (`pyqrcode`, `pypng`, `lxml`); keep ruff config
- [x] `hooks.py`: `required_apps = ["frappe/erpnext"]`, `before_install`/`before_migrate` version check, `after_install`, `before_uninstall`, `before_tests`
- [x] `patches/check_version_compatibility.py` (Frappe >= 15)
- [x] `install.py`, `uninstall.py`, `exceptions.py`
- [x] Module dir `uae_compliance/uae_compliance/` with `constants/`, `setup/`, `utils/`, `overrides/`
- [x] `utils/company.py::is_uae_company()` (Company.country == "United Arab Emirates")
- [x] Constants: emirates, tax categories (S/Z/E/O/AE/N), GCC countries (designated zones seed list in Phase 1)
- [x] `tests/__init__.py` with `before_tests` and UAE test company (AED) helpers
- [x] Linter workflow (`.github/workflows/linter.yml`) modelled on oman_compliance; the server test workflow (`ci.yml`) was removed, run tests locally
- [x] Docs: ARCHITECTURE and CONFIGURATION markdown files; update README
- [x] Verify primary sources (FTA/MoF): done, see UAE_VERIFICATION.md

## From verification (see ../UAE_VERIFICATION.md)
- [ ] Close remaining items in UAE_VERIFICATION.md section 7 (current FAF spec, optional live VAT 201 check)
