# Phase 5 – Advanced schemes

- [x] Profit margin scheme (invoice flag, return section; e-invoice flag in Phase 6) (PR 5b)
- [x] Partial exemption: input apportionment and annual adjustment (PR 5a)
- [ ] Capital asset scheme (10-year adjustment, assets >= AED 5M) - confirm rules
- [ ] Bad-debt relief
- [x] Tourist refund (box 2): validations (PR 5b)
- [x] Excise tax: rates, item categories and a check on invoices; the excise return itself is not built (PR 5b)
- [x] Tax groups (PR 5c)
- [ ] Tests for each scheme

## From verification (see ../UAE_VERIFICATION.md)
- [x] Capital assets: 5 years non-buildings, 10 years buildings, AED 5M threshold (PR 5a)
- [ ] Excise per CD 197/2025: volumetric sweetened drinks (AED 1.09 / 0.79 per litre), 100% tobacco/e-liquids/energy drinks
- [ ] CD 149/2026: composite supply (Art 4(6)), margin scheme purchase price rules, apportionment changes (from tax year after 1 Oct 2027)
- [ ] Tourist refund: 90 days, min AED 250, cap AED 35,000 per 24 h

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
