# Phase 2 – Transaction logic

- [x] `overrides/transaction.py::set_vat_category_defaults` (template -> designated-zone address -> default standard)
- [x] Sales Invoice: zero/exempt/out-of-scope rows must carry no VAT; mixed-category same-item check; export detection; simplified invoice flag; emirate required for standard-rated; AED VAT amounts for foreign currency
- [x] Purchase Invoice: RCM requires Output + Input rows; GCC/import/zone-supplier flags; postponed import VAT; blocked/non-recoverable input tax
- [x] `overrides/item_tax_template.py` validation
- [x] Tax credit note: 14-day warning (Art. 61/70)
- [ ] Tax group handling (moved to Phase 5 with the other schemes)
- [x] Verify ERPNext regional hooks (`update_itemised_tax_data`, RCM grand-total) don't double-handle RCM
- [x] `utils/tax_account.py` (item_wise_tax_detail parsing per company VAT accounts)
- [x] Tests (sales, purchase, item tax template, non-UAE company unaffected)

## From verification (see ../UAE_VERIFICATION.md)
- [x] Warn when tax invoice not issued within 14 days of supply (not credit notes)
- [x] Simplified invoice: allowed <= AED 10,000 or unregistered recipient; blocked under reverse charge and for e-invoicing registrants
- [x] Reverse-charge case flag (`uae_reverse_charge_type`): imports, hydrocarbons, electronic devices, precious metals, metal scrap (scrap requires recipient declaration and RCM statement)
- [x] Designated zone goods: default inside UAE per ER Art 51(5); outside only with evidence. A zone address only raises a warning and never auto zero-rates a row

Notes: blocked/non-recoverable input tax is a per-row flag (`uae_input_tax_not_recoverable` on Purchase Invoice Item) for the Phase 4 return; apportionment is Phase 5. `Issues E-Invoices` is a per-company flag in UAE Compliance Settings. The simplified-invoice flag is conservative: unregistered recipient, total (incl. VAT) at or below the threshold, base currency AED, and not an e-invoicing company. Sales Invoice has a new `uae_supply_date` for the 14-day tax invoice warning. ERPNext's regional RCM hooks key off its own hidden `reverse_charge` field (kept at "N"), so they do not double-handle reverse charge.
Reverse charge rows: add the VAT to the Input VAT account and deduct it from the Output VAT account; the two rows must cancel out so the supplier total is unchanged. A purchase typed "Import of Services" is never flagged as an import of goods. Purchase rows marked zero rated, exempt or out of scope are checked against VAT on the Input account.
