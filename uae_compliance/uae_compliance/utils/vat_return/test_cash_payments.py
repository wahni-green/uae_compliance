import frappe

from uae_compliance.tests import create_submitted_purchase_invoice
from uae_compliance.uae_compliance.doctype.uae_vat_return.test_uae_vat_return import (
	VATReturnTestCase,
	_boxes,
)


class TestCashPaymentLimit(VATReturnTestCase):
	def setUp(self):
		super().setUp()
		self.cash_account = frappe.db.get_value(
			"Account", {"company": self.company, "account_type": "Cash", "is_group": 0}, "name"
		)
		if not frappe.db.exists("Mode of Payment", "Cash"):
			frappe.get_doc({"doctype": "Mode of Payment", "mode_of_payment": "Cash", "type": "Cash"}).insert()

		self.addCleanup(self.set_limit, 0)

	def set_limit(self, amount):
		frappe.db.set_single_value("UAE Compliance Settings", "cash_payment_limit", amount)
		frappe.clear_document_cache("UAE Compliance Settings", "UAE Compliance Settings")

	def purchase(self, rate=5000, **kwargs):
		return create_submitted_purchase_invoice(
			[{"rate": rate}], taxes=[(self.input, 5, "Add")], posting_date=self.date, **kwargs
		)

	def pay_in_cash(self, invoice, mode="Cash"):
		from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

		entry = get_payment_entry("Purchase Invoice", invoice.name)
		entry.mode_of_payment = mode
		entry.paid_from = self.cash_account
		entry.reference_no = "CASH-1"
		entry.reference_date = self.date
		entry.insert()
		entry.submit()
		return entry

	def generate(self):
		doc = self.new_return()
		doc.generate_return()
		return doc

	def recovered(self, doc):
		return _boxes(doc)["9"].vat_amount

	def test_nothing_changes_while_no_limit_is_set(self):
		self.pay_in_cash(self.purchase())

		self.assertEqual(self.recovered(self.generate()), 250)

	def test_input_vat_on_a_large_cash_payment_is_not_recovered(self):
		self.set_limit(1000)
		self.pay_in_cash(self.purchase())

		self.assertEqual(self.recovered(self.generate()), 0)

	def test_a_purchase_paid_in_cash_on_the_invoice_itself(self):
		self.set_limit(1000)
		self.purchase(is_paid=1, mode_of_payment="Cash", cash_bank_account=self.cash_account)

		self.assertEqual(self.recovered(self.generate()), 0)

	def test_a_payment_intended_in_cash_counts_before_it_is_made(self):
		self.set_limit(1000)
		self.purchase(uae_cash_payment_intended=1)

		self.assertEqual(self.recovered(self.generate()), 0)

	def test_an_intended_cash_payment_under_the_limit_is_recovered(self):
		self.set_limit(10000)
		self.purchase(uae_cash_payment_intended=1)

		self.assertEqual(self.recovered(self.generate()), 250)

	def test_a_payment_under_the_limit_is_recovered(self):
		self.set_limit(10000)
		self.pay_in_cash(self.purchase())

		self.assertEqual(self.recovered(self.generate()), 250)

	def test_a_payment_by_bank_is_recovered(self):
		self.set_limit(1000)
		if not frappe.db.exists("Mode of Payment", "Wire Transfer"):
			frappe.get_doc(
				{"doctype": "Mode of Payment", "mode_of_payment": "Wire Transfer", "type": "Bank"}
			).insert()
		self.pay_in_cash(self.purchase(), mode="Wire Transfer")

		self.assertEqual(self.recovered(self.generate()), 250)

	def test_the_value_of_the_supply_counts_not_the_cash_part(self):
		from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

		self.set_limit(1000)
		invoice = self.purchase()
		entry = get_payment_entry("Purchase Invoice", invoice.name)
		entry.mode_of_payment = "Cash"
		entry.paid_from = self.cash_account
		entry.paid_amount = entry.received_amount = 100
		entry.references[0].allocated_amount = 100
		entry.reference_no = "CASH-2"
		entry.reference_date = self.date
		entry.insert()
		entry.submit()

		self.assertEqual(self.recovered(self.generate()), 0)

	def test_a_cash_payment_after_generating_blocks_filing(self):
		self.set_limit(1000)
		invoice = self.purchase()
		doc = self.generate()
		self.assertEqual(self.recovered(doc), 250)

		self.pay_in_cash(invoice)

		self.assertRaises(frappe.ValidationError, doc.mark_as_filed)

	def test_the_invoice_warns_when_it_is_paid_in_cash_above_the_limit(self):
		from unittest.mock import patch

		self.set_limit(1000)
		with patch("frappe.msgprint") as msgprint:
			self.purchase(is_paid=1, mode_of_payment="Cash", cash_bank_account=self.cash_account)

		self.assertTrue(any("cash" in str(call).lower() for call in msgprint.call_args_list))

	def test_no_warning_without_a_limit(self):
		from unittest.mock import patch

		with patch("frappe.msgprint") as msgprint:
			self.purchase(is_paid=1, mode_of_payment="Cash", cash_bank_account=self.cash_account)

		self.assertFalse(any("cash payment limit" in str(call) for call in msgprint.call_args_list))

	def test_a_credit_note_keeps_the_original_s_input_vat_out(self):
		from erpnext.controllers.sales_and_purchase_return import make_return_doc

		self.set_limit(1000)
		invoice = self.purchase()
		self.pay_in_cash(invoice)
		credit = make_return_doc("Purchase Invoice", invoice.name)
		credit.posting_date = self.date
		credit.set_posting_time = 1
		credit.insert()
		credit.submit()

		# Neither the purchase nor its return counts: the return must not give back VAT never claimed.
		self.assertEqual(self.recovered(self.generate()), 0)

	def test_a_credit_note_of_a_purchase_that_was_not_blocked_is_unchanged(self):
		from erpnext.controllers.sales_and_purchase_return import make_return_doc

		self.set_limit(10000)
		invoice = self.purchase()
		self.pay_in_cash(invoice)
		credit = make_return_doc("Purchase Invoice", invoice.name)
		credit.posting_date = self.date
		credit.set_posting_time = 1
		credit.insert()
		credit.submit()

		self.assertEqual(self.recovered(self.generate()), 0)

	def test_the_value_is_compared_in_the_currency_of_the_limit(self):
		from unittest.mock import patch

		from uae_compliance.uae_compliance.utils.vat_return.cash_payments import exceeds_cash_limit

		invoice = {"base_grand_total": 5000, "company": self.company, "posting_date": self.date}
		with (
			patch("frappe.get_cached_value", return_value="USD"),
			patch("erpnext.setup.utils.get_exchange_rate", return_value=3.6725),
		):
			# USD 5,000 is AED 18,362.5.
			self.assertTrue(exceeds_cash_limit(invoice, 10000, self.company))
			self.assertFalse(exceeds_cash_limit(invoice, 20000, self.company))

		self.assertFalse(exceeds_cash_limit(invoice, 10000, self.company))
