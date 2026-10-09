"""Migration from ERPNext's built-in UAE localization to this app's own model.

Everything here is idempotent and non-destructive: ERPNext's fields and records are only read, never
changed or deleted. Submitted documents' item rows are never modified; only new mirror fields on
document headers are filled (no financial data changes). Ambiguous cases are logged for manual
review, not guessed.
"""

import re

import frappe

from uae_compliance.uae_compliance.constants import DEFAULT_TRN_RE

# ERPNext's UAE Item Tax Templates (setup wizard country_wise_tax.json) start with these prefixes;
# the company abbreviation suffix (" - ABBR") varies.
TEMPLATE_PREFIX_CATEGORY = (
	("UAE VAT Zero", "Zero Rated"),
	("UAE VAT Exempted", "Exempt"),
	("UAE VAT 5%", "Standard Rated"),
)

ITEM_ROW_PARENTS = {
	"Sales Order Item": "Sales Order",
	"Quotation Item": "Quotation",
	"Delivery Note Item": "Delivery Note",
	"Sales Invoice Item": "Sales Invoice",
	"Purchase Invoice Item": "Purchase Invoice",
}


def _log(title: str, message: str) -> None:
	frappe.log_error(title=f"UAE Compliance migration: {title}", message=message)


def migrate_item_vat_flags(dry_run: bool = False) -> dict:
	"""ERPNext Item.is_zero_rated / is_exempt -> Item.uae_vat_category, plus the matching Item Tax
	Templates, plus the item rows of *draft* documents. Items with both flags set are skipped and
	logged for manual review. Never overwrites a category that is already set."""
	result = {"items": 0, "conflicts": [], "templates": 0, "draft_rows": 0}

	if frappe.db.has_column("Item", "is_zero_rated") and frappe.db.has_column("Item", "is_exempt"):
		items = frappe.get_all(
			"Item",
			filters=[["uae_vat_category", "in", ["", None]]],
			or_filters={"is_zero_rated": 1, "is_exempt": 1},
			fields=["name", "is_zero_rated", "is_exempt"],
		)
		for item in items:
			if item.is_zero_rated and item.is_exempt:
				result["conflicts"].append(item.name)
				continue

			result["items"] += 1
			if not dry_run:
				category = "Zero Rated" if item.is_zero_rated else "Exempt"
				frappe.db.set_value("Item", item.name, "uae_vat_category", category, update_modified=False)

	if result["conflicts"] and not dry_run:
		_log(
			"items with both is_zero_rated and is_exempt",
			"Set the VAT Category manually on: " + ", ".join(result["conflicts"]),
		)

	for template in frappe.get_all(
		"Item Tax Template",
		filters=[["uae_vat_category", "in", ["", None]]],
		fields=["name", "title"],
	):
		for prefix, category in TEMPLATE_PREFIX_CATEGORY:
			if (template.title or template.name).startswith(prefix):
				result["templates"] += 1
				if not dry_run:
					frappe.db.set_value(
						"Item Tax Template",
						template.name,
						"uae_vat_category",
						category,
						update_modified=False,
					)
				break

	if not dry_run:
		result["draft_rows"] = backfill_draft_item_rows()

	return result


def backfill_draft_item_rows() -> int:
	"""Copy the Item's VAT Category to blank item rows of draft (docstatus 0) documents only."""
	total = 0
	for child, parent in ITEM_ROW_PARENTS.items():
		total += _count_and_execute(
			f"""
			UPDATE `tab{child}` c
			JOIN `tab{parent}` p ON p.name = c.parent
			JOIN `tabItem` i ON i.name = c.item_code
			SET c.uae_vat_category = i.uae_vat_category
			WHERE p.docstatus = 0
				AND c.parenttype = %(parent)s
				AND IFNULL(c.uae_vat_category, '') = ''
				AND IFNULL(i.uae_vat_category, '') != ''
			""",
			{"parent": parent},
		)

	return total


def _count_and_execute(query: str, values: dict) -> int:
	frappe.db.sql(query, values)
	return frappe.db.sql("SELECT ROW_COUNT()")[0][0] or 0


def migrate_vat_settings() -> dict:
	"""ERPNext UAE VAT Settings (one per company, rows of single `account`) -> UAE Compliance
	Settings output/input accounts. Liability accounts become Output, Asset accounts Input; if a
	company has more than one account of a kind it is ambiguous and is logged, not guessed."""
	result = {"migrated": [], "ambiguous": []}
	if not frappe.db.table_exists("UAE VAT Settings"):
		return result

	settings = frappe.get_doc("UAE Compliance Settings")
	existing = {row.company for row in settings.vat_accounts}

	for legacy in frappe.get_all("UAE VAT Settings", pluck="name"):
		company = legacy
		if company in existing or not frappe.db.exists("Company", company):
			continue

		output, input_ = [], []
		for row in frappe.get_all("UAE VAT Account", filters={"parent": legacy}, pluck="account"):
			root_type = frappe.db.get_value("Account", row, "root_type")
			(output if root_type == "Liability" else input_ if root_type == "Asset" else []).append(row)

		if len(output) != 1 or len(input_) > 1:
			result["ambiguous"].append(company)
			continue

		settings.append(
			"vat_accounts",
			{
				"company": company,
				"output_vat_account": output[0],
				"input_vat_account": input_[0] if input_ else None,
			},
		)
		result["migrated"].append(company)

	if result["migrated"]:
		settings.flags.ignore_permissions = True
		settings.save()

	if result["ambiguous"]:
		_log(
			"UAE VAT Settings need manual mapping",
			"Set Output/Input VAT accounts in UAE Compliance Settings for: " + ", ".join(result["ambiguous"]),
		)

	return result


def migrate_master_data() -> dict:
	"""TRN, Arabic names and emirate from ERPNext's fields into this app's fields (only where the
	new field is blank)."""
	counts = {}

	counts["company_trn"] = _copy_trn("Company")
	counts["customer_trn"] = _copy_trn("Customer")
	counts["supplier_trn"] = _copy_trn("Supplier")

	for doctype, old, new in (
		("Customer", "customer_name_in_arabic", "uae_customer_name_in_arabic"),
		("Supplier", "supplier_name_in_arabic", "uae_supplier_name_in_arabic"),
		("Address", "emirate", "uae_emirate"),
		("Sales Invoice", "vat_emirate", "uae_emirate"),
		("Sales Order", "vat_emirate", "uae_emirate"),
		("Delivery Note", "vat_emirate", "uae_emirate"),
		("Sales Invoice", "tourist_tax_return", "uae_tourist_refund"),
	):
		counts[f"{doctype}.{new}"] = _copy_field(doctype, old, new)

	return counts


def _copy_trn(doctype: str) -> int:
	count = 0
	rows = frappe.get_all(
		doctype,
		filters=[["uae_trn", "in", ["", None]]],
		fields=["name", "tax_id"],
	)
	for row in rows:
		tax_id = re.sub(r"[\s-]", "", row.tax_id or "")
		if tax_id and DEFAULT_TRN_RE.match(tax_id):
			frappe.db.set_value(doctype, row.name, "uae_trn", tax_id, update_modified=False)
			count += 1

	return count


def _copy_field(doctype: str, old: str, new: str) -> int:
	if not frappe.db.has_column(doctype, old):
		return 0

	frappe.db.sql(
		f"""
		UPDATE `tab{doctype}`
		SET `{new}` = `{old}`
		WHERE IFNULL(`{old}`, '') NOT IN ('', '0', '0.0', '0.00')
			AND IFNULL(`{new}`, '') IN ('', '0', '0.0', '0.00')
		"""
	)
	return frappe.db.sql("SELECT ROW_COUNT()")[0][0] or 0


def migrate_purchase_reverse_charge() -> int:
	"""Purchase Invoice.reverse_charge = 'Y' -> uae_is_reverse_charge = 1 (header flag only)."""
	if not frappe.db.has_column("Purchase Invoice", "reverse_charge"):
		return 0

	frappe.db.sql(
		"""
		UPDATE `tabPurchase Invoice`
		SET uae_is_reverse_charge = 1
		WHERE reverse_charge = 'Y' AND IFNULL(uae_is_reverse_charge, 0) = 0
		"""
	)
	return frappe.db.sql("SELECT ROW_COUNT()")[0][0] or 0
