# UAE Compliance – User Guide

For the people who set up and use UAE VAT in ERPNext. Settings are described in [UAE_COMPLIANCE_CONFIGURATION.md](UAE_COMPLIANCE_CONFIGURATION.md); how the app is built is in [UAE_COMPLIANCE_ARCHITECTURE.md](UAE_COMPLIANCE_ARCHITECTURE.md).

The app works for companies whose country is United Arab Emirates. Its invoice checks apply only to UAE companies, but hiding ERPNext's built-in UAE fields affects the whole site (existing field data is kept). For UAE companies, report with the **UAE VAT Return** instead of ERPNext's UAE VAT report.

## 1. Set up once

1. **UAE Compliance Settings:** add a row for your company with the Output VAT account, the Input VAT account (and Excise Tax account if you pay excise) and your filing frequency (Quarterly Stagger 1, 2 or 3, or Monthly).
2. **Company:** enter the **TRN** (15 digits, starting with 1 and ending with 03), the **TIN (Peppol)** (10 digits), the Arabic name if you print Arabic invoices, and the **Legal Registration** type and ID. Add the company address with its **Emirate**.
3. **Item Tax Templates:** give each template a **VAT Category** (Standard Rated, Zero Rated, Exempt or Out of Scope). Use **Fetch VAT Accounts** on a template to add the company's VAT accounts to it. Zero rated and exempt templates should carry 0% VAT. Exempt items also need a **VAT Exemption Reason**.
4. **Items:** set a default **VAT Category**. Services need a **Service Accounting Code** for e-invoices, and goods use the customs tariff number as the HS code.
5. **Customers and suppliers:** enter the **TRN** (and **TIN** for businesses you will e-invoice). Mark customers in a **Designated Zone** on their address.

Data from ERPNext's own UAE VAT setup (item flags, VAT accounts, TRNs) is migrated when the app is installed or updated. Check **Error Log** for cases it could not decide.

## 2. Sales

- **Standard rated sales** need a **VAT Emirate** on the invoice: Box 1 of the return is reported by emirate. It defaults from the company's address.
- **Zero rated and exempt rows** must carry no VAT. The app refuses a row whose category and VAT disagree, and refuses an explicit 0% rate on a standard rated row; mark it Zero Rated or Exempt instead.
- **Exports:** **Export** is set for you when the shipping (or customer) address is in a country other than the company's. You cannot tick it yourself. Choose Zero Rated for the rows.
- **Designated zones** are never zero rated automatically. Whether a supply is zero rated depends on the goods and the customs conditions, so you choose the category.
- **Simplified tax invoices** (under AED 10,000, customer details optional) are flagged **Simplified Tax Invoice** automatically: only for customers without a TRN, up to the threshold in UAE Compliance Settings, and never for companies that send e-invoices.
- **Free trade zone, deemed and e-commerce supplies:** tick **Supply Involving Free Trade Zone** (and enter the **Free Zone Beneficiary ID**), **Deemed Supply** (a supply without consideration; it has no due date or payment details on the e-invoice) or **Supply through E-commerce** (the e-invoice then carries the delivery address, taken from the shipping address, else the customer's: it needs a street, city and emirate). These only mark the e-invoice; VAT is worked out as before.
- **Reverse charge supplies:** when you supply crude or refined oil, natural gas, pure hydrocarbons, electronic devices, or precious metals and stones to a registered recipient who accounts for the VAT, tick **Reverse Charge Supply**, choose the **Reverse Charge Type** and tick **Recipient Declarations Held** (before the supply you must hold the recipient's written declarations of intended use and of registration, and have verified their registration). The invoice charges no VAT, prints the reverse charge statement, and is left out of every box of your VAT 201, because the supplier does not report the tax. The FTA's texts do not say where the *value* of such a sale belongs, so confirm this treatment with the FTA or your tax adviser. Every row must be Standard Rated; it cannot be an export, a margin scheme supply or a zero rated supply, and the customer needs a TRN. For an e-invoice each item needs a barcode of 8, 12, 13 or 14 digits (its GTIN). Metal scrap can be sold this way but cannot be sent as an e-invoice, as the specification has no type of goods for it.
- **Foreign currency:** the invoice shows the VAT in AED as well.
- **Tourist refunds** are entered as **Tax Refund provided to Tourists** (minimum purchase total of AED 250, refund up to AED 35,000) and appear in Box 2.
- **Profit margin scheme:** tick **Profit Margin Scheme** and enter the **Margin Scheme Purchase Price**; VAT is charged on the margin only. On an e-invoice every line shows the price (the amount plus the VAT on its margin) with no VAT stated, as the specification requires; every row must be standard rated.
- **Print:** use the print formats **UAE Tax Invoice**, **UAE Simplified Tax Invoice** and **UAE Tax Credit Note**.

### Credit notes
Make a return against the invoice. It needs a **Credit Note Reason Code** for e-invoicing. A tax credit note should be issued within 14 days of the event that changes the supply; track this deadline yourself, as the app does not warn about late credit notes. Credit notes reduce the amount and VAT of the period they are issued in, in the same box as the original.

## 3. Purchases

- Standard rated purchases from UAE suppliers are recoverable when the VAT is posted to the Input VAT account. Tick **Input VAT Not Recoverable** for blocked input VAT such as some entertainment.
- **Reverse charge:** tick **Reverse Charge Applicable** and choose the **Reverse Charge Type** (imports of services or goods, hydrocarbons, electronic devices, precious metals and stones, metal scrap, other). Add both the Output and Input VAT rows. Purchases other than goods imports are declared in Box 3, with the recoverable VAT in Box 10. For goods imports, see the next bullet. **GCC Supplier** is set for you from the supplier address's country.
- **Imports of goods:** **Import of Goods** is set for you when the Dispatch Address is in another country, or when you choose the **Import of Goods** reverse charge type; entering an **Import Permit Number** alone does not set it. If VAT is postponed through the customs account, tick **Postponed Import VAT**: it is declared in Box 6 and recovered in Box 10. VAT paid at the border is an ordinary purchase.
- **Partial exemption:** if you make both taxable and exempt supplies, mark each purchase's **Input VAT Attribution** as Taxable Supplies, Exempt Supplies or Residual. Exempt VAT is not recovered; residual VAT is recovered at the period's recovery ratio, and the annual apportionment corrects it afterwards.

## 4. Adjustments and schemes

- **UAE VAT Adjustment:** bad debt relief (more than six months after the supply, with the customer notified), its repayment, the annual apportionment and other adjustments. These appear in the adjustment column of the return. Credit notes do not.
- **UAE Capital Asset:** record an asset of AED 5,000,000 or more bought with input VAT; the app calculates the yearly adjustments (5 years, 10 for buildings). For each year, enter the recovery percentage and adjustment date, create the draft **UAE VAT Adjustment**, then review and submit it: the return includes only submitted adjustments.
- **UAE Excise Rate** holds excise rates by category; give an excisable item its **Excise Category**.
- **UAE Tax Group:** list the member companies and the representative. The representative files one return for the group, and supplies between members are left out.

## 5. VAT 201 return

1. Create a **UAE VAT Return** for the company and period. Use the period the FTA assigned you. The app warns if it differs from your configured filing frequency, but allows custom periods, such as a first period starting on the registration date. The due date is the 28th day after the period ends, moved to Monday if it falls on a weekend; public holidays are not considered.
2. Choose **Generate Return**. It fills Boxes 1a to 1g (by emirate), 2 to 11, and the net figures in Boxes 12 to 14. Tick **Request a Refund** for Box 15.
3. Check the figures against the **UAE VAT Sales Register** and **UAE VAT Purchase Register**, which list the invoices behind each box. If invoices or adjustments of the period are submitted, cancelled or changed after you generate, the return warns you and **cannot be filed** until you generate it again.
4. File on EmaraTax, then choose **Mark as Filed**. A filed return cannot be changed.
5. **Download FAF** produces the FTA Audit File for the period.

The app does not calculate penalties.

## 6. E-invoicing

Only companies enabled in **UAE E-Invoice Settings** send e-invoices (see the configuration guide). From then on:

1. Submitting a Sales Invoice builds its PINT AE document and checks it. An invoice whose lines are all exempt or out of scope is sent as an out of scope invoice (type 480; a credit note is type 81), because the specification does not allow them on an ordinary tax invoice. An invoice that would be invalid is **not issued**: fix what the message says (a missing TRN, TIN, address, VAT Emirate, and so on) and submit again.
2. The invoice is sent in the background. Its **E-Invoice Status** shows the progress: Generated, Submitted (accepted by the provider), Delivered (to the buyer) and Cleared (reported to the FTA). Rejected means the provider or the FTA refused it; the reasons are in the **E-Invoice Log**.
3. A failed send is retried automatically with increasing waits. After the retry limit the log shows Failed. Fix the cause and use **Retry** on the log.
4. **A sent invoice cannot be cancelled.** Issue a credit note. An invoice whose last send attempt has no known outcome (for example, a timeout) also cannot be cancelled: use **Retry** until the status is settled.
5. Logs are kept for five years and cannot be deleted before.

Received invoices appear as **inbound** logs, matched to your suppliers by TIN or TRN. One that cannot be read or is addressed to someone else is marked Invalid with the reason. Entering them as Purchase Invoices is still done by hand.

### What cannot be sent yet
Invoices of metal scrap under the reverse charge, charges or discounts outside the item rows, and VAT that differs from the rows are refused or logged as Invalid with a clear message. Self-billing, summary, continuous and agent billing invoices are also unsupported, but the app does not detect or reject them: identify these yourself and issue all unsupported invoices outside the app, following your provider's process until support is added. A company whose own currency is not AED cannot send e-invoices.

## 7. When something looks wrong

| You see | Likely cause |
|---|---|
| "Invalid E-Invoice" on submit | A required identifier or address detail is missing; the message lists each. |
| TRN or TIN rejected | It does not match the pattern in UAE Compliance Settings (15 digits starting 1 ending 03; 10 digits starting 1). |
| Box 1 is zero for a standard rated sale | The invoice has no VAT Emirate, or its VAT is not on the Output VAT account. |
| A purchase is missing from Box 9 | It is blocked input VAT, attributed to exempt supplies, or not Standard Rated. |
| E-invoice stays Generated | The provider was unreachable; it retries on its own. Check **Status Detail** on the log. |
| Log says provider settings changed | The log was created under another provider or environment. Restore the settings, then use **Retry**. |
| "Return Out of Date" when filing | Documents of the period changed after the return was generated. Generate it again. |
