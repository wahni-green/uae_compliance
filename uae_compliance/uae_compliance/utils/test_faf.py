import csv
import io

import frappe

from uae_compliance.tests import create_submitted_purchase_invoice
from uae_compliance.uae_compliance.doctype.uae_vat_return.test_uae_vat_return import (
	VATReturnTestCase,
)
from uae_compliance.uae_compliance.utils.faf import generate_faf


def _tables(content: str) -> list[list[list[str]]]:
	"""Split FAF output on blank lines into tables of rows."""
	tables, current = [], []
	for row in csv.reader(io.StringIO(content)):
		if row:
			current.append(row)
		elif current:
			tables.append(current)
			current = []
	if current:
		tables.append(current)

	return tables


class TestFAF(VATReturnTestCase):
	def _generate(self):
		return generate_faf(self.company, self.date, self.date)

	def test_four_tables_in_order(self):
		self.sale(rate=1000)
		tables = _tables(self._generate())

		# Company; supplier + totals; customer + totals; general ledger + totals (a blank line only
		# separates the tables, so each listing's totals row stays inside its own table).
		self.assertEqual(tables[0][0][0], "TaxablePersonNameEn")
		self.assertEqual(tables[1][0][0], "SupplierName")
		self.assertEqual(tables[2][0][0], "CustomerName")
		self.assertEqual(tables[3][0][0], "TransactionDate")

	def test_company_information(self):
		frappe.db.set_value("Company", self.company, "uae_trn", "100123456789003")
		header, row = _tables(self._generate())[0]

		values = dict(zip(header, row, strict=True))
		self.assertEqual(values["TaxablePersonNameEn"], self.company)
		self.assertEqual(values["TRN"], "100123456789003")
		self.assertEqual(values["FAFVersion"], "FAFv1.0.0")
		self.assertEqual(values["PeriodStart"], values["PeriodEnd"])
		self.assertRegex(values["PeriodStart"], r"^\d{2}-\d{2}-\d{4}$")

	def test_customer_listing_and_totals(self):
		self.sale(rate=1000, emirate="Dubai")
		self.sale(item="_Test Zero Item", rate=300, vat_rate=0)

		customer = _tables(self._generate())[2]
		header, *lines, totals_header, totals = customer
		rows = [dict(zip(header, line, strict=True)) for line in lines]

		self.assertEqual({row["TaxCode"] for row in rows}, {"SR", "ZR"})
		self.assertEqual(sorted(row["SupplyValueAED"] for row in rows), ["1000.00", "300.00"])
		self.assertEqual(totals_header, ["SupplyTotalAED", "VATTotalAED", "TransactionCountTotal"])
		self.assertEqual(totals, ["1300.00", "50.00", "2"])

	def test_supplier_listing_marks_reverse_charge(self):
		create_submitted_purchase_invoice(
			[{"rate": 100}],
			taxes=[(self.output, 5, "Deduct"), (self.input, 5, "Add")],
			posting_date=self.date,
			uae_is_reverse_charge=1,
			uae_reverse_charge_type="Import of Services",
			uae_permit_no="PERMIT1",
		)
		header, *lines, _totals_header, totals = _tables(self._generate())[1]
		row = dict(zip(header, lines[0], strict=True))

		self.assertEqual(row["TaxCode"], "RC")
		self.assertEqual(row["PermitNo"], "PERMIT1")
		self.assertEqual(totals[2], "1")

	def test_general_ledger_totals_balance(self):
		self.sale(rate=1000)
		_header, *lines, _totals_header, totals = _tables(self._generate())[3]

		self.assertTrue(lines)
		self.assertEqual(totals[0], totals[1])
		self.assertEqual(totals[3], "AED")

	def test_commas_in_names_are_removed(self):
		frappe.db.set_value("Customer", "_Test UAE Customer", "customer_name", "Acme, Trading LLC")
		self.sale(rate=1000)
		content = self._generate()

		self.assertNotIn("Acme, Trading", content)
		header, line, _totals_header, _totals = _tables(content)[2]
		self.assertEqual(len(line), len(header))
		self.assertEqual(line[0], "Acme  Trading LLC")

	def test_download_faf_requires_read_permission(self):
		doc = self.new_return()
		frappe.set_user("Guest")
		self.addCleanup(frappe.set_user, "Administrator")
		self.assertRaises(frappe.PermissionError, doc.download_faf)
