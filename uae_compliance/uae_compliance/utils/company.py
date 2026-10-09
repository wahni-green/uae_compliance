import frappe

UAE = "United Arab Emirates"


def is_uae_company(company: str | None) -> bool:
	"""Every hook in this app starts with this check, so the app coexists with non-UAE companies on
	a shared bench."""
	if not company:
		return False

	return frappe.get_cached_value("Company", company, "country") == UAE
