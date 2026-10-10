from uae_compliance.uae_compliance.constants.emirates import EMIRATES

# VAT 201 box codes. Box 1 is lettered per emirate (1a-1g); see docs/UAE_VERIFICATION.md.
BOX_STANDARD_RATED_PREFIX = "1"
BOX_TOURIST_REFUNDS = "2"
BOX_REVERSE_CHARGE_SUPPLIES = "3"
BOX_ZERO_RATED = "4"
BOX_EXEMPT = "5"
BOX_IMPORTS = "6"
BOX_IMPORT_ADJUSTMENTS = "7"
BOX_SALES_TOTALS = "8"
BOX_STANDARD_RATED_EXPENSES = "9"
BOX_REVERSE_CHARGE_EXPENSES = "10"
BOX_EXPENSE_TOTALS = "11"

EMIRATE_BOX_CODES = {emirate: f"1{code[1]}" for emirate, code in EMIRATES.items()}

# Quarterly filing staggers: the months a three-month period starts in (FTA VAT Returns User Guide).
STAGGER_START_MONTHS = {
	"Quarterly - Stagger 1 (Feb-Apr)": (2, 5, 8, 11),
	"Quarterly - Stagger 2 (Mar-May)": (3, 6, 9, 12),
	"Quarterly - Stagger 3 (Apr-Jun)": (4, 7, 10, 1),
}
MONTHLY = "Monthly"

# The return and any payment are due by the 28th day after the end of the period.
RETURN_DUE_DAYS = 28

# Categories reported on the return. Out of Scope supplies are not.
REPORTABLE_VAT_CATEGORIES = ("Standard Rated", "Zero Rated", "Exempt")
# The category given to the rows of a sale under the reverse charge, which the return leaves out.
REVERSE_CHARGE_SUPPLY_CATEGORY = "Reverse Charge Supply"
