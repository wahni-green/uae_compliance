import frappe

from uae_compliance.tests import (
	configure_vat_settings,
	create_submitted_purchase_invoice,
	create_submitted_sales_invoice,
	delete_tax_groups,
	get_unique_test_date,
	make_customer,
	make_item,
	make_uae_company,
)
from uae_compliance.uae_compliance.doctype.uae_vat_return.test_uae_vat_return import (
	VATReturnTestCase,
	_boxes,
)
from uae_compliance.uae_compliance.report.uae_vat_sales_register import uae_vat_sales_register
from uae_compliance.uae_compliance.utils.vat_return.group import (
	get_return_companies,
	get_return_owner,
)


class TestTaxGroupReturn(VATReturnTestCase):
	def setUp(self):
		super().setUp()
		self.b = make_uae_company("_Test UAE Group Member B", "TGB")

		# Tests in a class share one transaction, so groups must not outlive the test that made them.
		self.addCleanup(delete_tax_groups)
		self.output_b, self.input_b = configure_vat_settings(self.b, append=True)
		make_item("_Test Print Item")

		self.group = frappe.get_doc(
			{
				"doctype": "UAE Tax Group",
				"group_name": "_Test Tax Group",
				"representative_member": self.company,
				"members": [{"company": self.company}, {"company": self.b}],
			}
		).insert()

		# Each member is an internal customer and supplier of the other.
		make_customer("_Test Member A Customer")
		make_customer("_Test Member B Customer")
		frappe.db.set_value("Customer", "_Test Member A Customer", "represents_company", self.company)
		frappe.db.set_value("Customer", "_Test Member B Customer", "represents_company", self.b)

	def _sale(self, company, customer, rate=1000):
		return create_submitted_sales_invoice(
			[{"item_code": "_Test Print Item", "rate": rate}],
			customer=customer,
			posting_date=self.date,
			company=company,
		)

	def test_return_covers_every_member(self):
		self._sale(self.company, "_Test UAE Customer", 1000)
		self._sale(self.b, "_Test UAE Customer", 400)

		doc = self.new_return()
		doc.generate_return()
		box = _boxes(doc)["1b"]

		self.assertEqual((box.amount, box.vat_amount), (1400, 70))

	def test_supplies_between_members_are_disregarded(self):
		self._sale(self.company, "_Test UAE Customer", 1000)
		self._sale(self.company, "_Test Member B Customer", 5000)  # to the other member
		self._sale(self.b, "_Test Member A Customer", 700)  # from the other member

		doc = self.new_return()
		doc.generate_return()

		self.assertEqual(_boxes(doc)["1b"].amount, 1000)

	def test_purchases_between_members_are_disregarded(self):
		frappe.get_doc({"doctype": "Supplier", "supplier_name": "_Test Member B Supplier"}).insert()
		frappe.db.set_value("Supplier", "_Test Member B Supplier", "represents_company", self.b)

		create_submitted_purchase_invoice(
			[{"rate": 500}],
			taxes=[(self.input, 5, "Add")],
			posting_date=self.date,
			supplier="_Test Member B Supplier",
		)
		create_submitted_purchase_invoice(
			[{"rate": 200}], taxes=[(self.input_b, 5, "Add")], posting_date=self.date, company=self.b
		)

		doc = self.new_return()
		doc.generate_return()
		box = _boxes(doc)["9"]

		self.assertEqual((box.amount, box.vat_amount), (200, 10))

	def test_a_member_cannot_file_its_own_return(self):
		doc = frappe.get_doc(
			{
				"doctype": "UAE VAT Return",
				"company": self.b,
				"from_date": self.date,
				"to_date": self.date,
			}
		).insert()

		self.assertRaises(frappe.ValidationError, doc.generate_return)

	def test_a_member_with_purchases_needs_an_input_vat_account(self):
		create_submitted_purchase_invoice(
			[{"rate": 200}], taxes=[(self.input_b, 5, "Add")], posting_date=self.date, company=self.b
		)
		settings = frappe.get_doc("UAE Compliance Settings")
		next(row for row in settings.vat_accounts if row.company == self.b).input_vat_account = None
		settings.save()
		frappe.clear_document_cache("UAE Compliance Settings", "UAE Compliance Settings")

		with self.assertRaises(frappe.ValidationError) as ctx:
			self.new_return().generate_return()
		self.assertIn("Input VAT Account", str(ctx.exception))

	def test_a_member_without_purchases_does_not_need_one(self):
		settings = frappe.get_doc("UAE Compliance Settings")
		next(row for row in settings.vat_accounts if row.company == self.b).input_vat_account = None
		settings.save()
		frappe.clear_document_cache("UAE Compliance Settings", "UAE Compliance Settings")
		self._sale(self.b, "_Test UAE Customer", 400)

		doc = self.new_return()
		doc.generate_return()
		self.assertEqual(_boxes(doc)["1b"].amount, 400)

	def test_a_return_generated_before_the_group_changed_is_stale(self):
		self._sale(self.company, "_Test UAE Customer", 1000)
		doc = self.new_return()
		doc.generate_return()
		self.assertEqual(doc.generated_for_companies, ",".join(sorted([self.company, self.b])))

		third = make_uae_company("_Test UAE Group Member C", "TGC")
		configure_vat_settings(third, append=True)
		self.group.reload()
		self.group.append("members", {"company": third})
		self.group.save()

		self.assertRaises(frappe.ValidationError, doc.mark_as_filed)

		doc.save()
		self.assertFalse(doc.boxes)

	def test_a_draft_return_of_a_company_that_joined_as_a_member_cannot_be_filed(self):
		solo = make_uae_company("_Test UAE Solo", "TSO")
		configure_vat_settings(solo, append=True)
		doc = frappe.get_doc(
			{"doctype": "UAE VAT Return", "company": solo, "from_date": self.date, "to_date": self.date}
		).insert()
		doc.generate_return()

		self.group.reload()
		self.group.append("members", {"company": solo})
		self.group.save()

		self.assertRaises(frappe.ValidationError, doc.mark_as_filed)

	def test_bad_debt_between_members_is_refused(self):
		from frappe.utils import add_months

		invoice = self._sale(self.company, "_Test Member B Customer", 1000)
		relief = frappe.get_doc(
			{
				"doctype": "UAE VAT Adjustment",
				"company": self.company,
				"adjustment_type": "Bad Debt Relief",
				"sales_invoice": invoice.name,
				"emirate": "Dubai",
				"posting_date": add_months(self.date, 7),
				"write_off_date": add_months(self.date, 7),
				"customer_notified": 1,
				"notification_date": add_months(self.date, 7),
				"vat_amount": -20,
			}
		)
		self.assertRaises(frappe.ValidationError, relief.insert)

	def test_existing_bad_debt_between_members_is_left_out_of_the_return(self):
		from frappe.utils import add_months

		from uae_compliance.uae_compliance.utils.vat_return.sections.adjustments import get_adjustments

		invoice = self._sale(self.company, "_Test Member B Customer", 1000)
		self.group.delete()  # the relief is claimed before the group exists
		date = add_months(self.date, 7)
		relief = frappe.get_doc(
			{
				"doctype": "UAE VAT Adjustment",
				"company": self.company,
				"adjustment_type": "Bad Debt Relief",
				"sales_invoice": invoice.name,
				"emirate": "Dubai",
				"posting_date": date,
				"write_off_date": date,
				"customer_notified": 1,
				"notification_date": date,
				"vat_amount": -20,
			}
		).insert()
		relief.submit()
		self.assertEqual(get_adjustments([self.company], date, date)["by_emirate"]["1b"], -20)

		frappe.get_doc(
			{
				"doctype": "UAE Tax Group",
				"group_name": "_Test Tax Group Again",
				"representative_member": self.company,
				"members": [{"company": self.company}, {"company": self.b}],
			}
		).insert()

		self.assertEqual(get_adjustments([self.company, self.b], date, date)["by_emirate"]["1b"], 0)

	def test_an_import_adjustment_that_still_has_an_invoice_is_kept(self):
		from frappe.utils import add_months

		from uae_compliance.uae_compliance.utils.vat_return.sections.adjustments import get_adjustments

		invoice = self._sale(self.company, "_Test Member B Customer", 1000)
		date = add_months(self.date, 9)
		adjustment = frappe.get_doc(
			{
				"doctype": "UAE VAT Adjustment",
				"company": self.company,
				"adjustment_type": "Import Adjustment",
				"posting_date": date,
				"amount": 100,
				"vat_amount": 5,
			}
		).insert()
		# A leftover from when the draft was another type.
		frappe.db.set_value("UAE VAT Adjustment", adjustment.name, "sales_invoice", invoice.name)
		frappe.db.set_value("UAE VAT Adjustment", adjustment.name, "docstatus", 1)

		result = get_adjustments([self.company, self.b], date, date)
		self.assertEqual(result["imports"]["vat_amount"], 5)

	def test_switching_the_type_of_a_draft_clears_the_old_invoice(self):
		invoice = self._sale(self.company, "_Test UAE Customer", 1000)
		adjustment = frappe.get_doc(
			{
				"doctype": "UAE VAT Adjustment",
				"company": self.company,
				"adjustment_type": "Import Adjustment",
				"posting_date": self.date,
				"amount": 100,
				"vat_amount": 5,
				"sales_invoice": invoice.name,
			}
		).insert()

		self.assertFalse(adjustment.sales_invoice)

	def test_every_member_needs_vat_accounts(self):
		settings = frappe.get_doc("UAE Compliance Settings")
		settings.vat_accounts = [row for row in settings.vat_accounts if row.company == self.company]
		settings.save()
		frappe.clear_document_cache("UAE Compliance Settings", "UAE Compliance Settings")

		self.assertRaises(frappe.ValidationError, self.new_return().generate_return)

	def test_adjustments_of_every_member_are_included(self):
		adjustment = frappe.get_doc(
			{
				"doctype": "UAE VAT Adjustment",
				"company": self.b,
				"adjustment_type": "Import Adjustment",
				"posting_date": self.date,
				"amount": 100,
				"vat_amount": 5,
			}
		).insert()
		adjustment.submit()

		doc = self.new_return()
		doc.generate_return()

		self.assertEqual(_boxes(doc)["7"].vat_amount, 5)

	def test_a_members_adjustment_cannot_be_dated_in_a_period_the_group_has_filed(self):
		self._sale(self.company, "_Test UAE Customer", 1000)
		doc = self.new_return()
		doc.generate_return()
		doc.mark_as_filed()

		adjustment = frappe.get_doc(
			{
				"doctype": "UAE VAT Adjustment",
				"company": self.b,
				"adjustment_type": "Import Adjustment",
				"posting_date": self.date,
				"amount": 100,
				"vat_amount": 5,
			}
		).insert()
		self.assertRaises(frappe.ValidationError, adjustment.submit)

	def test_register_follows_the_return(self):
		self._sale(self.company, "_Test UAE Customer", 1000)
		self._sale(self.b, "_Test UAE Customer", 400)
		self._sale(self.company, "_Test Member B Customer", 5000)

		_columns, data = uae_vat_sales_register.execute(
			{"company": self.company, "from_date": self.date, "to_date": self.date}
		)

		self.assertEqual(sum(row["amount"] for row in data), 1400)

	def test_company_outside_a_group_covers_only_itself(self):
		self.group.delete()
		self.assertEqual(get_return_companies(self.company), [self.company])
		self.assertEqual(get_return_companies(self.b), [self.b])

	def test_the_return_owner_of_a_member_is_the_representative(self):
		self.assertEqual(get_return_owner(self.b), self.company)
		self.assertEqual(get_return_owner(self.company), self.company)

	def test_representative_covers_the_members(self):
		self.assertEqual(sorted(get_return_companies(self.company)), sorted([self.company, self.b]))
