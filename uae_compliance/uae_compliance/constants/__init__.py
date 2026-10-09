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
