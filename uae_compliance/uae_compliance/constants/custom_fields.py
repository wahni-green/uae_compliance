from uae_compliance.uae_compliance.constants import (
	INPUT_TAX_ATTRIBUTION_SELECT_OPTIONS,
	MODULE,
	REVERSE_CHARGE_TYPE_SELECT_OPTIONS,
	SALES_REVERSE_CHARGE_TYPE_SELECT_OPTIONS,
	VAT_CATEGORY_SELECT_OPTIONS,
)
from uae_compliance.uae_compliance.constants.einvoice import EXCLUSION_SELECT_OPTIONS
from uae_compliance.uae_compliance.constants.emirates import EMIRATE_SELECT_OPTIONS
from uae_compliance.uae_compliance.constants.pint_ae import (
	BILLING_FREQUENCY_SELECT_OPTIONS,
	CREDIT_REASON_SELECT_OPTIONS,
	EXEMPTION_REASON_SELECT_OPTIONS,
	ITEM_TYPE_SELECT_OPTIONS,
	LEGAL_REGISTRATION_SELECT_OPTIONS,
)
from uae_compliance.uae_compliance.utils.company import UAE

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

def _emirate_field(insert_after):
	return _field(
		"uae_emirate",
		"VAT Emirate",
		"Select",
		insert_after,
		options=EMIRATE_SELECT_OPTIONS,
		fetch_from="company_address.uae_emirate",
		fetch_if_empty=1,
	)


def _emirate_tab_fields(insert_after):
	"""A tab of its own, shown only for a UAE company (client_scripts/transaction_tab.js), after the
	last field before Connections, itself a tab."""
	return [
		_field("uae_tab", "UAE Compliance", "Tab Break", insert_after),
		_emirate_field("uae_tab"),
	]


def _sales_invoice_fields():
	"""All on one tab, shown only for a UAE company (client_scripts/transaction_tab.js). A Section Break
	takes every field after it, so the tab sits after the last field before Connections, itself a tab."""
	has_period = "eval:doc.uae_is_summary_invoice || doc.uae_is_continuous_supply"
	return [
		_field("uae_tab", "UAE Compliance", "Tab Break", "remarks"),
		# Supply details
		_field("uae_supply_date", "Supply Date", "Date", "uae_tab"),
		_emirate_field("uae_supply_date"),
		_field("uae_cb_supply_1", "", "Column Break", "uae_emirate"),
		_field(
			"uae_einvoice_exclusion",
			"E-Invoice Exclusion",
			"Select",
			"uae_cb_supply_1",
			options=EXCLUSION_SELECT_OPTIONS,
		),
		_field(
			"uae_einvoice_exclusion_from_items",
			"E-Invoice Exclusion from Items",
			"Check",
			"uae_einvoice_exclusion",
			hidden=1,
			read_only=1,
			no_copy=1,
		),
		# E-invoice status
		_field("uae_einvoice_section", "E-Invoice", "Section Break", "uae_einvoice_exclusion_from_items"),
		_field("uae_einvoice_uuid", "E-Invoice UUID", "Data", "uae_einvoice_section", read_only=1, no_copy=1),
		_field("uae_cb_einvoice_1", "", "Column Break", "uae_einvoice_uuid"),
		_field(
			"uae_einvoice_status",
			"E-Invoice Status",
			"Data",
			"uae_cb_einvoice_1",
			read_only=1,
			no_copy=1,
		),
		_field("uae_cb_einvoice_2", "", "Column Break", "uae_einvoice_status"),
		# Not a Link: a Link would stop the log being deleted once its retention period has passed.
		_field(
			"uae_einvoice_log",
			"E-Invoice Log",
			"Data",
			"uae_cb_einvoice_2",
			read_only=1,
			no_copy=1,
		),
		# Transaction types: an invoice can be several at once, so these stay checkboxes
		_field("uae_type_section", "Transaction Type", "Section Break", "uae_einvoice_log"),
		_field("uae_is_export", "Export", "Check", "uae_type_section", read_only=1),
		_field("uae_is_simplified_tax_invoice", "Simplified Tax Invoice", "Check", "uae_is_export", read_only=1),
		_field("uae_is_margin_scheme", "Profit Margin Scheme", "Check", "uae_is_simplified_tax_invoice"),
		_field("uae_is_deemed_supply", "Deemed Supply", "Check", "uae_is_margin_scheme"),
		_field("uae_cb_type_1", "", "Column Break", "uae_is_deemed_supply"),
		_field("uae_is_free_zone_supply", "Supply Involving Free Trade Zone", "Check", "uae_cb_type_1"),
		_field(
			"uae_free_zone_beneficiary_id",
			"Free Zone Beneficiary ID",
			"Data",
			"uae_is_free_zone_supply",
			depends_on="uae_is_free_zone_supply",
			mandatory_depends_on="uae_is_free_zone_supply",
		),
		_field("uae_is_ecommerce_supply", "Supply through E-commerce", "Check", "uae_free_zone_beneficiary_id"),
		_field("uae_cb_type_2", "", "Column Break", "uae_is_ecommerce_supply"),
		_field("uae_is_summary_invoice", "Summary Invoice", "Check", "uae_cb_type_2"),
		_field("uae_is_continuous_supply", "Continuous Supply", "Check", "uae_is_summary_invoice"),
		_field("uae_is_agent_billing", "Disclosed Agent Billing", "Check", "uae_is_continuous_supply"),
		_field(
			"uae_principal_trn",
			"Principal TRN",
			"Data",
			"uae_is_agent_billing",
			depends_on="uae_is_agent_billing",
			mandatory_depends_on="uae_is_agent_billing",
		),
		# Invoice period
		_field(
			"uae_period_section",
			"Invoice Period",
			"Section Break",
			"uae_principal_trn",
			depends_on=has_period,
		),
		_field(
			"uae_invoice_period_start",
			"Invoice Period Start",
			"Date",
			"uae_period_section",
			mandatory_depends_on="uae_is_summary_invoice",
		),
		_field("uae_cb_period_1", "", "Column Break", "uae_invoice_period_start"),
		_field(
			"uae_invoice_period_end",
			"Invoice Period End",
			"Date",
			"uae_cb_period_1",
			mandatory_depends_on="uae_is_summary_invoice",
		),
		_field("uae_cb_period_2", "", "Column Break", "uae_invoice_period_end"),
		_field(
			"uae_billing_frequency",
			"Frequency of Billing",
			"Select",
			"uae_cb_period_2",
			options=BILLING_FREQUENCY_SELECT_OPTIONS,
			allow_on_submit=1,
			mandatory_depends_on="uae_is_summary_invoice",
		),
		# Reverse charge
		_field("uae_rc_section", "Reverse Charge", "Section Break", "uae_billing_frequency"),
		_field("uae_is_reverse_charge", "Reverse Charge Supply", "Check", "uae_rc_section"),
		_field("uae_cb_rc_1", "", "Column Break", "uae_is_reverse_charge"),
		_field(
			"uae_reverse_charge_type",
			"Reverse Charge Type",
			"Select",
			"uae_cb_rc_1",
			options=SALES_REVERSE_CHARGE_TYPE_SELECT_OPTIONS,
			depends_on="uae_is_reverse_charge",
			mandatory_depends_on="uae_is_reverse_charge",
		),
		_field("uae_cb_rc_2", "", "Column Break", "uae_reverse_charge_type"),
		_field(
			"uae_rc_declaration",
			"Recipient Declarations Held",
			"Check",
			"uae_cb_rc_2",
			depends_on="uae_is_reverse_charge",
			mandatory_depends_on="uae_is_reverse_charge",
		),
		# Tourist refund
		_field("uae_tourist_section", "Tourist Refund", "Section Break", "uae_rc_declaration"),
		_field(
			"uae_tourist_refund",
			"Tax Refund provided to Tourists",
			"Currency",
			"uae_tourist_section",
			options="currency",
		),
		_field("uae_cb_tourist_1", "", "Column Break", "uae_tourist_refund"),
		_field(
			"uae_tourist_passport",
			"Tourist Passport No",
			"Data",
			"uae_cb_tourist_1",
			depends_on="uae_tourist_refund",
			mandatory_depends_on="uae_tourist_refund",
		),
		_field("uae_cb_tourist_2", "", "Column Break", "uae_tourist_passport"),
		_field(
			"uae_tourist_departure_date",
			"Tourist Departure Date",
			"Date",
			"uae_cb_tourist_2",
			depends_on="uae_tourist_refund",
			mandatory_depends_on="uae_tourist_refund",
		),
		# Credit note
		_field(
			"uae_credit_note_section",
			"Credit Note",
			"Section Break",
			"uae_tourist_departure_date",
			depends_on="is_return",
		),
		_field("uae_credit_note_reason", "Reason for Credit Note", "Small Text", "uae_credit_note_section"),
		_field("uae_cb_credit_1", "", "Column Break", "uae_credit_note_reason"),
		_field(
			"uae_credit_note_reason_code",
			"Credit Note Reason Code",
			"Select",
			"uae_cb_credit_1",
			options=CREDIT_REASON_SELECT_OPTIONS,
		),
		_field("uae_cb_credit_2", "", "Column Break", "uae_credit_note_reason_code"),
		_field(
			"uae_credit_note_original_value",
			"Value Before This Credit Note",
			"Currency",
			"uae_cb_credit_2",
			options="Company:company:default_currency",
			read_only=1,
		),
	]


def _legal_registration_fields(insert_after):
	return [
		_field(
			"uae_legal_registration_type",
			"Legal Registration Type",
			"Select",
			insert_after,
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
	]


# Company's UAE fields sit on their own tab, shown only for a company in the UAE and emptied on save
# otherwise (overrides/company.py), so a shared bench's other companies never see them.
CUSTOM_FIELDS = {
	"Company": [
		_field(
			"uae_tab",
			"UAE Compliance",
			"Tab Break",
			"dashboard_tab",
			depends_on=f"eval:doc.country=='{UAE}'",
		),
		_field("uae_company_name_in_arabic", "Company Name in Arabic", "Data", "uae_tab"),
		_field(
			"uae_tax_group",
			"Tax Group",
			"Link",
			"uae_company_name_in_arabic",
			options="UAE Tax Group",
			read_only=1,
		),
		_field("uae_trn", "TRN", "Data", "uae_tax_group"),
		_field("uae_tin", "TIN (Peppol)", "Data", "uae_trn"),
		_field("uae_cb_company", "", "Column Break", "uae_tin"),
		*_legal_registration_fields("uae_cb_company"),
	],
	("Customer", "Supplier"): [
		_field("uae_trn", "TRN", "Data", "tax_id"),
		_field("uae_tin", "TIN (Peppol)", "Data", "uae_trn"),
	],
	"Customer": [
		_field("uae_customer_name_in_arabic", "Customer Name in Arabic", "Data", "customer_name"),
		*_legal_registration_fields("uae_tin"),
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
		_field("uae_is_real_estate", "Real Estate", "Check", "uae_exemption_reason_code"),
		_field(
			"uae_einvoice_exclusion",
			"E-Invoice Exclusion",
			"Select",
			"uae_is_real_estate",
			options=EXCLUSION_SELECT_OPTIONS,
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
	"Sales Order": _emirate_tab_fields("party_account_currency"),
	"Delivery Note": _emirate_tab_fields("instructions"),
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
		_field(
			"uae_reconciliation_status",
			"E-Invoice Reconciliation",
			"Select",
			"uae_cash_payment_intended",
			options="\nMatch Found\nIgnored",
			read_only=1,
			no_copy=1,
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
	"Sales Invoice": _sales_invoice_fields(),
}


NON_FIELD_TYPES = ("Tab Break", "Section Break", "Column Break")


def get_value_fieldnames(doctype: str) -> list[str]:
	"""The fields that hold a value among this app's custom fields on a doctype."""
	return [
		field["fieldname"]
		for doctypes, fields in CUSTOM_FIELDS.items()
		if doctype in ([doctypes] if isinstance(doctypes, str) else doctypes)
		for field in fields
		if field["fieldtype"] not in NON_FIELD_TYPES
	]
