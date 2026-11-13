# ERP Team Action List (BG e-invoicing tests)

Source: `BG_E-Invoicing_ERP_Team_Action_List.xlsx`. Decisions below were agreed point by point. Tick each item when it is done and committed.

Branch: `feat/erp-team-action-list`. Pull request goes to `develop`.

## Make mandatory

- [x] **1. Company registration type** (High). Block at Company save and at Sales Invoice submit, for companies enabled in UAE E-Invoice Settings.
- [x] **2. Company licence authority** (High). Checked: the field is already required for Trade License (commit 598a277). Now also blocked at Company save and at invoice submit, together with point 1.
- [x] **3. Exemption reason code on Exempt lines** (High). Submit is blocked when an Exempt line has no code.
- [x] **4. Customer licence authority** (Medium). Required when the type is Trade License, for all customers. The form already enforced it; the server check is new.
- [x] **5. Customer passport country** (Medium). Required when the ID type is Passport, on the form and on the server.
- [x] **6. Customer registration type** (Medium). Required when a registration ID is entered, on the form and on the server. Existing customers with no type are listed in the UAE Master Data Issues report.
- [x] **7. Address emirate** (Medium). Required when the country is United Arab Emirates, on the form and on the server. Existing addresses with no emirate are listed in the UAE Master Data Issues report.
- [x] **8. Sales Invoice customer address** (Medium). Submit is blocked for a UAE invoice with no customer address. ERPNext fills the primary address during validation, so the block applies when the customer has no usable address at all. That fallback is ERPNext's own and is not removed.

## Create field

- [x] **9. VAT category for Exempt and Out-of-scope** (High). No new field. The category comes from the Item Tax Template. Checked: a wrong template was not caught when a zero template was overridden by the item; point 17 now blocks that.
- [x] **10. Exemption reason code master** (High). New DocType UAE Exemption Reason, seeded with the four FTA codes and maintained by finance. It is a Link on the Item Tax Template, the Item and the line items. The line takes the template value, else the item's, and is read again on every save. The row field is read-only.
- [x] **11. UOM UN/ECE code** (High). Added `UOM.uae_uncefact_code`. A patch fills blanks from the old dictionary, with Pkt as XPA. Submit is blocked when a UOM on the invoice has no code, with no H87 fallback. Ctn, Bag, Tin, Bottle and Pcs are not in the old dictionary, so finance must enter their codes.
- [x] **12. Customer buyer category** (Medium). Added `uae_buyer_category` (B2B, B2G, B2C). B2C is out of scope. Existing customers stay blank.
- [x] **13. Intra-group exclusion** (Medium). Added `exclude_intra_vat_group` and `intra_group_grace_end` to UAE E-Invoice Settings. A UAE Tax Group lists companies, so a sale is intra-group when the customer is an internal customer (Represents Company) of a company in the same group as the invoicing company. Set the end date to 31-Dec-2028 for 24 months from 1-Jan-2027.
- [x] **14. E-invoice applicability on the invoice** (Medium). Added `uae_einvoice_applicable` and `uae_einvoice_exclusion_reason`, read-only and set at submit for companies that send e-invoices.
- [x] **15. Buyer endpoint** (Medium). No new field. `uae_tin` feeds IBT-049. The work is loading TIN data, which is not a code change.
- [ ] **16. PDF sent flag and setting** (Low). Deferred, not part of this pull request.

## Fix

- [x] **17. Item Tax Template overriding Zero and Exempt templates** (High). The old check missed it because the line took its category from the item's own 5% template. New check: a Sales Taxes and Charges Template that charges 0% VAT cannot be overridden by an item's Item Tax Template; the invoice cannot be saved.
- [x] **18. Customer disabling script** (High). Not in this app. Ignored.
- [x] **19. Header discount and extra charge rows** (Medium). Changed after testing. A header discount already exports correctly: ERPNext spreads it into the net amount of each row, for both "Net Total" and "Grand Total", and the e-invoice uses those amounts. So no document-level allowance was built. A charge row in the taxes table (freight) cannot get a VAT category, so submit is now blocked with a message to enter it as an item row.
- [x] **20. Cancellation after the e-invoice was attempted** (Medium). Added `block_cancellation_after_attempt` to UAE E-Invoice Settings (off by default). It blocks cancelling any invoice whose sending was attempted. The workflow button "Request for cancelation" is on the site, not in this app: finance adds the condition `not doc.uae_einvoice_status` to its transition (written in the user guide).
- [x] **21. Rounding method** (Medium). A warning when System Settings do not use Commercial Rounding, on saving UAE E-Invoice Settings with a company enabled and on submitting an e-invoice. The setting itself is not changed.
- [x] **22. Address country data** (Low). The UAE Master Data Issues report lists addresses whose country is another spelling of the UAE, such as "UAE". Nothing is changed.

## Other

- [x] **OCR review workflow.** `.github/workflows/ocr-review.yml`, copied from wahni-green/wahni_it. A review runs only when someone with write access opens the PR, marks it ready, adds the `ocr-review` label or comments `/ocr`.

## Notes

- Points 6, 7 and 22 are reports. They are grouped into one data-quality report.
- Point 8 does not remove ERPNext's fallback to the customer's primary address: ERPNext fills it during validation. Submit is blocked only when the customer has no usable address at all.
