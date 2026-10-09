import re

import frappe
from frappe import _

from uae_compliance.uae_compliance.constants import (
	DEFAULT_TIN_PATTERN,
	DEFAULT_TRN_PATTERN,
)


def _get_pattern(fieldname: str, default: str) -> re.Pattern:
	try:
		pattern = frappe.get_cached_doc("UAE Compliance Settings").get(fieldname) or default
	except Exception:
		# Settings table not available yet (e.g. during install/migrate): fall back to the default.
		pattern = default

	try:
		return re.compile(pattern)
	except re.error:
		return re.compile(default)


def _normalize(value: str) -> str:
	return re.sub(r"[\s-]", "", value)


def validate_trn(trn: str | None, label: str = "TRN") -> str | None:
	"""Normalize (strip spaces and hyphens) and validate a TRN against the configurable pattern in
	UAE Compliance Settings. Returns falsy input unchanged: TRN is optional on Company, Customer
	and Supplier. No checksum is applied since the FTA publishes none."""
	return _validate(trn, label, "trn_pattern", DEFAULT_TRN_PATTERN, "15-digit TRN, e.g. 100123456789003")


def validate_tin(tin: str | None, label: str = "TIN") -> str | None:
	return _validate(tin, label, "tin_pattern", DEFAULT_TIN_PATTERN, "10-digit TIN, e.g. 1234567890")


def _validate(value, label, fieldname, default, expected):
	if not value:
		return value

	value = _normalize(value)
	if not _get_pattern(fieldname, default).fullmatch(value):
		frappe.throw(
			_("{0} {1} is invalid. Expected a {2}.").format(label, frappe.bold(value), expected),
			title=_("Invalid {0}").format(label),
		)

	return value
