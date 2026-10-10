from uae_compliance.uae_compliance.constants import (
	INPUT_TAX_ATTRIBUTION_SELECT_OPTIONS,
	MODULE,
	REVERSE_CHARGE_TYPE_SELECT_OPTIONS,
	SALES_REVERSE_CHARGE_TYPE_SELECT_OPTIONS,
	VAT_CATEGORY_SELECT_OPTIONS,
)
from uae_compliance.uae_compliance.constants.emirates import EMIRATE_SELECT_OPTIONS
from uae_compliance.uae_compliance.constants.pint_ae import (
	CREDIT_REASON_SELECT_OPTIONS,
	EXEMPTION_REASON_SELECT_OPTIONS,
	ITEM_TYPE_SELECT_OPTIONS,
	LEGAL_REGISTRATION_SELECT_OPTIONS,
)

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
		_field(
			"uae_tax_group",
			"Tax Group",
			"Link",
			"uae_company_name_in_arabic",
			options="UAE Tax Group",
			read_only=1,
		),
	],
	("Company", "Customer", "Supplier"): [
		_field("uae_trn", "TRN", "Data", "tax_id"),
		_field("uae_tin", "TIN (Peppol)", "Data", "uae_trn"),
	],
	("Company", "Customer"): [
		_field(
			"uae_legal_registration_type",
			"Legal Registration Type",
			"Select",
			"uae_tin",
			options=LEGAL_REGISTRATION_SELECT_OPTIONS,
		),
		_field(
			"uae_legal_registration_id",
			"Legal Registration ID",
			"Data",
			"uae_legal_registration_type",
		),
		_field(
			"uae_licence_authority",
			"Licence Issuing Authority",
			"Data",
			"uae_legal_registration_id",
		),
		_field(
			"uae_passport_country",
			"Passport Issuing Country",
			"Link",
			"uae_licence_authority",
			options="Country",
			depends_on="eval:doc.uae_legal_registration_type=='Passport'",
		),
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
		_field(
			"uae_excise_category",
			"Excise Category",
			"Link",
			"uae_vat_category",
			options="UAE Excise Rate",
		),
		_field(
			"uae_excise_volume_litres",
			"Volume per Stock Unit (Litres)",
			"Float",
			"uae_excise_category",
			depends_on="uae_excise_category",
		),
		_field(
			"uae_item_type",
			"E-Invoice Item Type",
			"Select",
			"uae_excise_volume_litres",
			options=ITEM_TYPE_SELECT_OPTIONS,
		),
		_field("uae_sac_code", "Service Accounting Code", "Data", "uae_item_type"),
		_field(
			"uae_exemption_reason_code",
			"VAT Exemption Reason",
			"Select",
			"uae_sac_code",
			options=EXEMPTION_REASON_SELECT_OPTIONS,
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
		_field(
			"uae_exemption_reason_code",
			"VAT Exemption Reason",
			"Select",
			"uae_vat_category",
			options=EXEMPTION_REASON_SELECT_OPTIONS,
		),
		_field("uae_fetch_vat_accounts", "Fetch VAT Accounts", "Button", "section_break_5"),
	],
	"Product Bundle": [
		_field(
			"uae_principal_item",
			"Principal Component",
			"Link",
			"description",
			options="Item",
		),
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
		_field(
			"uae_cash_payment_intended",
			"Cash Payment Intended",
			"Check",
			"uae_is_postponed_import_vat",
		),
	],
	"Sales Invoice Item": [
		_field(
			"uae_margin_purchase_price",
			"Margin Scheme Purchase Price",
			"Currency",
			"uae_vat_category",
			options="currency",
			depends_on="eval:parent.uae_is_margin_scheme",
		),
	],
	"Purchase Invoice Item": [
		_field(
			"uae_input_tax_not_recoverable",
			"Input VAT Not Recoverable",
			"Check",
			"uae_vat_category",
		),
		_field(
			"uae_input_tax_attribution",
			"Input VAT Attribution",
			"Select",
			"uae_input_tax_not_recoverable",
			options=INPUT_TAX_ATTRIBUTION_SELECT_OPTIONS,
		),
	],
	"Sales Invoice": [
		_field("uae_supply_date", "Supply Date", "Date", "posting_date"),
		_field("uae_einvoice_uuid", "E-Invoice UUID", "Data", "amended_from", read_only=1, no_copy=1),
		_field(
			"uae_einvoice_status",
			"E-Invoice Status",
			"Data",
			"uae_einvoice_uuid",
			read_only=1,
			no_copy=1,
		),
		# Not a Link: a Link would stop the log being deleted once its retention period has passed.
		_field(
			"uae_einvoice_log",
			"E-Invoice Log",
			"Data",
			"uae_einvoice_status",
			read_only=1,
			no_copy=1,
		),
		_field(
			"uae_credit_note_reason",
			"Reason for Credit Note",
			"Small Text",
			"return_against",
			depends_on="is_return",
		),
		_field(
			"uae_credit_note_reason_code",
			"Credit Note Reason Code",
			"Select",
			"uae_credit_note_reason",
			options=CREDIT_REASON_SELECT_OPTIONS,
			depends_on="is_return",
		),
		_field(
			"uae_credit_note_original_value",
			"Value Before This Credit Note",
			"Currency",
			"uae_credit_note_reason",
			options="Company:company:default_currency",
			read_only=1,
			depends_on="is_return",
		),
		_field("uae_is_export", "Export", "Check", "customer_address", read_only=1),
		_field(
			"uae_is_simplified_tax_invoice",
			"Simplified Tax Invoice",
			"Check",
			"uae_is_export",
			read_only=1,
		),
		_field(
			"uae_is_margin_scheme",
			"Profit Margin Scheme",
			"Check",
			"uae_is_simplified_tax_invoice",
		),
		_field(
			"uae_is_free_zone_supply",
			"Supply Involving Free Trade Zone",
			"Check",
			"uae_is_margin_scheme",
		),
		_field(
			"uae_free_zone_beneficiary_id",
			"Free Zone Beneficiary ID",
			"Data",
			"uae_is_free_zone_supply",
			depends_on="uae_is_free_zone_supply",
			mandatory_depends_on="uae_is_free_zone_supply",
		),
		_field("uae_is_deemed_supply", "Deemed Supply", "Check", "uae_free_zone_beneficiary_id"),
		_field("uae_is_ecommerce_supply", "Supply through E-commerce", "Check", "uae_is_deemed_supply"),
		_field("uae_is_reverse_charge", "Reverse Charge Supply", "Check", "uae_is_ecommerce_supply"),
		_field(
			"uae_reverse_charge_type",
			"Reverse Charge Type",
			"Select",
			"uae_is_reverse_charge",
			options=SALES_REVERSE_CHARGE_TYPE_SELECT_OPTIONS,
			depends_on="uae_is_reverse_charge",
			mandatory_depends_on="uae_is_reverse_charge",
		),
		_field(
			"uae_rc_declaration",
			"Recipient Declarations Held",
			"Check",
			"uae_reverse_charge_type",
			depends_on="uae_is_reverse_charge",
			mandatory_depends_on="uae_is_reverse_charge",
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
