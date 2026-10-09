import frappe


class EInvoiceError(frappe.ValidationError):
	"""An invoice cannot be turned into a valid e-invoice."""


class EInvoiceNotSupportedError(EInvoiceError):
	"""The invoice uses something this app cannot yet express in PINT AE."""
