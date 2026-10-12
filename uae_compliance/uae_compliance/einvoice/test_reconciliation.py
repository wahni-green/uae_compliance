import itertools

import frappe
from frappe.tests.utils import FrappeTestCase

from uae_compliance.tests import (
	configure_vat_settings,
	create_submitted_purchase_invoice,
	get_uae_test_company,
)
from uae_compliance.uae_compliance.einvoice import reconciliation as recon
from uae_compliance.uae_compliance.report.uae_purchase_reconciliation import (
	uae_purchase_reconciliation as report,
)

_suppliers = itertools.count(1)


class TestComparing(FrappeTestCase):
	def test_bill_numbers_are_normalized(self):
		self.assertEqual(recon.normalize_bill_no(" inv/0012 "), "INV0012")
		self.assertEqual(recon.normalize_bill_no("0012"), "12")
		self.assertEqual(recon.normalize_bill_no("000"), "000")
		self.assertTrue(recon.bill_numbers_match("INV/0012", "inv-0012"))
		self.assertFalse(recon.bill_numbers_match("", ""))

	def test_close_bill_numbers(self):
		self.assertTrue(recon.bill_numbers_are_close("INV-12", "2026/INV-12"))
		self.assertTrue(recon.bill_numbers_are_close("INVOICE12345", "INVOICE12346"))
		self.assertFalse(recon.bill_numbers_are_close("A1", "B2"))
		self.assertFalse(recon.bill_numbers_are_close("12", "ABC12"))
		self.assertFalse(recon.bill_numbers_are_close(None, "12"))

	def test_amounts_are_compared_together(self):
		received = {"taxable": 1000, "tax": 50}
		self.assertTrue(recon.amounts_are_close(received, {"taxable": 1000.5, "tax": 50.5}))
		self.assertFalse(recon.amounts_are_close(received, {"taxable": 1000.6, "tax": 50.6}))
		self.assertTrue(recon.amounts_are_close({"taxable": -1000, "tax": -50}, {"taxable": 1000, "tax": 50}))

	def test_dates(self):
		self.assertTrue(recon.dates_are_close("2026-10-01", "2026-10-11"))
		self.assertFalse(recon.dates_are_close("2026-10-01", "2026-10-12"))
		self.assertFalse(recon.dates_are_close(None, "2026-10-12"))


class ReconciliationTestCase(FrappeTestCase):
	def setUp(self):
		self.company = get_uae_test_company()
		self.output, self.input = configure_vat_settings(self.company)
		self.supplier = f"_Test Recon Supplier {next(_suppliers)}"
		self.today = frappe.utils.today()

	def invoice(self, bill_no="INV/0012", rate=1000, vat=True, **kwargs):
		taxes = [(self.input, 5, "Add")] if vat else []
		return create_submitted_purchase_invoice(
			[{"rate": rate}],
			taxes=taxes,
			supplier=self.supplier,
			bill_no=bill_no,
			bill_date=kwargs.pop("bill_date", self.today),
			posting_date=kwargs.pop("posting_date", self.today),
			**kwargs,
		)

	def received(self, number="INV-0012", taxable=1000, tax=50, date=None, kind="Invoice", **kwargs):
		return frappe.get_doc(
			{
				"doctype": recon.LOG,
				"company": self.company,
				"direction": "Inbound",
				"status": "Delivered",
				"document_number": number,
				"document_type": kind,
				"document_date": date or self.today,
				"party_name": self.supplier,
				"supplier": self.supplier,
				"currency": "AED",
				"taxable_amount": taxable,
				"tax_amount": tax,
				"total_amount": taxable + tax,
				**kwargs,
			}
		).insert(ignore_permissions=True)

	def run_matching(self):
		return recon.run_matching(self.company, frappe.utils.add_days(self.today, -5), self.today)

	def rows(self):
		filters = frappe._dict(
			company=self.company, from_date=frappe.utils.add_days(self.today, -5), to_date=self.today
		)
		return [r for r in report.get_data(filters) if self.supplier in (r.get("supplier") or "")]

	def log_of(self, log):
		return frappe.get_doc(recon.LOG, log.name)


class TestMatching(ReconciliationTestCase):
	def test_an_exact_match_is_linked(self):
		book, log = self.invoice(), self.received()
		self.run_matching()

		log = self.log_of(log)
		self.assertEqual((log.match_status, log.link_name), ("Exact Match", book.name))
		self.assertEqual(
			frappe.db.get_value("Purchase Invoice", book.name, "uae_reconciliation_status"), "Match Found"
		)

	def test_a_different_way_of_writing_the_number_is_a_suggestion(self):
		self.invoice(bill_no="2026/INV-0012")
		log = self.received(number="INV-0012")
		self.run_matching()

		self.assertEqual(self.log_of(log).match_status, "Suggested Match")

	def test_a_date_far_apart_with_the_same_number_is_a_suggestion(self):
		book = self.invoice(bill_date=frappe.utils.add_days(self.today, -3))
		log = self.received(number="INV/0012", date=self.today)
		self.run_matching()

		log = self.log_of(log)
		self.assertEqual((log.match_status, log.link_name), ("Suggested Match", book.name))

	def test_amounts_beyond_the_tolerance_are_not_stored_as_a_match(self):
		self.invoice()
		log = self.received(taxable=1002, tax=50.1)
		self.run_matching()

		self.assertFalse(self.log_of(log).link_name)
		self.assertIn("Mismatch", [r["status"] for r in self.rows()])

	def test_small_differences_together_are_beyond_the_tolerance(self):
		self.invoice()
		log = self.received(taxable=1000.6, tax=50.6)
		self.run_matching()

		self.assertFalse(self.log_of(log).link_name)

	def test_a_credit_note_does_not_match_an_invoice(self):
		self.invoice()
		log = self.received(kind="Credit Note")
		self.run_matching()

		self.assertFalse(self.log_of(log).link_name)

	def test_each_document_is_claimed_once(self):
		self.invoice()
		first, second = self.received(), self.received()
		self.run_matching()

		linked = [self.log_of(first).link_name, self.log_of(second).link_name]
		self.assertEqual(len([name for name in linked if name]), 1)

	def test_an_invalid_e_invoice_is_not_matched_by_itself(self):
		self.invoice()
		log = self.received(status="Invalid", errors="Not addressed to this company")
		self.run_matching()

		self.assertFalse(self.log_of(log).link_name)

	def test_another_supplier_is_not_matched(self):
		self.invoice()
		other = frappe.get_doc({"doctype": "Supplier", "supplier_name": f"{self.supplier} Other"}).insert()
		log = self.received(supplier=other.name)
		self.run_matching()

		self.assertFalse(self.log_of(log).link_name)

	def test_a_reverse_charge_purchase_is_not_expected_to_have_an_e_invoice(self):
		book = self.invoice()
		frappe.db.set_value("Purchase Invoice", book.name, "uae_is_reverse_charge", 1)
		self.assertNotIn(
			book.name, [b["name"] for b in recon.get_books(self.company, self.today, self.today)]
		)


class TestActions(ReconciliationTestCase):
	def test_manual_link_releases_what_was_linked(self):
		first, second = self.invoice(), self.invoice(bill_no="OTHER")
		log = self.received()
		self.run_matching()
		self.assertEqual(self.log_of(log).link_name, first.name)

		recon.link_documents(log.name, second.name)
		self.assertEqual(
			(self.log_of(log).link_name, self.log_of(log).match_status), (second.name, "Manual Match")
		)
		self.assertFalse(frappe.db.get_value("Purchase Invoice", first.name, "uae_reconciliation_status"))

	def test_unlink_makes_both_unmatched(self):
		book, log = self.invoice(), self.received()
		self.run_matching()
		recon.unlink_documents([log.name])

		self.assertFalse(self.log_of(log).link_name)
		self.assertFalse(frappe.db.get_value("Purchase Invoice", book.name, "uae_reconciliation_status"))

	def test_ignoring_and_restoring(self):
		book, log = self.invoice(), self.received(number="XYZ", taxable=5000, tax=250)
		recon.ignore_documents([log.name], [book.name])
		self.assertEqual(self.log_of(log).recon_action, "Ignore")
		self.assertEqual(
			frappe.db.get_value("Purchase Invoice", book.name, "uae_reconciliation_status"), "Ignored"
		)
		self.assertEqual({r["status"] for r in self.rows()}, set())

		recon.restore_documents([log.name], [book.name])
		self.assertFalse(self.log_of(log).recon_action)
		self.assertEqual({r["status"] for r in self.rows()}, {"Only Received", "Only in Books"})

	def test_a_linked_document_cannot_be_ignored(self):
		book, log = self.invoice(), self.received()
		self.run_matching()

		self.assertRaises(frappe.ValidationError, recon.ignore_documents, [log.name], [])
		self.assertRaises(frappe.ValidationError, recon.ignore_documents, [], [book.name])

	def test_cancelling_the_invoice_releases_the_e_invoice(self):
		book, log = self.invoice(), self.received()
		self.run_matching()
		book.cancel()

		self.assertFalse(self.log_of(log).link_name)
		self.assertFalse(frappe.db.get_value("Purchase Invoice", book.name, "uae_reconciliation_status"))

	def test_an_ignored_e_invoice_is_not_matched(self):
		self.invoice()
		log = self.received()
		recon.ignore_documents([log.name], [])
		self.run_matching()

		self.assertFalse(self.log_of(log).link_name)

	def test_a_non_uae_company_is_refused(self):
		india = frappe.db.get_value("Company", {"country": "India"})
		self.assertRaises(frappe.ValidationError, recon.run_matching, india, self.today, self.today)


class TestReport(ReconciliationTestCase):
	def test_rows_by_status(self):
		matched_book, matched_log = self.invoice(), self.received()
		self.run_matching()

		self.received(number="ONLYREC-1", taxable=7000, tax=350)
		self.invoice(bill_no="ONLYBOOK-1", rate=3000)

		by_status = {}
		for row in self.rows():
			by_status.setdefault(row["status"], []).append(row)

		self.assertEqual(by_status["Exact Match"][0]["invoice"], matched_book.name)
		self.assertEqual(by_status["Exact Match"][0]["received"], matched_log.name)
		self.assertEqual(len(by_status["Only Received"]), 1)
		self.assertEqual(len(by_status["Only in Books"]), 1)

	def test_differences_are_named(self):
		self.invoice()
		self.received(taxable=1000, tax=50.5, date=frappe.utils.add_days(self.today, -2))
		self.run_matching()

		row = next(r for r in self.rows() if r["status"] == "Suggested Match")
		self.assertIn("Date", row["differences"])
		self.assertIn("VAT", row["differences"])
