# UAE Compliance – User Guide

For the people who set up and use UAE VAT in ERPNext. Settings are described in [UAE_COMPLIANCE_CONFIGURATION.md](UAE_COMPLIANCE_CONFIGURATION.md); how the app is built is in [UAE_COMPLIANCE_ARCHITECTURE.md](UAE_COMPLIANCE_ARCHITECTURE.md).

The app works for companies whose country is United Arab Emirates. Other companies on the same site are not affected. It replaces ERPNext's built-in UAE fields and report: those fields are hidden, and you report with the **UAE VAT Return** instead.

## 1. Set up once

1. **UAE Compliance Settings:** add a row for your company with the Output VAT account, the Input VAT account (and Excise Tax account if you pay excise) and your filing frequency (Quarterly Stagger 1, 2 or 3, or Monthly).
2. **Company:** enter the **TRN** (15 digits, starting with 1 and ending with 03), the **TIN (Peppol)** (10 digits), the Arabic name if you print Arabic invoices, and the **Legal Registration** type and ID. Add the company address with its **Emirate**.
3. **Item Tax Templates:** give each template a **VAT Category** (Standard Rated, Zero Rated, Exempt or Out of Scope). Use **Fetch VAT Accounts** on a template to add the company's VAT accounts to it. Zero rated and exempt templates should carry 0% VAT. Exempt items also need a **VAT Exemption Reason**.
4. **Items:** set a default **VAT Category**. Services need a **Service Accounting Code** for e-invoices, and goods use the customs tariff number as the HS code.
5. **Customers and suppliers:** enter the **TRN** (and **TIN** for businesses you will e-invoice). Mark customers in a **Designated Zone** on their address.

Data from ERPNext's own UAE VAT setup (item flags, VAT accounts, TRNs) is migrated when the app is installed or updated. Check **Error Log** for cases it could not decide.

## 2. Sales

- **Standard rated sales** need a **VAT Emirate** on the invoice: Box 1 of the return is reported by emirate. It defaults from the customer's address.
- **Zero rated and exempt rows** must carry no VAT. The app refuses a row whose category and VAT disagree, and refuses an explicit 0% rate on a standard rated row; mark it Zero Rated or Exempt instead.
- **Exports** are ticked **Export** and are zero rated.
- **Designated zones** are never zero rated automatically. Whether a supply is zero rated depends on the goods and the customs conditions, so you choose the category.
- **Simplified tax invoices** (under AED 10,000, customer details optional) are ticked **Simplified Tax Invoice**. Companies that send e-invoices do not use them.
- **Foreign currency:** the invoice shows the VAT in AED as well.
- **Tourist refunds** are entered as **Tax Refund provided to Tourists** (minimum AED 250 of VAT in a supply, up to AED 35,000) and appear in Box 2.
- **Profit margin scheme:** tick **Profit Margin Scheme** and enter the **Margin Scheme Purchase Price**; VAT is charged on the margin only.
- **Print:** use the print formats **UAE Tax Invoice**, **UAE Simplified Tax Invoice** and **UAE Tax Credit Note**.

### Credit notes
Make a return against the invoice. It needs a **Credit Note Reason Code** for e-invoicing. A tax credit note should be issued within 14 days of the event that changes the supply; the app warns when it is later. Credit notes reduce the amount and VAT of the period they are issued in, in the same box as the original.

## 3. Purchases

- Standard rated purchases from UAE suppliers are recoverable when the VAT is posted to the Input VAT account. Tick **Input VAT Not Recoverable** for blocked input VAT such as some entertainment.
- **Reverse charge:** tick **Reverse Charge Applicable** and choose the **Reverse Charge Type** (imports of services or goods, hydrocarbons, electronic devices, precious metals and stones, metal scrap, other). Add both the Output and Input VAT rows; the VAT is declared in Box 3 and recovered in Box 10. Purchases from a GCC supplier are ticked **GCC Supplier**.
- **Imports of goods:** tick **Import of Goods**, with the **Import Permit Number**. If VAT is postponed through the customs account, tick **Postponed Import VAT**: it is declared in Box 6 and recovered in Box 10. VAT paid at the border is an ordinary purchase.
- **Partial exemption:** if you make both taxable and exempt supplies, mark each purchase's **Input VAT Attribution** as Taxable Supplies, Exempt Supplies or Residual. Exempt VAT is not recovered; residual VAT is recovered at the period's recovery ratio, and the annual apportionment corrects it afterwards.

## 4. Adjustments and schemes

- **UAE VAT Adjustment:** bad debt relief (more than six months after the supply, with the customer notified), its repayment, the annual apportionment and other adjustments. These appear in the adjustment column of the return. Credit notes do not.
- **UAE Capital Asset:** record an asset of AED 5,000,000 or more bought with input VAT; the app calculates the yearly adjustments (5 years, 10 for buildings).
- **UAE Excise Rate** holds excise rates by category; give an excisable item its **Excise Category**.
- **UAE Tax Group:** list the member companies and the representative. The representative files one return for the group, and supplies between members are left out.

## 5. VAT 201 return

1. Create a **UAE VAT Return** for the company and period. The period must match your filing frequency; the due date is the 28th day after the period ends.
2. Choose **Generate Return**. It fills Boxes 1a to 1g (by emirate), 2 to 11, and the net figures in Boxes 12 to 14. Tick **Request a Refund** for Box 15.
3. Check the figures against the **UAE VAT Sales Register** and **UAE VAT Purchase Register**, which list the invoices behind each box. If anything changes after you generate, the return is marked stale: generate it again.
4. File on EmaraTax, then choose **Mark as Filed**. A filed return cannot be changed.
5. **Download FAF** produces the FTA Audit File for the period.

The app does not calculate penalties.

## 6. E-invoicing

Only companies enabled in **UAE E-Invoice Settings** send e-invoices (see the configuration guide). From then on:

1. Submitting a Sales Invoice builds its PINT AE document and checks it. An invoice that would be invalid is **not issued**: fix what the message says (a missing TRN, TIN, address, VAT Emirate, and so on) and submit again.
2. The invoice is sent in the background. Its **E-Invoice Status** shows the progress: Generated, Submitted (accepted by the provider), Delivered (to the buyer) and Cleared (reported to the FTA). Rejected means the provider or the FTA refused it; the reasons are in the **E-Invoice Log**.
3. A failed send is retried automatically with increasing waits. After the retry limit the log shows Failed. Fix the cause and use **Retry** on the log.
4. **A sent invoice cannot be cancelled.** Issue a credit note. An invoice whose last send attempt has no known outcome (for example, a timeout) also cannot be cancelled: use **Retry** until the status is settled.
5. Logs are kept for five years and cannot be deleted before.

Received invoices appear as **inbound** logs, matched to your suppliers by TIN or TRN. One that cannot be read or is addressed to someone else is marked Invalid with the reason. Entering them as Purchase Invoices is still done by hand.

### What cannot be sent yet
Invoices with reverse charge or out of scope supplies, margin scheme invoices, charges or discounts outside the item rows, VAT that differs from the rows, and self-billing, summary, continuous, agent or deemed supply invoices are refused or logged as Invalid with a clear message. Issue them outside the app and keep to your provider's process until support is added. A company whose own currency is not AED cannot send e-invoices.

## 7. When something looks wrong

| You see | Likely cause |
|---|---|
| "Invalid E-Invoice" on submit | A required identifier or address detail is missing; the message lists each. |
| TRN or TIN rejected | It does not match the pattern in UAE Compliance Settings (15 digits starting 1 ending 03; 10 digits starting 1). |
| Box 1 is zero for a standard rated sale | The invoice has no VAT Emirate, or its VAT is not on the Output VAT account. |
| A purchase is missing from Box 9 | It is blocked input VAT, attributed to exempt supplies, or not Standard Rated. |
| E-invoice stays Generated | The provider was unreachable; it retries on its own. Check **Status Detail** on the log. |
| Log says provider settings changed | The log was created under another provider or environment. Restore the settings, then use **Retry**. |
| Return is stale | Invoices changed after generation. Generate it again. |
