import itertools

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


def get_uae_test_company() -> str:
	"""A Company registered in the UAE, creating a minimal one if none exists on this site. Created
	uncommitted inside the calling test's own transaction, so it is rolled back automatically."""
	# Prefer the company the test bootstrap creates; other tests add UAE companies of their own.
	if frappe.db.exists("Company", TEST_COMPANY):
		return TEST_COMPANY

	existing = frappe.db.get_value("Company", {"country": "United Arab Emirates"}, order_by="creation asc")
	if existing:
		return existing

	company = frappe.get_doc(
		{
			"doctype": "Company",
			"company_name": "_Test UAE Company",
			"abbr": "TUC",
			"default_currency": "AED",
			"country": "United Arab Emirates",
			"create_chart_of_accounts_based_on": "Standard Template",
			"chart_of_accounts": "Standard",
		}
	).insert()
	return company.name


def get_vat_accounts(company: str) -> tuple[str, str]:
	"""(output, input) VAT account for a company, creating the input account if missing."""
	abbr = frappe.get_cached_value("Company", company, "abbr")
	output = frappe.db.get_value("Account", f"VAT 5% - {abbr}") or frappe.db.get_value(
		"Account", {"company": company, "account_type": "Tax", "is_group": 0, "root_type": "Liability"}
	)
	input_name = f"Input VAT - {abbr}"
	if not frappe.db.exists("Account", input_name):
		frappe.get_doc(
			{
				"doctype": "Account",
				"account_name": "Input VAT",
				"company": company,
				"parent_account": f"Current Assets - {abbr}",
				"account_type": "Tax",
				"root_type": "Asset",
			}
		).insert()

	return output, input_name


def configure_vat_settings(company: str, issues_e_invoices: int = 0, append: bool = False) -> tuple[str, str]:
	"""Point UAE Compliance Settings at this company's VAT accounts (rolled back with the test).
	`append` keeps the rows of other companies, for tests that involve several."""
	output, input_ = get_vat_accounts(company)
	settings = frappe.get_doc("UAE Compliance Settings")
	if append:
		settings.vat_accounts = [row for row in settings.vat_accounts if row.company != company]
	else:
		settings.vat_accounts = []
	settings.append(
		"vat_accounts",
		{
			"company": company,
			"output_vat_account": output,
			"input_vat_account": input_,
			"issues_e_invoices": issues_e_invoices,
		},
	)
	settings.save()
	frappe.clear_document_cache("UAE Compliance Settings", "UAE Compliance Settings")
	return output, input_


def make_item(item_code: str, category: str | None = None):
	if frappe.db.exists("Item", item_code):
		return frappe.get_doc("Item", item_code)

	return frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": item_code,
			"item_name": item_code,
			"item_group": "All Item Groups",
			"stock_uom": "Nos",
			"is_stock_item": 0,
			"uae_vat_category": category or "",
		}
	).insert()


def make_customer(name: str, trn: str | None = None):
	if frappe.db.exists("Customer", name):
		doc = frappe.get_doc("Customer", name)
		doc.uae_trn = trn
		doc.save()
		return doc

	return frappe.get_doc({"doctype": "Customer", "customer_name": name, "uae_trn": trn}).insert()


def make_address(
	title: str, country: str, customer: str | None = None, supplier: str | None = None, **kwargs
):
	links = []
	if customer:
		links.append({"link_doctype": "Customer", "link_name": customer})
	if supplier:
		links.append({"link_doctype": "Supplier", "link_name": supplier})

	return frappe.get_doc(
		{
			"links": links,
			"doctype": "Address",
			"address_title": title,
			"address_type": "Billing",
			"address_line1": "1 Test Street",
			"city": "Test City",
			"country": country,
			**kwargs,
		}
	).insert()


def make_sales_invoice(rows: list[dict], customer: str = "_Test UAE Customer", rate: float = 5, **kwargs):
	"""A draft Sales Invoice with a VAT row at `rate`% on the output account. Each row dict takes
	item_code, qty, rate, plus optional uae_vat_category, item_tax_template and `vat_rate` (a row-
	level override of the invoice rate, e.g. 0)."""
	company = kwargs.pop("company", get_uae_test_company())
	output, _input = get_vat_accounts(company)
	make_customer(customer) if not frappe.db.exists("Customer", customer) else None

	items = []
	for row in rows:
		row = dict(row)
		vat_rate = row.pop("vat_rate", None)
		if vat_rate is not None and not row.get("item_tax_template"):
			row["item_tax_template"] = get_rate_template(company, output, vat_rate)
		items.append({"qty": 1, "rate": 100, **row})

	doc = frappe.get_doc(
		{
			"doctype": "Sales Invoice",
			"company": company,
			"customer": customer,
			"posting_date": (posting_date := kwargs.pop("posting_date", frappe.utils.today())),
			"due_date": posting_date,
			"set_posting_time": 1,
			"items": items,
			"taxes": [
				{
					"charge_type": "On Net Total",
					"account_head": output,
					"description": "VAT",
					"rate": rate,
				}
			],
			**kwargs,
		}
	)
	return doc


def get_rate_template(company: str, output_account: str, rate: float) -> str:
	"""An Item Tax Template with no VAT Category that applies `rate`% to the output account."""
	title = f"_Test UAE VAT {rate}%"
	abbr = frappe.get_cached_value("Company", company, "abbr")
	name = f"{title} - {abbr}"
	if not frappe.db.exists("Item Tax Template", name):
		frappe.get_doc(
			{
				"doctype": "Item Tax Template",
				"title": title,
				"company": company,
				"taxes": [{"tax_type": output_account, "tax_rate": rate}],
			}
		).insert()

	return name


def set_company_address(company: str, **kwargs) -> str:
	"""Give the company a default address and return its name."""
	address = frappe.get_doc(
		{
			"doctype": "Address",
			"address_title": f"{company} HQ",
			"address_type": "Office",
			"address_line1": "1 Sheikh Zayed Road",
			"city": "Dubai",
			"country": "United Arab Emirates",
			"uae_emirate": "Dubai",
			"is_your_company_address": 1,
			"links": [{"link_doctype": "Company", "link_name": company}],
			**kwargs,
		}
	).insert()
	return address.name


def create_submitted_sales_invoice(rows=None, emirate="Dubai", **kwargs):
	"""A submitted Sales Invoice with a VAT emirate, for print and report tests."""
	make_item("_Test Print Item")
	doc = make_sales_invoice(rows or [{"item_code": "_Test Print Item"}], **kwargs)
	doc.uae_emirate = emirate
	doc.insert()
	doc.submit()
	return doc


_test_date_counter = itertools.count()
_bill_counter = itertools.count()


def get_unique_test_date():
	"""A fresh date, never repeated in a test run. FrappeTestCase only rolls back once per class, so
	two test methods that create invoices on the same day would see each other's invoices in a
	period query. Offsets from the current fiscal year's start, because a submitted invoice outside
	every fiscal year is refused by ERPNext."""
	from erpnext.accounts.utils import get_fiscal_year
	from frappe.utils import add_days, getdate

	_, fiscal_year_start, _end = get_fiscal_year(getdate())
	return add_days(fiscal_year_start, next(_test_date_counter))


def make_uae_company(name: str, abbr: str) -> str:
	"""A second UAE company, for tests involving more than one."""
	if frappe.db.exists("Company", name):
		return name

	return (
		frappe.get_doc(
			{
				"doctype": "Company",
				"company_name": name,
				"abbr": abbr,
				"default_currency": "AED",
				"country": "United Arab Emirates",
				"create_chart_of_accounts_based_on": "Standard Template",
				"chart_of_accounts": "Standard",
			}
		)
		.insert()
		.name
	)


def create_submitted_purchase_invoice(
	rows=None, taxes=(), posting_date=None, supplier="_Test UAE Supplier", company=None, **kwargs
):
	"""A submitted Purchase Invoice. `taxes` is a list of (account, rate, add_deduct) tuples."""
	company = company or get_uae_test_company()
	make_item("_Test Print Item")
	if not frappe.db.exists("Supplier", supplier):
		frappe.get_doc({"doctype": "Supplier", "supplier_name": supplier}).insert()

	posting_date = posting_date or frappe.utils.today()
	doc = frappe.get_doc(
		{
			"doctype": "Purchase Invoice",
			"company": company,
			"supplier": supplier,
			"posting_date": posting_date,
			"due_date": posting_date,
			"set_posting_time": 1,
			"bill_no": f"BILL-{next(_bill_counter)}",
			"items": [
				{"item_code": "_Test Print Item", "qty": 1, "rate": 100, **row} for row in (rows or [{}])
			],
			"taxes": [
				{
					"charge_type": "On Net Total",
					"account_head": account,
					"description": "VAT",
					"rate": rate,
					"add_deduct_tax": add_deduct,
					"category": "Total",
				}
				for account, rate, add_deduct in taxes
			],
			**kwargs,
		}
	)
	doc.insert()
	doc.submit()
	return doc


def delete_tax_groups() -> None:
	for name in frappe.get_all("UAE Tax Group", pluck="name"):
		frappe.delete_doc("UAE Tax Group", name, force=True)


def setup_einvoice_masters(company: str, customer: str = "_Test UAE Customer") -> dict:
	"""Everything a PINT AE invoice needs from the company, the customer and their addresses."""
	frappe.db.set_value(
		"Company",
		company,
		{
			"uae_tin": "1234567890",
			"uae_trn": "100123456789003",
			"uae_legal_registration_type": "Trade License",
			"uae_legal_registration_id": "112345678900003",
			"uae_licence_authority": "Dubai Economy",
		},
	)
	make_customer(customer, "100987654321003")
	frappe.db.set_value(
		"Customer",
		customer,
		{
			"customer_name": customer,
			"uae_tin": "1987654321",
			"uae_trn": "134567890123003",
			"uae_legal_registration_type": "Trade License",
			"uae_legal_registration_id": "112345679000001",
			"uae_licence_authority": "Abu Dhabi DED",
			"customer_type": "Company",
		},
	)
	frappe.clear_document_cache("Company", company)
	company_address = set_company_address(company)
	customer_address = make_address(
		f"{customer} HQ", "United Arab Emirates", customer=customer, uae_emirate="Abu Dhabi"
	)
	return {"company_address": company_address, "customer_address": customer_address.name}


def make_einvoice_item(item_code: str, category: str | None = None, **fields):
	"""A service item with the service accounting code a PINT AE line needs."""
	item = make_item(item_code, category)
	frappe.db.set_value("Item", item.name, {"uae_sac_code": "998311", **fields})
	return item
