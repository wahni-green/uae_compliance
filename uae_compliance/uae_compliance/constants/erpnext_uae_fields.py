# Custom fields created by ERPNext's own UAE localization (erpnext/regional/united_arab_emirates/
# setup.py) that this app replaces. They are hidden (never deleted) by Property Setters.
_PURCHASE = [
	"company_trn",
	"supplier_name_in_arabic",
	"recoverable_standard_rated_expenses",
	"reverse_charge",
	"recoverable_reverse_charge",
	"permit_no",
	"vat_section",
]
_SALES = [
	"company_trn",
	"customer_name_in_arabic",
	"vat_emirate",
	"tourist_tax_return",
	"permit_no",
	"vat_section",
]
_ITEM_ROW = ["tax_code", "tax_rate", "tax_amount", "total_amount"]

ERPNEXT_UAE_FIELDS = {
	"Item": ["tax_code", "is_zero_rated", "is_exempt"],
	"Customer": ["customer_name_in_arabic"],
	"Supplier": ["supplier_name_in_arabic"],
	"Address": ["emirate"],
	"Purchase Invoice": _PURCHASE,
	"Purchase Order": _PURCHASE,
	"Purchase Receipt": _PURCHASE,
	"Sales Invoice": _SALES,
	"POS Invoice": _SALES,
	"Sales Order": _SALES,
	"Delivery Note": _SALES,
	"Sales Invoice Item": [*_ITEM_ROW, "is_zero_rated", "is_exempt"],
	"POS Invoice Item": [*_ITEM_ROW, "is_zero_rated", "is_exempt"],
	"Purchase Invoice Item": _ITEM_ROW,
	"Sales Order Item": _ITEM_ROW,
	"Delivery Note Item": _ITEM_ROW,
	"Quotation Item": _ITEM_ROW,
	"Purchase Order Item": _ITEM_ROW,
	"Purchase Receipt Item": _ITEM_ROW,
	"Supplier Quotation Item": _ITEM_ROW,
}
