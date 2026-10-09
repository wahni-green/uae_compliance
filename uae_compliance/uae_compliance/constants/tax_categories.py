UAE_VAT_CATEGORIES = ("Standard Rated", "Zero Rated", "Exempt", "Out of Scope")

# PINT AE tax category codes (IBT-151). There is no "G" code: exports, free zone, deemed supply and
# margin scheme are carried in ProfileExecutionID flags. See docs/UAE_VERIFICATION.md.
PINT_AE_TAX_CATEGORY_CODES = {
	"Standard Rated": "S",
	"Zero Rated": "Z",
	"Exempt": "E",
	"Out of Scope": "O",
}
PINT_AE_REVERSE_CHARGE_CODE = "AE"
