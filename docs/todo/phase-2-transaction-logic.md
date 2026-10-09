# Phase 2 – Transaction logic

- [ ] `overrides/transaction.py::set_vat_category_defaults` (template -> designated-zone address -> default standard)
- [ ] Sales Invoice: zero/exempt/out-of-scope rows must carry no VAT; mixed-category same-item check; export detection; simplified invoice flag; emirate required for standard-rated; AED VAT amounts for foreign currency
- [ ] Purchase Invoice: RCM requires Output + Input rows; GCC/import/zone-supplier flags; postponed import VAT; blocked/non-recoverable input tax
- [ ] `overrides/item_tax_template.py` validation
- [ ] Tax credit note: 14-day warning (Art. 61/70)
- [ ] Tax group handling
- [ ] Verify ERPNext regional hooks (`update_itemised_tax_data`, RCM grand-total) don't double-handle RCM
- [ ] `utils/tax_account.py` (item_wise_tax_detail parsing per company VAT accounts)
- [ ] Tests (sales, purchase, item tax template, non-UAE company unaffected)

## From verification (see ../UAE_VERIFICATION.md)
- [ ] Warn when tax invoice not issued within 14 days of supply (not credit notes)
- [ ] Simplified invoice: allowed <= AED 10,000 or unregistered recipient; blocked under reverse charge and for e-invoicing registrants
- [ ] Reverse-charge case flag: imports, hydrocarbons, electronic devices, precious metals, metal scrap (scrap requires recipient declaration and RCM statement)
- [ ] Designated zone goods: default inside UAE per ER Art 51(5); outside only with evidence
