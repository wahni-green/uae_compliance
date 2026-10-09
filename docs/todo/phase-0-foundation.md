# Phase 0 – Foundation

- [ ] Add dependencies to `pyproject.toml` (`pyqrcode`, `pypng`, `lxml`); keep ruff config
- [ ] `hooks.py`: `required_apps = ["frappe/erpnext"]`, `before_install`/`before_migrate` version check, `after_install`, `before_uninstall`, `before_tests`
- [ ] `patches/check_version_compatibility.py` (Frappe >= 15)
- [ ] `install.py`, `uninstall.py`, `exceptions.py`
- [ ] Module dir `uae_compliance/uae_compliance/` with `constants/`, `setup/`, `utils/`, `overrides/`
- [ ] `utils/company.py::is_uae_company()` (Company.country == "United Arab Emirates")
- [ ] Constants: emirates, tax categories (S/Z/E/G/O/AE), GCC countries, designated zones
- [ ] `tests/__init__.py` with `before_tests` and UAE test company (AED) helpers
- [ ] CI (`.github/workflows/ci.yml`, `linter.yml`) modelled on oman_compliance
- [ ] Docs: ARCHITECTURE and CONFIGURATION markdown files; update README
- [ ] Verify primary sources (FTA/MoF): thresholds, TRN rules, RCM domestic cases (see plan "Open items")

## From verification (see ../UAE_VERIFICATION.md)
- [ ] Close remaining items in UAE_VERIFICATION.md section 7 (live VAT 201 form, FAF Appendix 5, zones list)
