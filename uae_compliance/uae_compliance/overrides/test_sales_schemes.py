from unittest.mock import patch

import frappe

from uae_compliance.tests import create_submitted_sales_invoice, make_item, make_sales_invoice
from uae_compliance.uae_compliance.doctype.uae_vat_return.test_uae_vat_return import (
	VATReturnTestCase,
	_boxes,
)
from uae_compliance.uae_compliance.overrides.sales_schemes import (
	get_expected_excise,
	get_expected_margin_vat,
	warn_if_excise_missing,
)
from uae_compliance.uae_compliance.report.uae_vat_sales_register import uae_vat_sales_register
from uae_compliance.uae_compliance.setup import create_excise_rates


class TestMarginScheme(VATReturnTestCase):
	def _margin_kwargs(self, net, cost, vat):
		taxes = (
			[{"charge_type": "Actual", "account_head": self.output, "description": "VAT", "tax_amount": vat}]
			if vat
			else []
		)
		make_item("_Test Margin Item")
		return {
			"rows": [{"item_code": "_Test Margin Item", "rate": net, "uae_margin_purchase_price": cost}],
			"customer": "_Test UAE Customer",
			"posting_date": self.date,
			"taxes": taxes,
			"uae_is_margin_scheme": 1,
		}

	def _draft(self, net=1000, cost=600, vat=20):
		"""An unsaved margin invoice."""
		kwargs = self._margin_kwargs(net, cost, vat)
		return make_sales_invoice(kwargs.pop("rows"), **kwargs)

	def _submitted(self, net=1000, cost=600, vat=20):
		kwargs = self._margin_kwargs(net, cost, vat)
		return create_submitted_sales_invoice(kwargs.pop("rows"), **kwargs)

	def test_vat_is_the_standard_rate_of_the_margin(self):
		invoice = self._draft()
		invoice.calculate_taxes_and_totals()
		self.assertEqual(get_expected_margin_vat(invoice), 20)
		invoice.insert()

	def test_wrong_vat_is_rejected(self):
		invoice = self._draft(vat=50)
		self.assertRaises(frappe.ValidationError, invoice.insert)

	def test_a_row_sold_at_a_loss_owes_nothing(self):
		invoice = self._draft(net=500, cost=600, vat=0)
		invoice.calculate_taxes_and_totals()
		self.assertEqual(get_expected_margin_vat(invoice), 0)
		invoice.insert()

	def test_purchase_price_is_required(self):
		invoice = self._draft(cost=0)
		self.assertRaises(frappe.ValidationError, invoice.insert)

	def test_only_standard_rated_rows_qualify(self):
		make_item("_Test Margin Zero", "Zero Rated")
		invoice = make_sales_invoice(
			[
				{
					"item_code": "_Test Margin Zero",
					"rate": 1000,
					"uae_margin_purchase_price": 600,
					"vat_rate": 0,
				}
			],
			customer="_Test UAE Customer",
			posting_date=self.date,
			uae_is_margin_scheme=1,
		)
		self.assertRaises(frappe.ValidationError, invoice.insert)

	def test_return_reports_the_full_sales_value_and_the_purchase_price(self):
		self._submitted()
		doc = self.new_return()
		doc.generate_return()
		boxes = _boxes(doc)

		# Box 1: price including the VAT (1000 + 20) and the VAT on the margin; box 9: purchase price.
		self.assertEqual((boxes["1b"].amount, boxes["1b"].vat_amount), (1020, 20))
		self.assertEqual((boxes["9"].amount, boxes["9"].vat_amount), (600, 0))
		self.assertEqual(doc.profit_margin_scheme_applied, 1)
		self.assertEqual(doc.total_due_tax, 20)

	def test_register_amount_matches_the_return(self):
		self._submitted()
		_columns, data = uae_vat_sales_register.execute(
			{"company": self.company, "from_date": self.date, "to_date": self.date}
		)
		self.assertEqual((data[0]["amount"], data[0]["vat_amount"]), (1020, 20))

	def test_return_without_margin_sales_leaves_the_flag_alone(self):
		self.sale(rate=1000)
		doc = self.new_return()
		doc.generate_return()
		self.assertEqual(doc.profit_margin_scheme_applied, 0)

	def test_invoice_shows_no_tax_amount(self):
		invoice = self._submitted()
		html = frappe.get_print("Sales Invoice", invoice.name, print_format="UAE Tax Invoice")

		self.assertIn("Profit Margin Scheme", html)
		self.assertIn("Total Payable", html)
		self.assertNotIn("Total VAT", html)
		self.assertNotIn("VAT %", html)


class TestTouristRefund(VATReturnTestCase):
	def _invoice(self, rate=1000, refund=20, item="_Test Print Item", **kwargs):
		row = {"item_code": item, "rate": rate}
		if item == "_Test Zero Item":
			row["vat_rate"] = 0
		make_item("_Test Print Item")
		return make_sales_invoice(
			[row],
			customer="_Test UAE Customer",
			posting_date=self.date,
			uae_tourist_refund=refund,
			**kwargs,
		)

	def test_valid_refund(self):
		self._invoice().insert()

	def test_refund_cannot_exceed_the_vat_charged(self):
		self.assertRaises(frappe.ValidationError, self._invoice(refund=51).insert)

	def test_purchase_must_reach_the_minimum(self):
		self.assertRaises(frappe.ValidationError, self._invoice(rate=200, refund=5).insert)

	def test_refund_is_capped(self):
		self.assertRaises(frappe.ValidationError, self._invoice(rate=1_000_000, refund=36_000).insert)
		self._invoice(rate=1_000_000, refund=35_000).insert()

	def test_needs_a_standard_rated_row(self):
		self.assertRaises(frappe.ValidationError, self._invoice(item="_Test Zero Item", refund=10).insert)

	def test_negative_refund_is_rejected(self):
		self.assertRaises(frappe.ValidationError, self._invoice(refund=-5).insert)


class TestExcise(VATReturnTestCase):
	def setUp(self):
		super().setUp()
		create_excise_rates()
		self.accounts = frappe.db.get_value(
			"Account", {"company": self.company, "account_type": "Tax", "is_group": 0}, "name"
		)

	def _item(self, code, category, litres=None):
		item = make_item(code)
		frappe.db.set_value(
			"Item",
			item.name,
			{"uae_excise_category": category, "uae_excise_volume_litres": litres or 0},
		)
		frappe.clear_document_cache("Item", item.name)
		return item

	def _invoice(self, item, qty=1, rate=1000):
		doc = make_sales_invoice(
			[{"item_code": item.name, "qty": qty, "rate": rate}],
			customer="_Test UAE Customer",
			posting_date=self.date,
		)
		doc.calculate_taxes_and_totals()
		return doc

	def test_percentage_excise_is_a_share_of_the_net_amount(self):
		item = self._item("_Test Cigarettes", "Tobacco and Tobacco Products")
		self.assertEqual(get_expected_excise(self._invoice(item)), 1000)

	def test_per_litre_excise_uses_the_volume(self):
		item = self._item("_Test Cola", "Sweetened Drinks (8 g or more sugar per 100 ml)", litres=1.5)
		invoice = self._invoice(item, qty=10, rate=5)
		self.assertAlmostEqual(get_expected_excise(invoice), 10 * 1.5 * 1.09)

	def test_goods_without_a_category_owe_none(self):
		item = make_item("_Test Plain Goods")
		self.assertEqual(get_expected_excise(self._invoice(item)), 0)

	def test_warns_when_no_excise_account_is_configured(self):
		item = self._item("_Test Vape", "E-Cigarette Liquids")
		with patch("uae_compliance.uae_compliance.overrides.sales_schemes.frappe.msgprint") as msg:
			warn_if_excise_missing(self._invoice(item))

		self.assertTrue(any("Excise Tax Account" in str(call) for call in msg.call_args_list))

	def test_warns_when_the_excise_charged_differs(self):
		item = self._item("_Test Vape", "E-Cigarette Liquids")
		self.addCleanup(self._clear_excise_account)
		settings = frappe.get_doc("UAE Compliance Settings")
		settings.vat_accounts[0].excise_tax_account = self.accounts
		settings.save()
		frappe.clear_document_cache("UAE Compliance Settings", "UAE Compliance Settings")

		invoice = self._invoice(item)
		invoice.append(
			"taxes",
			{
				"charge_type": "Actual",
				"account_head": self.accounts,
				"description": "Excise",
				"tax_amount": 400,
				"base_tax_amount": 400,
			},
		)
		with patch("uae_compliance.uae_compliance.overrides.sales_schemes.frappe.msgprint") as msg:
			warn_if_excise_missing(invoice)
		self.assertTrue(
			any("1000.0 is expected" in str(call) or "expected" in str(call) for call in msg.call_args_list)
		)

		invoice.taxes[-1].base_tax_amount = 1000
		with patch("uae_compliance.uae_compliance.overrides.sales_schemes.frappe.msgprint") as msg:
			warn_if_excise_missing(invoice)
		msg.assert_not_called()

	def _clear_excise_account(self):
		frappe.clear_document_cache("UAE Compliance Settings", "UAE Compliance Settings")

	def test_does_not_warn_without_excise_goods(self):
		item = make_item("_Test Plain Goods")
		with patch("uae_compliance.uae_compliance.overrides.sales_schemes.frappe.msgprint") as msg:
			warn_if_excise_missing(self._invoice(item))

		msg.assert_not_called()
