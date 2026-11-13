# ERP Team Action List (BG e-invoicing tests)

Source: `BG_E-Invoicing_ERP_Team_Action_List.xlsx`. Decisions below were agreed point by point. Tick each item when it is done and committed.

Branch: `feat/erp-team-action-list`. Pull request goes to `develop`.

## Make mandatory

- [x] **1. Company registration type** (High). Block at Company save and at Sales Invoice submit, for companies enabled in UAE E-Invoice Settings.
- [x] **2. Company licence authority** (High). Checked: the field is already required for Trade License (commit 598a277). Now also blocked at Company save and at invoice submit, together with point 1.
- [x] **3. Exemption reason code on Exempt lines** (High). Submit is blocked when an Exempt line has no code.
- [x] **4. Customer licence authority** (Medium). Required when the type is Trade License, for all customers. The form already enforced it; the server check is new.
- [x] **5. Customer passport country** (Medium). Required when the ID type is Passport, on the form and on the server.
- [x] **6. Customer registration type** (Medium). Required when a registration ID is entered, on the form and on the server. The report of existing customers with no type is still to do (see the data-quality report note).
- [x] **7. Address emirate** (Medium). Required when the country is United Arab Emirates, on the form and on the server. The report of existing addresses with no emirate is still to do (data-quality report).
- [x] **8. Sales Invoice customer address** (Medium). Submit is blocked for a UAE invoice with no customer address. ERPNext fills the primary address during validation, so the block applies when the customer has no usable address at all. That fallback is ERPNext's own and is not removed.

## Create field

- [ ] **9. VAT category for Exempt and Out-of-scope** (High). No new field. The category comes from the Item Tax Template, so this is a finance setup issue. Check the existing consistency check catches a wrong template.
- [x] **10. Exemption reason code master** (High). New DocType UAE Exemption Reason, seeded with the four FTA codes and maintained by finance. It is a Link on the Item Tax Template, the Item and the line items. The line takes the template value, else the item's.
- [x] **11. UOM UN/ECE code** (High). Added `UOM.uae_uncefact_code`. A patch fills blanks from the old dictionary, with Pkt as XPA. Submit is blocked when a UOM on the invoice has no code, with no H87 fallback. Ctn, Bag, Tin, Bottle and Pcs are not in the old dictionary, so finance must enter their codes.
- [x] **12. Customer buyer category** (Medium). Added `uae_buyer_category` (B2B, B2G, B2C). B2C is out of scope. Existing customers stay blank.
- [x] **13. Intra-group exclusion** (Medium). Added `exclude_intra_vat_group` and `intra_group_grace_end` to UAE E-Invoice Settings. A UAE Tax Group lists companies, so a sale is intra-group when the customer is an internal customer (Represents Company) of a company in the same group as the invoicing company. Set the end date to 31-Dec-2028 for 24 months from 1-Jan-2027.
- [x] **14. E-invoice applicability on the invoice** (Medium). Added `uae_einvoice_applicable` and `uae_einvoice_exclusion_reason`, read-only and set at submit for companies that send e-invoices.
- [x] **15. Buyer endpoint** (Medium). No new field. `uae_tin` feeds IBT-049. The work is loading TIN data, which is not a code change.
- [ ] **16. PDF sent flag and setting** (Low). Deferred.

## Fix

- [ ] **17. Item Tax Template overriding Zero and Exempt templates** (High). Block submit when a Zero, Exempt or Out-of-scope line carries VAT.
- [x] **18. Customer disabling script** (High). Not in this app. Ignored.
- [ ] **19. Header discount and extra charge rows** (Medium). Send them as a document-level allowance and charge.
- [ ] **20. Cancellation after the e-invoice was attempted** (Medium). Add a setting that blocks cancellation for any status except not sent.
- [ ] **21. Rounding method** (Medium). Warn when the site uses Banker's rounding. No change to the setting.
- [ ] **22. Address country data** (Low). Report addresses whose country is not United Arab Emirates, such as "UAE". No change.

## Other

- [x] **OCR review workflow.** `.github/workflows/ocr-review.yml`, copied from wahni-green/wahni_it. A review runs only when someone with write access opens the PR, marks it ready, adds the `ocr-review` label or comments `/ocr`.

## Notes

- Points 6, 7 and 22 are reports. They are grouped into one data-quality report.
- Point 8 removes the primary address fallback, so flows that rely on it will fail at submit.
