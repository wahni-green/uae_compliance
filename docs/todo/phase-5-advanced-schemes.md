# Phase 5 – Advanced schemes

- [ ] Profit margin scheme (invoice flag, return section, e-invoice flag)
- [x] Partial exemption: input apportionment and annual adjustment (PR 5a)
- [ ] Capital asset scheme (10-year adjustment, assets >= AED 5M) - confirm rules
- [ ] Bad-debt relief
- [ ] Tourist refund (box 2) - confirm scheme specifics
- [ ] Excise tax (50%/100% items, accounts, reporting)
- [ ] Tax groups
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
