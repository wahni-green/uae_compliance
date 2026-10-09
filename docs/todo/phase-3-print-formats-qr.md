# Phase 3 – Print formats & QR

- [x] Shared macros `print_format/_shared/`
- [x] UAE Tax Invoice (EN/AR) with TRNs, supply date, per-line VAT, AED disclosure
- [x] UAE Simplified Tax Invoice (< AED 10,000)
- [x] UAE Tax Credit/Debit Note
- [x] Jinja methods in `hooks.py`: exchange-rate/AED disclosure, QR, output VAT, item-wise VAT rates
- [x] Interim QR payload (`utils/qr_code.py`)
- [x] Missing-address / missing-TRN warnings
- [x] Render tests / visual check

## From verification (see ../UAE_VERIFICATION.md)
- [x] Tax invoice shows AED amounts and exchange rate; reverse-charge statement with Decree-Law reference
- [x] Tax Credit Note content per ER Art 60(1) (original, corrected, difference, reason, reference)
- [x] No QR on e-invoice (PINT AE) print path; QR only for non-e-invoice formats

Notes: formats are `UAE Tax Invoice` (auto-switches to the simplified layout for flagged invoices and to the credit note layout for returns), `UAE Simplified Tax Invoice` and `UAE Tax Credit Note`. A tax debit note format is not built: ER Art 60 covers credit notes only. Amounts print as plain numbers with the currency in the headings (the Arabic AED symbol detaches minus signs in the PDF engine), and layouts avoid flexbox because wkhtmltopdf predates it. Returns require a `Reason for Credit Note` on submit. The QR code is off by default (UAE Compliance Settings > Show QR Code on Tax Invoices), never printed for e-invoicing companies, and its labelled-text payload is not a government format, since the FTA publishes no QR specification.
