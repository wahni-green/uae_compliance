from uae_compliance.uae_compliance.einvoice.pipeline import extend_retention_for_item


def on_update(doc, method=None):
	"""Ticking Real Estate extends the retention of the e-invoices already issued for the item."""
	if doc.get("uae_is_real_estate") and doc.has_value_changed("uae_is_real_estate"):
		extend_retention_for_item(doc.name)
