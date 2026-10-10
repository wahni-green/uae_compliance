import re

MODULE = "UAE Compliance"

# TRN: 15 digits, starting with 1 and ending with 03 (Schematron rule ibr-132-ae of the PINT AE
# specification). No FTA source states a checksum. This is only the default for the configurable
# pattern in UAE Compliance Settings.
DEFAULT_TRN_PATTERN = r"^1[0-9]{12}03$"
LEGACY_TRN_PATTERN = r"^100[0-9]{12}$"
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
IMPORT_OF_SERVICES_TYPE = "Import of Services"

# What a supplier can supply under a domestic reverse charge (see docs/UAE_VERIFICATION.md section 8).
# The recipient then accounts for the VAT and the supplier does not report it.
SALES_REVERSE_CHARGE_TYPES = [
	"Crude or Refined Oil",
	"Natural Gas",
	"Pure Hydrocarbons",
	"Electronic Devices",
	"Precious Metals and Stones",
	"Metal Scrap",
]
SALES_REVERSE_CHARGE_TYPE_SELECT_OPTIONS = "\n" + "\n".join(SALES_REVERSE_CHARGE_TYPES)

# Tax invoice must be issued within 14 days of the supply (Decree-Law Art 67, ER Art 59(13)).
TAX_INVOICE_ISSUE_DAYS = 14

# Adjustments that are not transactions, reported in the adjustment columns of the VAT 201.
ADJUSTMENT_BAD_DEBT_RELIEF = "Bad Debt Relief"
ADJUSTMENT_BAD_DEBT_REPAYMENT = "Bad Debt Repayment"
ADJUSTMENT_ANNUAL_APPORTIONMENT = "Annual Apportionment"
ADJUSTMENT_CAPITAL_ASSETS = "Capital Assets Scheme"
ADJUSTMENT_IMPORT = "Import Adjustment"
ADJUSTMENT_TYPES = [
	ADJUSTMENT_BAD_DEBT_RELIEF,
	ADJUSTMENT_BAD_DEBT_REPAYMENT,
	ADJUSTMENT_ANNUAL_APPORTIONMENT,
	ADJUSTMENT_CAPITAL_ASSETS,
	ADJUSTMENT_IMPORT,
]
ADJUSTMENT_TYPE_SELECT_OPTIONS = "\n".join(ADJUSTMENT_TYPES)

# Bad debt relief needs more than six months to have passed (Decree-Law Art 64).
BAD_DEBT_MONTHS = 6

# Input tax attribution for partial exemption (ER Art 55).
INPUT_TAX_ATTRIBUTIONS = ["Taxable Supplies", "Exempt Supplies", "Residual"]
INPUT_TAX_ATTRIBUTION_SELECT_OPTIONS = "\n" + "\n".join(INPUT_TAX_ATTRIBUTIONS)
ATTRIBUTION_EXEMPT = "Exempt Supplies"
ATTRIBUTION_RESIDUAL = "Residual"

# Capital assets scheme (ER Arts 57-58).
CAPITAL_ASSET_THRESHOLD = 5_000_000
CAPITAL_ASSET_YEARS = {"Building": 10, "Other": 5}

# The standard rate of VAT. Used where a figure is derived from the rate (profit margin scheme).
STANDARD_VAT_RATE = 5

# Tax refunds for tourists (FTA Decision 2 of 2018 as amended).
TOURIST_MIN_PURCHASE = 250
TOURIST_REFUND_CAP = 35_000
