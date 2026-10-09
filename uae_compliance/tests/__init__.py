import frappe
from frappe.desk.page.setup_wizard.setup_wizard import setup_complete
from frappe.utils import getdate

TEST_COMPANY = "_Test UAE VAT Company"


def before_tests() -> None:
	frappe.clear_cache()

	# setup_complete() is a one-time site setup step, so only bootstrap on a site with no Company.
	if not frappe.db.a_row_exists("Company"):
		year = getdate().year

		setup_complete(
			{
				"currency": "AED",
				"full_name": "Test User",
				"company_name": TEST_COMPANY,
				"timezone": "Asia/Dubai",
				"company_abbr": "TUVC",
				"industry": "Manufacturing",
				"country": "United Arab Emirates",
				"fy_start_date": f"{year}-01-01",
				"fy_end_date": f"{year}-12-31",
				"language": "English",
				"company_tagline": "Testing",
				"email": "test@example.com",
				"password": "test",
				"chart_of_accounts": "Standard",
			}
		)

		frappe.db.set_value("Company", TEST_COMPANY, "tax_id", "100123456789003")

	if frappe.db.exists("Company", TEST_COMPANY):
		global_defaults = frappe.get_single("Global Defaults")
		global_defaults.default_company = TEST_COMPANY
		global_defaults.save()

	frappe.db.commit()  # nosemgrep

	frappe.flags.country = "United Arab Emirates"
