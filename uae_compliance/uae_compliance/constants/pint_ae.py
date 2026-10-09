"""PINT AE (Peppol UAE e-invoicing) constants, from the specification bundle at
https://docs.peppol.eu/poac/ae/pint-ae/ (version 1.0.4) and the MoF Guidelines. See
docs/UAE_VERIFICATION.md section 4."""

CUSTOMIZATION_ID = "urn:peppol:pint:billing-1@ae-1"
PROFILE_ID = "urn:peppol:bis:billing"

# Participant identifier scheme for the UAE: the 10 digit TIN.
ENDPOINT_SCHEME = "0235"
# Predefined endpoints for a buyer that is not on the network yet, and for exports.
ENDPOINT_BUYER_NOT_ON_NETWORK = "9900000098"
ENDPOINT_EXPORT = "9900000099"

INVOICE_TYPE_CODE = "380"
CREDIT_NOTE_TYPE_CODE = "381"

# Tax category codes (IBT-151). There is no code for exports: those are flagged in the transaction
# type (ProfileExecutionID).
CATEGORY_CODES = {"Standard Rated": "S", "Zero Rated": "Z", "Exempt": "E"}
SUPPORTED_CATEGORIES = tuple(CATEGORY_CODES)

# ProfileExecutionID: eight 0/1 flags (BTAE-02).
FLAG_FREE_TRADE_ZONE = 0
FLAG_DEEMED_SUPPLY = 1
FLAG_MARGIN_SCHEME = 2
FLAG_SUMMARY = 3
FLAG_CONTINUOUS = 4
FLAG_AGENT_BILLING = 5
FLAG_E_COMMERCE = 6
FLAG_EXPORT = 7

# Country subdivision codes of the emirates (IBT-039, IBT-054).
EMIRATE_SUBDIVISIONS = {
	"Abu Dhabi": "AUH",
	"Dubai": "DXB",
	"Sharjah": "SHJ",
	"Ajman": "AJM",
	"Umm Al Quwain": "UAQ",
	"Ras Al Khaimah": "RAK",
	"Fujairah": "FUJ",
}

# Legal registration identifier types (BTAE-15, BTAE-16) and their scheme agency IDs.
LEGAL_REGISTRATION_TYPES = {
	"Trade License": "TL",
	"Emirates ID": "EID",
	"Passport": "PAS",
	"Cabinet Decision": "CD",
}
LEGAL_REGISTRATION_SELECT_OPTIONS = "\n" + "\n".join(LEGAL_REGISTRATION_TYPES)
TRADE_LICENSE_AGENCY = "Trade License issuing Authority"

# VAT exemption reason codes (IBT-186).
EXEMPTION_REASONS = {
	"DL8.46.1": "Financial services",
	"DL8.46.2": "Residential units",
	"DL8.46.3": "Bare land",
	"DL8.46.4": "Local passenger transport",
}
EXEMPTION_REASON_SELECT_OPTIONS = "\n" + "\n".join(EXEMPTION_REASONS)

# Credit note reason codes (BTAE-03).
CREDIT_REASONS = {
	"DL8.61.1.A": "The supply was cancelled",
	"DL8.61.1.B": "The tax treatment changed because the nature of the supply changed",
	"DL8.61.1.C": "The agreed consideration was altered (for example bad debt relief)",
	"DL8.61.1.D": "Goods or services were returned and the consideration returned",
	"DL8.61.1.E": "Tax was charged or the tax treatment applied in error",
	"VD": "Volume discount",
}
CREDIT_REASON_SELECT_OPTIONS = "\n" + "\n".join(CREDIT_REASONS)

# Payment means: "instrument not defined". Credit transfer (30) would need an account identifier.
PAYMENT_MEANS_CODE = "1"

# UN/ECE Recommendation 20 unit codes for the units of measure we recognise; anything else is
# reported as a piece (H87).
UNIT_CODES = {
	"Nos": "H87",
	"Unit": "H87",
	"Kg": "KGM",
	"Gram": "GRM",
	"Litre": "LTR",
	"Meter": "MTR",
	"Box": "BX",
	"Pair": "PR",
	"Hour": "HUR",
	"Day": "DAY",
	"Month": "MON",
}
DEFAULT_UNIT_CODE = "H87"

# Item type (BTAE-13): goods need an HS code, services a service accounting code.
ITEM_TYPE_CODES = {"Goods": "G", "Services": "S", "Both": "B"}
ITEM_TYPE_SELECT_OPTIONS = "\n" + "\n".join(ITEM_TYPE_CODES)

# UAE standard time. The e-invoice IssueTime carries an offset.
UTC_OFFSET = "+04:00"

# VAT identifier format from the Schematron (rule ibr-132-ae): 15 digits, starting with 1 and
# ending with 03. The TIN (Peppol participant identifier) is 10 digits starting with 1.
PINT_TRN_PATTERN = r"^1[0-9]{12}03$"
PINT_TIN_PATTERN = r"^1[0-9]{9}$"
