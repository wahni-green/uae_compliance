import frappe
from frappe.tests.utils import FrappeTestCase

from uae_compliance.uae_compliance.einvoice import pipeline
from uae_compliance.uae_compliance.overrides import purchase_invoice, transaction
from uae_compliance.uae_compliance.utils.company import is_uae_company


def get_foreign_company() -> str:
	company = frappe.db.get_value("Company", {"country": ("!=", "United Arab Emirates")})
	if not company:
		raise frappe.DoesNotExistError("No non-UAE company on this site")

	return company


class TestNonUAECompanyIsUnaffected(FrappeTestCase):
	"""The app shares a bench with non-UAE companies, so each hook leaves their documents alone."""

	def setUp(self):
		self.company = get_foreign_company()
		self.assertFalse(is_uae_company(self.company))

	def _document(self, doctype, **values):
		return frappe.get_doc(
			{
				"doctype": doctype,
				"company": self.company,
				"items": [{"item_code": "_Test Item", "qty": 1, "rate": 100}],
				**values,
			}
		)

	def test_purchase_invoice_is_not_checked(self):
		doc = self._document("Purchase Invoice", supplier="_Test Supplier", reverse_charge_applicable=1)
		# A UAE company would be refused: reverse charge without the VAT rows, and a category is set.
		purchase_invoice.validate(doc)

		self.assertFalse(doc.items[0].get("uae_vat_category"))
		self.assertFalse(doc.get("uae_is_import_of_goods"))
		self.assertFalse(doc.get("uae_is_gcc_supplier"))

	def test_sales_documents_get_no_vat_category(self):
		for doctype in ("Sales Order", "Quotation", "Delivery Note"):
			doc = self._document(doctype)
			transaction.set_vat_category_defaults(doc)
			self.assertFalse(doc.items[0].get("uae_vat_category"), doctype)

	def test_item_tax_template_is_not_checked(self):
		from uae_compliance.uae_compliance.overrides.item_tax_template import validate

		template = frappe.get_doc(
			{
				"doctype": "Item Tax Template",
				"title": "_Test Non UAE Zero",
				"company": self.company,
				"uae_vat_category": "Zero Rated",
				"taxes": [
					{"tax_type": frappe.db.get_value("Account", {"company": self.company}), "tax_rate": 5}
				],
			}
		)
		validate(template)

	def test_party_without_a_trn_is_accepted(self):
		from uae_compliance.uae_compliance.overrides.party import validate_trn_and_tin

		for doctype in ("Customer", "Supplier"):
			doc = frappe.get_doc({"doctype": doctype, "uae_trn": "", "uae_tin": ""})
			validate_trn_and_tin(doc)
			self.assertFalse(doc.uae_trn)
			self.assertFalse(doc.uae_tin)

	def test_no_e_invoice_is_required_or_queued(self):
		doc = self._document("Sales Invoice", customer="_Test Customer", posting_date=frappe.utils.today())

		self.assertIsNone(pipeline.get_setting_if_required(doc))

		before = frappe.db.count(pipeline.LOG)
		pipeline.validate_before_submit(doc)
		pipeline.queue_einvoice(doc)
		self.assertEqual(frappe.db.count(pipeline.LOG), before)

	def test_cancelling_an_invoice_without_a_log_is_not_blocked(self):
		doc = self._document("Sales Invoice", customer="_Test Customer")
		doc.name = "_TEST-NON-UAE-SINV"
		pipeline.guard_cancellation(doc)

	def test_vat_return_is_not_generated(self):
		return_ = frappe.get_doc(
			{
				"doctype": "UAE VAT Return",
				"company": self.company,
				"from_date": "2026-01-01",
				"to_date": "2026-03-31",
			}
		)
		self.assertRaises(frappe.ValidationError, return_.generate_return)


class TestCompanyUAEFields(FrappeTestCase):
	def test_uae_fields_are_emptied_for_a_non_uae_company(self):
		from uae_compliance.uae_compliance.overrides import company

		doc = frappe.get_doc("Company", get_foreign_company())
		for fieldname in company.UAE_FIELDS:
			doc.set(fieldname, "x")

		company.validate(doc)

		for fieldname in company.UAE_FIELDS:
			self.assertFalse(doc.get(fieldname), fieldname)

	def test_transaction_uae_fields_are_emptied_for_a_non_uae_company(self):
		from uae_compliance.uae_compliance.constants.custom_fields import get_value_fieldnames

		for doctype in ("Sales Order", "Delivery Note", "Sales Invoice"):
			doc = frappe.new_doc(doctype)
			doc.company = get_foreign_company()
			fieldnames = get_value_fieldnames(doctype)
			self.assertIn("uae_emirate", fieldnames)
			for fieldname in fieldnames:
				doc.set(fieldname, "x")

			transaction.clear_uae_fields(doc)

			for fieldname in fieldnames:
				self.assertFalse(doc.get(fieldname), f"{doctype}.{fieldname}")
