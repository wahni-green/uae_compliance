from uae_compliance.uae_compliance.constants import (
	MODULE,
	REVERSE_CHARGE_TYPE_SELECT_OPTIONS,
	VAT_CATEGORY_SELECT_OPTIONS,
)
from uae_compliance.uae_compliance.constants.emirates import EMIRATE_SELECT_OPTIONS

# Every field uses the `uae_` prefix so it never clashes with ERPNext's own UAE regional fields or
# with oman_compliance's fields on a shared bench.


def _field(fieldname, label, fieldtype, insert_after, **kwargs):
	field = {
		"fieldname": fieldname,
		"label": label or None,
		"fieldtype": fieldtype,
		"insert_after": insert_after,
		"module": MODULE,
	}
	if fieldtype in ("Data", "Small Text", "Select"):
		field["translatable"] = 0

	field.update(kwargs)
	return field


_ITEM_ROW_DOCTYPES = (
	"Sales Order Item",
	"Quotation Item",
	"Delivery Note Item",
	"Sales Invoice Item",
	"Purchase Invoice Item",
)

CUSTOM_FIELDS = {
	"Company": [
		_field("uae_company_name_in_arabic", "Company Name in Arabic", "Data", "company_name"),
	],
	("Company", "Customer", "Supplier"): [
		_field("uae_trn", "TRN", "Data", "tax_id"),
		_field("uae_tin", "TIN (Peppol)", "Data", "uae_trn"),
	],
	"Customer": [
		_field("uae_customer_name_in_arabic", "Customer Name in Arabic", "Data", "customer_name"),
	],
	"Supplier": [
		_field("uae_supplier_name_in_arabic", "Supplier Name in Arabic", "Data", "supplier_name"),
	],
	"Address": [
		_field("uae_address_in_arabic", "Address in Arabic", "Small Text", "address_line2"),
		_field("uae_emirate", "Emirate", "Select", "state", options=EMIRATE_SELECT_OPTIONS),
		_field(
			"uae_designated_zone",
			"Designated Zone",
			"Link",
			"country",
			options="UAE Designated Zone",
		),
	],
	"Item": [
		_field(
			"uae_vat_category",
			"VAT Category",
			"Select",
			"item_group",
			options=VAT_CATEGORY_SELECT_OPTIONS,
		),
	],
	_ITEM_ROW_DOCTYPES: [
		_field(
			"uae_vat_category",
			"VAT Category",
			"Select",
			"item_tax_template",
			options=VAT_CATEGORY_SELECT_OPTIONS,
			in_list_view=1,
		),
	],
	"Item Tax Template": [
		_field(
			"uae_vat_category",
			"VAT Category",
			"Select",
			"disabled",
			options=VAT_CATEGORY_SELECT_OPTIONS,
		),
		_field("uae_fetch_vat_accounts", "Fetch VAT Accounts", "Button", "section_break_5"),
	],
	("Sales Order", "Delivery Note", "Sales Invoice"): [
		_field(
			"uae_emirate",
			"VAT Emirate",
			"Select",
			"company_address",
			options=EMIRATE_SELECT_OPTIONS,
			fetch_from="company_address.uae_emirate",
			fetch_if_empty=1,
		),
	],
	"Purchase Invoice": [
		# Anchored on the last field before the "Taxes and Charges" section, so that section's own
		# fields are not pulled into this one (a Section Break swallows every field after it).
		_field("uae_vat_section", "UAE VAT", "Section Break", "base_tax_withholding_net_total"),
		_field("uae_is_reverse_charge", "Reverse Charge Applicable", "Check", "uae_vat_section"),
		_field(
			"uae_reverse_charge_type",
			"Reverse Charge Type",
			"Select",
			"uae_is_reverse_charge",
			options=REVERSE_CHARGE_TYPE_SELECT_OPTIONS,
			depends_on="uae_is_reverse_charge",
			mandatory_depends_on="uae_is_reverse_charge",
		),
		_field(
			"uae_rc_declaration",
			"Recipient Declaration on File",
			"Check",
			"uae_reverse_charge_type",
			depends_on="eval:doc.uae_reverse_charge_type=='Metal Scrap'",
		),
		_field("uae_is_gcc_supplier", "GCC Supplier", "Check", "uae_rc_declaration", read_only=1),
		_field("uae_permit_no", "Import Permit Number", "Data", "uae_is_gcc_supplier"),
		_field("uae_column_break_pinv", "", "Column Break", "uae_permit_no"),
		_field("uae_is_import_of_goods", "Import of Goods", "Check", "uae_column_break_pinv", read_only=1),
		_field(
			"uae_is_postponed_import_vat",
			"Postponed Import VAT",
			"Check",
			"uae_is_import_of_goods",
		),
	],
	"Purchase Invoice Item": [
		_field(
			"uae_input_tax_not_recoverable",
			"Input VAT Not Recoverable",
			"Check",
			"uae_vat_category",
		),
	],
	"Sales Invoice": [
		_field("uae_supply_date", "Supply Date", "Date", "posting_date"),
		_field("uae_is_export", "Export", "Check", "customer_address", read_only=1),
		_field(
			"uae_is_simplified_tax_invoice",
			"Simplified Tax Invoice",
			"Check",
			"uae_is_export",
			read_only=1,
		),
		_field(
			"uae_tourist_refund",
			"Tax Refund provided to Tourists",
			"Currency",
			"uae_emirate",
			options="currency",
		),
	],
}
