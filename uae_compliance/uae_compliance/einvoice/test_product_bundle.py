from unittest.mock import patch

import frappe
from lxml import etree

from uae_compliance.tests import make_einvoice_item
from uae_compliance.uae_compliance.einvoice.pint_ae_builder import NAMESPACES, build_xml
from uae_compliance.uae_compliance.einvoice.test_pint_ae import EInvoiceTestCase
from uae_compliance.uae_compliance.einvoice.validators import validate_xml
from uae_compliance.uae_compliance.utils.vat_return import get_invoice_rows

BUNDLE = "_Test Bundle Package"


class TestProductBundle(EInvoiceTestCase):
	"""A Product Bundle is the way to sell a composite supply: one invoice row for the bundle item,
	which carries the VAT category of the principal component (ER Art 4(6))."""

	def setUp(self):
		super().setUp()
		make_einvoice_item("_Test Bundle Licence")
		make_einvoice_item("_Test Bundle Support", "Zero Rated")
		make_einvoice_item(BUNDLE)
		frappe.db.set_value("Item", BUNDLE, "is_stock_item", 0)
		if not frappe.db.exists("Product Bundle", BUNDLE):
			frappe.get_doc(
				{
					"doctype": "Product Bundle",
					"new_item_code": BUNDLE,
					"items": [
						{"item_code": "_Test Bundle Licence", "qty": 1},
						{"item_code": "_Test Bundle Support", "qty": 1},
					],
				}
			).insert()

	def test_a_bundle_is_one_row_with_one_category_and_one_line(self):
		doc = self.invoice([{"item_code": BUNDLE, "rate": 1000}], submit=True)

		self.assertEqual(
			[(row.item_code, row.uae_vat_category) for row in doc.items], [(BUNDLE, "Standard Rated")]
		)
		rows = get_invoice_rows("Sales Invoice", self.company, self.date, self.date)
		self.assertEqual(
			[(row.item_code, row.category, row.base_net_amount) for row in rows],
			[(BUNDLE, "Standard Rated", 1000)],
		)

		xml = build_xml(doc)[0]
		lines = etree.fromstring(xml).xpath("cac:InvoiceLine", namespaces={"cac": NAMESPACES["cac"]})
		self.assertEqual(len(lines), 1)
		self.assertEqual(validate_xml(xml), [])

	def bundle(self):
		return frappe.get_doc("Product Bundle", BUNDLE)

	def test_the_principal_component_must_be_in_the_bundle(self):
		bundle = self.bundle()
		bundle.uae_principal_item = "_Test EInv Service"

		self.assertRaises(frappe.ValidationError, bundle.save)

	def test_a_bundle_item_that_differs_from_its_principal_component_is_warned_about(self):
		frappe.db.set_value("Item", "_Test Bundle Licence", "uae_vat_category", "Standard Rated")
		frappe.db.set_value("Item", BUNDLE, "uae_vat_category", "Zero Rated")
		bundle = self.bundle()
		bundle.uae_principal_item = "_Test Bundle Licence"

		with patch("frappe.msgprint") as msgprint:
			bundle.save()

		self.assertTrue(any("principal component" in str(call) for call in msgprint.call_args_list))

	def test_no_warning_when_the_bundle_item_matches(self):
		frappe.db.set_value("Item", "_Test Bundle Licence", "uae_vat_category", "Standard Rated")
		frappe.db.set_value("Item", BUNDLE, "uae_vat_category", "Standard Rated")
		bundle = self.bundle()
		bundle.uae_principal_item = "_Test Bundle Licence"

		with patch("frappe.msgprint") as msgprint:
			bundle.save()

		msgprint.assert_not_called()

	def test_a_bundle_without_a_principal_component_is_left_alone(self):
		bundle = self.bundle()
		bundle.uae_principal_item = None

		with patch("frappe.msgprint") as msgprint:
			bundle.save()

		msgprint.assert_not_called()
