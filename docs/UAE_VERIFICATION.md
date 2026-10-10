# Primary-Source Verification (as of 2026-10-09)

Result of checking the assumptions in [UAE_COMPLIANCE_PLAN.md](UAE_COMPLIANCE_PLAN.md) against FTA, MoF and Peppol documents. Research was done by three research passes that read the documents; items marked **Unverified** or **Secondary** still need a human check (ideally an FTA tax-software contact or the live EmaraTax form) before they are hard-coded.

## 1. Corrections to the plan's assumptions
| # | Assumption in plan | Verified | Impact |
|---|---|---|---|
| 1 | Capital asset scheme: 10-year adjustment | **5 years for non-buildings, 10 years only for buildings**; threshold AED 5M confirmed (ER Arts 57-58; CD 149/2026 rewords as "business asset") | Phase 5 |
| 2 | Credit note must be issued within 14 days | **No 14-day credit-note limit found.** The 14 days applies to **tax invoices** (Decree-Law Art 67; ER Art 59(13)). Credit-note triggers: Decree-Law Arts 61, 62(2), 70(1) | Phase 2: warn on late tax invoices, not credit notes |
| 3 | Simplified invoice < AED 10,000 | Allowed if recipient unregistered, or registered and consideration **does not exceed** AED 10,000; not allowed under reverse charge (ER Art 59(2),(5)); **not allowed at all for e-invoicing registrants** (CD 100/2025, ER Art 59(16)) | Phase 2/3/6 |
| 4 | TRN: 15 digits, check-digit possible | No primary source gives a format. Use `^100\d{12}$` (secondary) **and do not claim a checksum**. Peppol e-invoicing Schematron: VAT TRN is 15 digits starting `1` and ending `03`; TIN is 10 digits `1XXXXXXXXX` | Phase 1 validation; make the regex configurable |
| 5 | Tax category code `G` (export) | **Does not exist in PINT AE.** Codes: S, E, O, AE, Z, N (N = "Standard rate additional VAT", used for margin scheme). Free zone / deemed supply / margin / exports are an 8-character 0/1 flag string in `ProfileExecutionID` | Phase 6 mapping |
| 6 | Invoice types 380/381 | Invoice 380 (commercial/tax) and 480 (out of scope of VAT); credit note 381 and 81 (goods/services related) | Phase 6 |
| 7 | E-invoice QR code | **No QR code on PINT AE invoices** (Guidelines s5.3). Keep QR only for non-e-invoice print formats | Phase 3/6 |
| 8 | ASP appointment deadline for revenue >= AED 50M | **30 Oct 2026** (amended MD 244; Feb 2026 Guidelines still say 31 Jul 2026). Revenue < AED 50M and government: ASP by 31 Mar 2027 | Docs |
| 9 | E-invoice penalty AED 5,000 per invoice | AED 5,000 per month for late implementation/ASP appointment; **AED 100 per invoice, capped AED 5,000/month**; AED 1,000/day for failing to report system failure (CD 106/2025; EY secondary) | Docs |
| 10 | Excise 50% on sweetened drinks | Repealed from 1 Jan 2026 (CD 197/2025). Now volumetric: AED 1.09/L (>= 8 g sugar/100 ml), AED 0.79/L (5 to < 8 g), 0 below. Tobacco, e-cigarette liquids/devices, energy drinks 100% | Phase 5 excise |
| 11 | AED 150M turnover => monthly filing | Primary guide says FTA assigns period (default 3 months); the AED 150M rule is **secondary only** | Phase 4: make period type a setting |
| 12 | VAT 201 "GCC section" | **Not found** in primary guides | Phase 4: omit until confirmed on live EmaraTax form |
| 13 | Tourist refund via "Planet" | Operator not named in legal text; scheme per FTA Decision 2/2018 (amended). 90-day export window; min AED 250/supplier; refund cap AED 35,000 per tourist per 24 h | Phase 5 |
| 14 | Tax invoice only requires TRN, etc. | Also: AED amounts and exchange rate (Central Bank rate on date of supply), reverse-charge statement with Decree-Law reference (ER Art 59(1)) | Phase 3 |

New developments to incorporate: **Cabinet Decision 149/2026 (effective 1 Oct 2026)** adds ER Art 4(6) (interconnected components are a single composite supply, relevant to software licence/support/hosting bundles) and changes margin scheme (purchase price includes costs only where related input tax is non-recoverable), input tax and apportionment rules (government/charity method applies from the first tax year starting after 1 Oct 2027).

## 2. VAT 201 (FTA VAT User Guide - Returns v40, Aug 2021; EmaraTax manual)
Confirmed: boxes 1-15 numbering/labels and columns.
- Box 1 standard-rated supplies **per Emirate** (Amount, VAT, Adjustment; adjustment = bad-debt relief / commercial-property sale only). The a-g lettering and Emirate order are **not in the text**: confirm on the live form.
- Box 2 tourist refunds (pre-populated, negative). Box 3 reverse-charge supplies (Amount, VAT). Box 4 zero-rated (Amount). Box 5 exempt (Amount). Box 6 goods imported (auto from customs; includes duty and excise). Box 7 import adjustments. Box 8 totals.
- Box 9 standard-rated expenses (Amount, Recoverable VAT, Adjustment: bad-debt repayment, annual apportionment, capital assets). Box 10 reverse-charge input (recovers VAT in boxes 3, 6, 7). Box 11 totals.
- Box 12 total due, 13 total recoverable, 14 payable/recoverable, 15 **Yes/No** refund request (Yes leads to Form VAT311; No carries credit forward).
- Profit margin scheme: only a Yes/No flag; full sales value in box 1 and full purchase price in box 9.
- Rounded to 2 decimals, `0` where nothing applies; errors < AED 10,000 corrected in current return, larger need Voluntary Disclosure; nil return required.
- Periods: default 3 months; staggers S1 (Feb-Apr...), S2 (Mar-May...), S3 (Apr-Jun...), S4 monthly. Due by the **28th day after period end** (next business day if weekend/holiday).
- Penalties: late filing AED 1,000, then AED 2,000 within 24 months (primary). Late payment: old 2%/4%/300% regime (2021 guide); **new 14% p.a. non-compounding from 14 Apr 2026 is secondary only** (Cabinet Decision 129/2025).
- **FAF**: format is in "Appendix 5 for VAT" of the FTA *Requirements Document for Tax Accounting Software* (not obtained). Minimum 21 data elements known (company name, user ID, TRN, FAF version, GL ID, supplier/customer locations, reverse charges, tax codes, invoice numbers/dates, permit numbers, transaction IDs, debit/credit amounts, VAT in currency and AED, AR/AP, product references, descriptions). CSV layout is secondary only. Request the document via the FTA vendor page or info_tas@tax.gov.ae.


## 2b. FTA *Requirements Document for Tax Accounting Software* (Oct 2017, 60 pages)
Source: https://www.oracle.com/webfolder/s/delivery_production/docs/FY16h1/doc21/Req-Doc-TaxAcc-Software-English.pdf (FTA Target Operating Model document, **hosted by Oracle**; FTA-hosted copy not located). It is the Oct 2017 pre-launch version: **FAF and tax-code details are authoritative for structure, but the VAT return layout in it is outdated** (see below).
- **FAF format (Appendix 5):** `.csv`, comma delimiter (no commas inside fields), dates DD-MM-YYYY, Decimal[14,2], FAFVersion `FAFv1.0.0`, four tables:
  1. Company information (one row): TaxablePersonNameEn/Ar, TRN, TaxAgencyName, TAN, TaxAgentName, TAAN, PeriodStart, PeriodEnd, FAFCreationDate, ProductVersion, FAFVersion.
  2. Supplier/purchase listing (one row per invoice line, sorted by InvoiceDate): SupplierName, SupplierCountry, SupplierTRN, InvoiceDate, InvoiceNo, PermitNo, TransactionID, LineNo, ProductDescription, PurchaseValueAED, VATValueAED, TaxCode, FCYCode, PurchaseFCY, VATFCY; plus a totals row (PurchaseTotalAED, VATTotalAED, TransactionCountTotal).
  3. Customer/supply listing: CustomerName, CustomerCountry, CustomerTRN, InvoiceDate, InvoiceNo, TransactionID, LineNo, ProductDescription, SupplyValueAED, VATValueAED, TaxCode, Country (export destination), FCYCode, SupplyFCY, VATFCY; plus totals row.
  4. General ledger: TransactionDate, AccountID, AccountName, TransactionDescription, Name, TransactionID, SourceDocumentID, SourceType, Debit, Credit, Balance; plus totals row (TotalDebit, TotalCredit, TransactionCountTotal, GLTCurrency).
- **FAF tax codes (Appendix 3):** sales `SR` (standard), `ZR` (zero), `EX` (exempt), `IG` (intra-GCC supplies), `RC` (reverse charge), `OA` (amendments to output tax); purchases `SR`, `RC`, `IA` (amendments to input tax). Verify these still apply: the document is from 2017, **before** the later FAF updates, and Appendix 5 itself points to "Appendix 2" for tax codes although they are listed in Appendix 3.
- **Software requirements:** FAF must be generated by a user with no assistance, for a selectable period; must not be modifiable or an image.
- **VAT return layout in this document is the pre-launch form, differing from the 2021 guide:** it lettered Box 1 as **1a Abu Dhabi, 1b Dubai, 1c Sharjah, 1d Ajman, 1e Umm Al Quwain, 1f Ras Al Khaimah, 1g Fujairah** (this settles the lettering and emirate order), but had extra boxes (5 supplies to customers registered in other GCC states; 6 exempt; 7 imports; 8 import adjustments; 9 totals; 10-12 expenses; 13-16 net VAT/refund) and **GCC sections** (transfer of own goods to Bahrain/Kuwait/Oman/Qatar/Saudi Arabia; recoverable VAT paid in other GCC states). The **2021 guide's 15-box numbering is later and wins**; the GCC sections and Box 5 were removed in the final form (not seen in the 2021 guide). Emirate lettering 1a-1g is retained from this document as the best available evidence; confirm on the live form.
- **Corroboration (secondary):** ClearTax's VAT 201 page (https://www.cleartax.com/ae/vat-return-uae) lists boxes 1-14 matching the 2021 guide (box 1 standard rated sales, 2 tourist refunds, 3 reverse charge sales, 4 zero-rated, 5 exempt, 6 imports, 7 import adjustments, 8 totals, 9 standard-rated expenses, 10 reverse charge purchases, 11 totals, 12-13 output/input tax, 14 payable/refundable). It says only "fill Box 1 ... corresponding emirate": **no 1a-1g lettering, no emirate order, no version/date, and no GCC section or GCC Box 5** mentioned. Vendor blog, so supporting evidence only. Net effect: GCC sections are absent from every current source found; Box 1 lettering still rests on the 2017 FTA document.
- Appendix 7 (producing data required for VAT return preparation) describes mapping tax codes to return boxes; worth reading in detail in Phase 4.

## 3. VAT law rules
- **Thresholds:** mandatory AED 375,000 (ER Art 7); voluntary AED 187,500 (ER Art 8).
- **Tax invoice (ER Art 59(1)):** "Tax Invoice"; supplier name/address/TRN; recipient name/address/TRN if registered; unique number; issue date; supply date if different; description; per line unit price, quantity, rate, amount in AED; discount; gross amount in AED; tax amount in AED plus exchange rate; reverse-charge statement with Decree-Law reference. Issue within 14 days of supply (Art 67). Simplified invoice content: ER 59(2). Credit note content: "Tax Credit Note", original value, corrected value, difference and tax on difference in AED, reason, reference to original supply (ER Art 60(1)).
- **Reverse charge cases:** imports of goods/services by registrants (Decree-Law Art 48(1), ER Art 48); hydrocarbons registrant-to-registrant for resale (Art 48(3)-(6)); electronic devices (CD 91/2023; **medium confidence**); precious metals/stones/jewellery (CD 127/2024, effective 26 Feb 2025); metal scrap (CD 153/2025, effective 14 Jan 2026, requires recipient declaration and an explicit RCM statement on the invoice). Designated zones: **no general RCM**; goods consumed/short in a zone are treated as imported (ER Art 51(9)).
- **Designated zones (ER Art 51):** goods supplied within a zone default to **inside the UAE** and are outside only if used in production in the zone, delivered outside the State with evidence, or moved onshore with import VAT paid; zone-to-zone transfers not taxed under customs suspension; services in a zone are inside the UAE; a business established in a zone is UAE-resident. Current zone list only from secondary sources (medium-low); Dubai Textile City and Al Quoz removed in 2021. **The seed list must be admin-editable and re-verified against the FTA legislation page.**
- **Schemes:** partial exemption (ER Art 55; ratio rounded to nearest whole %, annual true-up in first period of next year, further adjustment if difference > AED 250,000); change of use within 5 years (Art 56); bad-debt relief (Decree-Law Art 64: written off, > 6 months, recipient notified); margin scheme (ER Art 29: second-hand goods, antiques > 50 years, collectors' items; no tax shown on invoice; stock book); tourist refund (ER Art 68); tax groups (Decree-Law Art 14, ER Arts 9-12).
- **Cabinet Decision 100/2024:** multiple-component rule needs both separate pricing and a single supplier (ER Art 4(4)); export zero-rating evidence (Arts 30-31; Arabic/English or certified translation); Art 3bis; deregistration (Arts 14, 14bis); tourist 90 days.

## 4. E-invoicing (MoF Guidelines V1.0 23 Feb 2026, Mandatory Fields V1.0, Programme deck 30 Jun 2026, docs.peppol.eu PINT-AE v1.0.4)
- **Legal basis:** FDL 16/2024 (VAT Art 65(5)); MD 243/2025 (system), MD 244/2025 (timeline, amended), MD 64/2025 (ASP accreditation, white-label allowed), CD 106/2025 (penalties), CD 74/2023 (retention).
- **Timeline:** pilot from 1 Jul 2026 (voluntary, penalties only from mandatory date); go-live 1 Jan 2027 (>= AED 50M), 1 Jul 2027 (others), 1 Oct 2027 (government); VAT-group intra-group grace 24 months from 1 Jan 2027.
- **Scope:** B2B, B2G, G2B, G2G, VAT-registered or not. **Not in scope:** B2C, supplies to/from non-business individuals, sovereign government activity, airline e-tickets, exempt financial services, imports under reverse charge. One ASP handles both sending and receiving.
- **Model:** 5 corners (supplier, supplier's ASP, buyer's ASP, buyer, FTA/MoF platform).
- **Technical:** UBL 2.1 Invoice/CreditNote; CustomizationID starts `urn:peppol:pint:billing-1@ae-1` (self-billing `urn:peppol:pint:selfbilling-1@ae-1`); ProfileID `urn:peppol:bis:billing`; 51 mandatory fields (tax invoice), 49 (commercial); `cbc:UUID` and `cbc:IssueTime` on tax invoices.
- **ProfileExecutionID flag positions:** 1 free trade zone, 2 deemed supply, 3 profit margin, 4 summary invoice, 5 continuous supply, 6 agent billing, 7 e-commerce, 8 exports.
- **Exemption reason codes:** DL8.46.1 financial services, DL8.46.2 residential units, DL8.46.3 bare land, DL8.46.4 local passenger transport.
- **Participant ID:** scheme `0235` + 10-digit TIN. Predefined endpoints: `0235:9900000098` (buyer not yet on system), `0235:9900000099` (exports, no Peppol ID), `0235:9900000097` (deemed supply). Seller/buyer legal registration ID with type (TL, EID, PAS, CD) required.
- **AED:** if document currency is not AED set `TaxCurrencyCode` = AED, include VAT total in AED and total incl. VAT in AED (`AdditionalDocumentReference` type `aedtotal-incl-vat`), Central Bank rate (rules ibr-140-ae, ibr-153-ae, ibr-175-ae).
- **Item type** G/S/B; services need Service Accounting Code.
- **Retention:** 5 years after tax period (7 for real estate; +4 years during dispute/audit); "store within the State" interpreted as retrievable by the FTA.
- **Resources:** https://docs.peppol.eu/poac/ae/pint-ae/resources.zip (code lists, Schematron, 24 sample XMLs); XSD is standard OASIS UBL 2.1. **Pin to v1.0.4.** Caveat: the "N" tax category in the code list is a Greek capital Nu (U+039D) while Schematron uses Latin N; check against the live Schematron.
- **Unverified:** MD 243/244/64 and CD 106 article texts (taken from MoF Guidelines/deck and EY).

## 5. Excise (Cabinet Decision 197/2025, effective 1 Jan 2026; repeals CD 52/2019)
Tobacco and tobacco products 100%; e-cigarette liquids and devices 100%; energy drinks 100%; sweetened drinks volumetric (see table above). Lab report required, otherwise highest tier applies (Art 13(4)).

## 6. Primary sources
- Consolidated VAT Executive Regulation (FTA, Sep 2026, incl. CD 100/2024, 100/2025, 149/2026): https://tax.gov.ae//Datafolder/Files/Legislation/2026/Law-No-8-of-2017-and-its-amendments--09-2026.pdf
- Consolidated ER (MoF, Oct 2025): https://mof.gov.ae/wp-content/uploads/2025/10/Cabinet-Decision-No.-52-of-2017-of-the-Executive-Regulation-of-the-Federal-Decree-Law-No.-8-of-2017-on-Value-Added-Tax-and-its-amendments.pdf
- Decree-Law consolidated: https://tax.gov.ae/DataFolder/Files/Legislation/Federal%20Decree-Law%20No.%208%20of%202017%20and%20amendments%20-%20For%20Publishing.pdf
- VATP040: https://tax.gov.ae/Datafolder/Files/Pdf/2025/VATP040%20-%20Amendments%20to%20VAT%20ER%20-%2014%2003%202025.pdf
- VAT Returns User Guide v40: https://tax.gov.ae/DataFolder/Files/Pdf/VAT%20Returns%20User%20GuideEnglishV40%2015%2008%202021%20SEP2021.pdf
- EmaraTax VAT 201 manual: https://tax.gov.ae/DownloadOpenTextFile?fileUrl=en%2FVAT_VAT_Guides%2FVAT_Returns_form%2FProcess_the_VAT_201_returns_form_EN.pdf
- Certification Guidelines for Tax Accounting Software (FAF): https://tax.gov.ae/DataFolder/Files/Pdf/certification-guidelines-for-tax-accounting-software.pdf
- Designated Zones VAT Guide: https://tax.gov.ae/DataFolder/Files/Pdf/Designated-Zones-VAT-Guide.pdf
- Designated zones list (2018): https://tax.gov.ae/-/media/Files/FTA/links/Legislation/VAT/ar/05-designated-zones.pdf
- CD 127/2024 precious metals RCM: https://tax.gov.ae/Datafolder/Files/Legislation/2025/Cabinet-Decision-No-127-of-2024-on-Reverse-Charge-Mechanism-for-Precious-Metals.pdf
- CD 153/2025 metal scrap RCM: https://mof.gov.ae/wp-content/uploads/2025/12/Cabinet-Decision-No.-153-of-2025-on-the-Application-of-the-Reverse-Charge-Mechanism-on-Metal-Scrap-en.pdf
- CD 197/2025 excise: https://tax.gov.ae/Datafolder/Files/Legislation/2025/Cabinet-Decision-No-197-of-2025.pdf
- Tourist refund Decision 2/2018 (consolidated 2026): https://tax.gov.ae//Datafolder/Files/Pdf/2026/legislation/Decision%20No.%202%20of%202018%20on%20Tax%20Refunds%20for%20Tourists%20Scheme%20and%20amendments%20-%20For%20publishing%20-%2008%2007%202026.pdf
- Electronic devices RCM clarification (FTA news): https://tax.gov.ae/en/media.centre/News/federal.tax.authority.issues.public.clarification.on.implementing.reverse.charge.mechanism.on.electronic.devices.among.registrants.in.the.uae.aspx
- Registration topic page: https://tax.gov.ae/en/taxes/vat/vat.topics/registration.for.vat.aspx
- E-invoicing Guidelines V1.0: https://mof.gov.ae/wp-content/uploads/2026/02/UAE-Electronic-Invoicing-Guidelines_V-1.0-23Feb2026.pdf
- E-invoicing Mandatory Fields V1.0: https://mof.gov.ae/wp-content/uploads/2026/02/UAE-Electronic-Invoice-mandatory-fields_V-1.0-23Feb2026.pdf
- E-invoicing Programme deck (30 Jun 2026): https://mof.gov.ae/wp-content/uploads/2026/06/UAE-eInvoicing-Programme-30June2026.pdf
- PINT-AE specification: https://docs.peppol.eu/poac/ae/pint-ae/ and bundle https://docs.peppol.eu/poac/ae/pint-ae/resources.zip
- ClearTax VAT 201 page (secondary, box-layout corroboration): https://www.cleartax.com/ae/vat-return-uae
- Secondary used for gaps: KPMG (FDL 16/2024) https://kpmg.com/ae/en/insights/tax-insights/updated-uae-vat-law-no-16-of-2024.html ; EY (CD 106/2025 penalties) https://globaltaxnews.ey.com/news/2025-2433-uae-ministry-of-finance-publishes-cabinet-decision-on-penalties-for-noncompliance-with-e-invoicing

## 7. Still to confirm before coding
- [x] Box 1 lettering: **decided by user to keep 1a-1g** (1a Abu Dhabi, 1b Dubai, 1c Sharjah, 1d Ajman, 1e Umm Al Quwain, 1f Ras Al Khaimah, 1g Fujairah). Evidence is the 2017 FTA doc only; make labels data-driven so they are easy to change.
- [ ] Live EmaraTax VAT 201 form (optional): GCC sections are absent from all current sources found (2021 guide, ClearTax), so treated as removed
- [ ] Obtain a current FAF spec (2017 doc may be superseded) and confirm FAF tax codes; ask info_tas@tax.gov.ae
- [ ] Current designated zones list (FTA legislation page)
- [ ] Late-payment penalty regime (CD 129/2025) and AED 150M monthly rule
- [ ] CD 91/2023 text (electronic devices RCM) and its current supplier rules
- [ ] **Open point:** where the supplier reports the *value* of a sale under a domestic reverse charge on the VAT 201. The Cabinet Decisions say only that the supplier does not report "such Tax", and the FTA's guide has no supplier-side box (section 8). The app leaves such sales out of every box; confirm with the FTA or a tax adviser, and change `get_invoice_rows` (`REVERSE_CHARGE_SUPPLY_CATEGORY`) if the value belongs in a box, such as Box 4
- [ ] Text of MD 243/244/64 and CD 106/2025
- [ ] Greek "N" vs Latin N tax category in PINT-AE Schematron

## 8. Reverse charge on the supplier's side (researched 2026-10-10)

Needed before sales invoices under a domestic reverse charge (PINT category AE) can be built.

**Settled by primary sources**
- **The supplier does not account for or report the tax.** Cabinet Decision 153/2025 (metal scrap) Art 2(1)(a): "The supplier shall not be responsible for accounting for Tax related to the supply ... and shall not report such Tax in his Tax Return". Cabinet Decision 127/2024 (precious metals and stones) Art 2(1)(a) says the same. The recipient accounts for it.
- **The invoice must carry an explicit reverse charge statement** (CD 153/2025 Art 2(3)(b)(3)).
- **Before the supply the supplier must hold the recipient's two written declarations** (intended use for resale or production; registered with the FTA) **and verify the recipient's registration** (both decisions, Art 2(3)). Without the declarations the reverse charge does not apply and the supplier charges VAT in the ordinary way (Art 2(4)).
- **It does not apply to a supply that is zero rated** (Art 2(2)).
- **The VAT 201 has no supplier-side reverse charge box.** The FTA's VAT Returns User Guide (v4.0, 2021) defines Box 3 as "the value of supplies of goods and services *received*" under the reverse charge, listing "local supplies subject to the reverse charge provisions (e.g. specific supplies within the oil and gas industry)" among what the recipient includes, and Box 10 as the recipient's recovery.

**Not settled by any primary source found**
- Where, or whether, the *value* of such a supply appears on the supplier's return. The decisions say only that the supplier does not report "such Tax". The FAF sales tax code list does include `RC` (section 4), which suggests the supply is recorded in the books but carries no tax. Confirm with the FTA or an adviser before relying on it.
- Whether electronic devices (CD 91/2023, public clarification VATP034) have the same supplier rules in the current text; only secondary sources were read.

**PINT AE requirements for category AE lines** (official Schematron)
- Percent 5, line and breakdown tax amounts 0 (ibr-162-ae, aligned-ibrp-ae-09-ae); the buyer's TRN is required (ibr-103-ae).
- A goods or services type (BTAE-09, `NatureCode`) from a closed list (ibr-006-ae, ibr-166-ae): `DL8.48.8.2` Electronic Devices, `DL8.48.8.1` Gold and Diamonds, `DL8.48.3.1` Crude or refined oil, `DL8.48.3.2` Natural gas, `DL8.48.3.3` Pure hydrocarbons. **There is no code for metal scrap**, so a metal scrap supply cannot be expressed in PINT AE v1.0.4.
- An item standard identifier with scheme `0160` (GTIN) on every AE line (ibr-174-ae).
- AE appears on mixed documents; a document with only E and O lines is a 480/81 (rule ibr-122-ae).

## 9. Cabinet Decision 149/2026 (read 2026-10-10)

Source: the FTA's consolidated Executive Regulation of September 2026, which footnotes every change made by CD 149/2026 (issued 1 September 2026, effective **1 October 2026**, so already in force), checked against secondary summaries. Almost all of it is a rule the user applies, not a calculation the app makes.

**In force now**
| ER article | Change | What it means for the app |
|---|---|---|
| Art 4(6), new | A supply of several components is **one composite supply**, taxed by its principal component, where the components are interconnected and cannot be separated | A judgement on the facts. Sold as a **Product Bundle**: one invoice row, for the bundle item, carrying the principal component's VAT category, tax template and rate. A **Principal Component** field on the bundle warns when the bundle item's category differs. Whether components are really inseparable is the user's judgement |
| Art 29(5) (margin scheme) | The "purchase price" includes costs and fees **only where the input VAT on them is not recoverable** | The app takes the purchase price as entered and cannot tell what it contains. The user must enter it on this basis |
| Art 41(4) | Zero rating of medical products (as specified by Cabinet decision) | A choice of VAT category by the user |
| Art 46(2) | A person is "outside the State" if present for under 30 days and not effectively connected with the supply | Bears on the place of supply of services; the user's judgement |
| Art 53 (employee benefits, sub-clauses 34 and 35) | Tighter tests for recovering input VAT on goods and services provided to employees, such as accommodation | The user ticks **Input VAT Not Recoverable**; nothing is derived |
| Art 54(3), new | Input VAT is **not recoverable** on a supply whose value exceeds an amount set by a decision of the Minister, where it is paid or intended to be paid **in cash** | **The Ministerial Decision with the amount had not been published** in any source found (about 10 days after the effective date). Built as a setting (UAE Compliance Settings, off until set): cash paid on the invoice, by a Payment Entry, or marked intended, on a supply above the limit. The wording refers to the value of the supply, not the cash part |
| Art 57 | Capital asset defined as a "business asset" of AED 5M or more | No change to the scheme as built |
| Art 60(1)(a) | The credit note must show the words "Tax Credit Note" | The print format already does |

**From the first tax year starting after 1 October 2027**
- Art 55(6) and (7) are rewritten: input VAT is recovered in full where it relates to taxable supplies, none where it relates to others, and the rest by the percentage of taxable supplies in all supplies, rounded to a whole number. Capital assets and reverse charge receipts are excluded from the percentage.
- A new Art 55 clause sets a separate calculation for **government entities and charities**.
- The app's partial exemption (rounded percentage of taxable over taxable plus exempt supplies) is close to this already. The exclusion of capital asset supplies and reverse charge receipts from the percentage, and the government and charity method, are not built.

**Open points**
- The Ministerial Decision on the cash payment amount: watch the Ministry of Finance and FTA sites and enter the amount in UAE Compliance Settings when it is published. The rule counts the supply's value, not the cash part, and a payment intended in cash is marked by the user; confirm the reading with an adviser.
- Confirm with an adviser how the composite supply rule applies to a given bundle (software licence, support and hosting) and which component is principal.
