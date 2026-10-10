# Phase 5 – Advanced schemes

- [x] Profit margin scheme (invoice flag, return section; e-invoice flag in Phase 6) (PR 5b)
- [x] Partial exemption: input apportionment and annual adjustment (PR 5a)
- [x] Capital asset scheme (5 years, 10 for buildings; assets >= AED 5M; rules confirmed in UAE_VERIFICATION.md) (PR 5a)
- [x] Bad-debt relief and repayment (PR 5a)
- [x] Tourist refund (box 2): validations (PR 5b)
- [x] Excise tax: rates, item categories and a check on invoices; the excise return itself is not built (PR 5b)
- [x] Tax groups (PR 5c)
- [x] Tests for each scheme

## From verification (see ../UAE_VERIFICATION.md)
- [x] Capital assets: 5 years non-buildings, 10 years buildings, AED 5M threshold (PR 5a)
- [x] Excise rates per CD 197/2025 (volumetric sweetened drinks AED 1.09 / 0.79 per litre, 100% tobacco, e-liquids and energy drinks), item categories and an invoice check (PR 5b)
- [ ] Excise return and excise on purchases (not built; only needed if the company files excise through this app)
- [ ] **CD 149/2026 (in force since 1 Oct 2026, so already applicable): not implemented.** (a) Margin scheme: the purchase price includes costs only where the related input tax is not recoverable; the app takes the purchase price as entered, so it neither checks nor derives it. (b) Composite supply (ER Art 4(6)): interconnected components are one supply, which matters for licence, support and hosting bundles; nothing in the app identifies or treats them. (c) Input tax and apportionment changes, including the government/charity method from the first tax year starting after 1 Oct 2027. Read the Cabinet Decision text before building
- [x] Tourist refund: minimum purchase AED 250, cap AED 35,000, refund not above the VAT charged, standard rated only (PR 5b)
- [ ] Tourist refund: the 90-day limit and the AED 35,000 cap per 24 hours across invoices are not validated (only a single invoice is checked)

## PR 5a: adjustments, partial exemption, capital assets
- **UAE VAT Adjustment** (submittable): Bad Debt Relief (box 1 adjustment column, per emirate, negative; more than six months after the supply, customer notified, never more than the VAT charged), Bad Debt Repayment (box 9 adjustment, negative; more than six months after the supplier's notice), Annual Apportionment and Capital Assets Scheme (box 9 adjustment, signed), Import Adjustment (box 7 amount and VAT).
- **Partial exemption:** `Input VAT Attribution` on purchase rows (Taxable Supplies, Exempt Supplies, Residual). Residual input VAT is recovered at the period's ratio, taxable (standard and zero rated) over taxable plus exempt supplies, rounded to a whole percentage; exempt-attributed rows claim nothing. The ratio and residual figures are stored on the return, and **Calculate Apportionment** on an Annual Apportionment adjustment trues the year up from its Filed returns. The further adjustment when the annual difference exceeds AED 250,000 and the sectoral methods are not built.
- **UAE Capital Asset:** assets costing AED 5M or more excluding VAT; a yearly schedule (10 years for buildings, 5 for other assets) adjusting 1/10 or 1/5 of the input VAT by the change in the recoverable percentage, with a button that creates a draft UAE VAT Adjustment per year (a cancelled one can be replaced).
- Review hardening: bad debt relief needs the write-off and notice dates on or before the adjustment date, takes its emirate from the invoice and re-checks the VAT limit under a lock on the invoice at submission; an adjustment cannot be dated in a period whose return is Filed; one Annual Apportionment per tax year; the annual calculation needs the year's Filed returns to run without a gap and to have recorded their figures; import adjustments recover their recoverable share (default 100%) in box 10.

## PR 5b: profit margin scheme, tourist refunds, excise
- **Profit margin scheme:** `Profit Margin Scheme` on a sales invoice and a purchase price per row. The row amount is the price before the VAT; the VAT due is the standard rate of the margin (net amount less purchase price, never below zero per row), and the VAT posted to the Output VAT account must equal it. The invoice prints with no tax amount and a margin scheme statement. The return reports the full sales value (price including the VAT) in box 1 and the purchase price in box 9 with no recoverable VAT, and ticks the profit margin scheme question (set from the margin sales of the period on every generation). Rows sharing an item code split the VAT by margin, so a row sold at a loss takes none. Returns of margin invoices are not validated.
- **Tourist refunds:** a refund cannot exceed the VAT charged, the purchase must be at least AED 250, the refund at most AED 35,000, and only standard rated sales qualify; it is recorded in the invoice currency and converted for box 2.
- **Excise:** `UAE Excise Rate` (seeded from Cabinet Decision 197/2025: tobacco, e-cigarette liquids and devices, energy drinks 100%; sweetened drinks AED 1.09 per litre at 8 g or more sugar per 100 ml and AED 0.79 at 5 g to under 8 g), an excise category and volume per unit on Item, and a warning on sales invoices when the excise charged on the Excise Tax account differs from what the goods require. The excise return and excise on purchases are not built. The volume on the Item is per stock unit (a carton of 24 half-litre bottles is 12 litres), per-litre excise uses the stock quantity, and only an active rate in force on the invoice date applies.

## PR 5c: tax groups
- **UAE Tax Group** (members, a representative member, one group per company) mirrored on Company as `Tax Group`. The representative's VAT return covers every member's invoices and adjustments; a member that is not the representative cannot generate a return. Supplies between members, identified by the internal customer or supplier that represents the other member (`Represents Company`), are disregarded in the return and in both registers. Every member needs its VAT accounts configured. The FAF export still covers a single company.
- Review hardening: a company's Input VAT Account is required when it has purchases in the period (otherwise their recoverable VAT would silently be zero); a draft return records the companies it covered and goes stale when the group changes; bad debt relief or repayment of a supply between members is refused, and one that predates the group is left out of the return; membership checks lock the member companies in a fixed order and read membership with a locking read.
