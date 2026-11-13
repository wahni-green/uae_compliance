import frappe

from uae_compliance.uae_compliance.einvoice.test_pipeline import PipelineTestCase
from uae_compliance.uae_compliance.report.uae_e_invoice_status import uae_e_invoice_status


class TestEInvoiceStatus(PipelineTestCase):
	def rows_of(self, doc, **filters):
		filters = {
			"company": self.company,
			"from_date": doc.posting_date,
			"to_date": doc.posting_date,
			**filters,
		}
		_columns, data = uae_e_invoice_status.execute(filters)
		return [row for row in data if row["invoice"] == doc.name]

	def test_a_submitted_invoice_is_listed_with_its_log_status(self):
		doc, _enqueue = self.submit()
		log = self.log_of(doc)

		(row,) = self.rows_of(doc)

		self.assertEqual((row["status"], row["log"]), (log.status, log.name))

	def test_the_status_filter_keeps_only_that_status(self):
		doc, _enqueue = self.submit()

		self.assertEqual(len(self.rows_of(doc, status=self.log_of(doc).status)), 1)
		self.assertEqual(self.rows_of(doc, status="Cleared"), [])

	def test_an_invoice_without_a_log_is_not_sent(self):
		doc, _enqueue = self.submit()
		# A direct delete: the log's own delete is refused during the retention period.
		frappe.db.delete("UAE E-Invoice Log", {"reference_name": doc.name})

		(row,) = self.rows_of(doc, status="Not Sent")

		self.assertEqual(row["status"], "Not Sent")
