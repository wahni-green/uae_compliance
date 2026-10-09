import re

MODULE = "UAE Compliance"

# TRN: 15 digits, commonly shown as 100-XXXX-XXXX-XXXX. No primary FTA source states the format or a
# checksum, so this is only the default for the configurable pattern in UAE Compliance Settings.
DEFAULT_TRN_PATTERN = r"^100[0-9]{12}$"
# TIN (Peppol / Corporate Tax): 10 digits starting with 1.
DEFAULT_TIN_PATTERN = r"^1[0-9]{9}$"
DEFAULT_TRN_RE = re.compile(DEFAULT_TRN_PATTERN)
DEFAULT_TIN_RE = re.compile(DEFAULT_TIN_PATTERN)

VAT_CATEGORIES = ["Standard Rated", "Zero Rated", "Exempt", "Out of Scope"]
DEFAULT_VAT_CATEGORY = "Standard Rated"
ZONE_DEFAULT_VAT_CATEGORY = "Zero Rated"
NO_TAX_VAT_CATEGORIES = {"Zero Rated", "Exempt", "Out of Scope"}

# A leading blank option: Frappe fills a Select with no default to its first option on every new
# row, which would defeat the category defaulting logic.
VAT_CATEGORY_SELECT_OPTIONS = "\n" + "\n".join(VAT_CATEGORIES)

FILING_FREQUENCIES = [
	"Quarterly - Stagger 1 (Feb-Apr)",
	"Quarterly - Stagger 2 (Mar-May)",
	"Quarterly - Stagger 3 (Apr-Jun)",
	"Monthly",
]

# Reverse charge cases (see docs/UAE_VERIFICATION.md section 3). Designated zone supplies have no
# general reverse charge: goods consumed or short in a zone are treated as imported (ER Art 51(9)).
REVERSE_CHARGE_TYPES = [
	"Import of Services",
	"Import of Goods",
	"Hydrocarbons",
	"Electronic Devices",
	"Precious Metals and Stones",
	"Metal Scrap",
	"Other",
]
REVERSE_CHARGE_TYPE_SELECT_OPTIONS = "\n" + "\n".join(REVERSE_CHARGE_TYPES)
METAL_SCRAP_TYPE = "Metal Scrap"
IMPORT_OF_GOODS_TYPE = "Import of Goods"

# Tax invoice must be issued within 14 days of the supply (Decree-Law Art 67, ER Art 59(13)).
TAX_INVOICE_ISSUE_DAYS = 14
