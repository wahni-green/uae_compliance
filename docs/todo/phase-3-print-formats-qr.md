# Phase 3 – Print formats & QR

- [ ] Shared macros `print_format/_shared/`
- [ ] UAE Tax Invoice (EN/AR) with TRNs, supply date, per-line VAT, AED disclosure
- [ ] UAE Simplified Tax Invoice (< AED 10,000)
- [ ] UAE Tax Credit/Debit Note
- [ ] Jinja methods in `hooks.py`: exchange-rate/AED disclosure, QR, output VAT, item-wise VAT rates
- [ ] Interim QR payload (`utils/qr_code.py`)
- [ ] Missing-address / missing-TRN warnings
- [ ] Render tests / visual check

## From verification (see ../UAE_VERIFICATION.md)
- [ ] Tax invoice shows AED amounts and exchange rate; reverse-charge statement with Decree-Law reference
- [ ] Tax Credit Note content per ER Art 60(1) (original, corrected, difference, reason, reference)
- [ ] No QR on e-invoice (PINT AE) print path; QR only for non-e-invoice formats
