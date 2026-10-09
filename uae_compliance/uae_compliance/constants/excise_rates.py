# Excise tax rates under Cabinet Decision 197 of 2025, effective 1 January 2026 (see
# docs/UAE_VERIFICATION.md section 5). The old 50% rate on carbonated and sweetened drinks is
# repealed; sweetened drinks are now charged per litre by sugar content. Seeded once and then
# admin-editable.
PERCENTAGE = "Percentage of Excise Price"
PER_LITRE = "Per Litre"
EFFECTIVE_FROM = "2026-01-01"

EXCISE_RATES = [
	{"category": "Tobacco and Tobacco Products", "rate_type": PERCENTAGE, "rate": 100},
	{"category": "E-Cigarette Liquids", "rate_type": PERCENTAGE, "rate": 100},
	{"category": "E-Cigarette Devices", "rate_type": PERCENTAGE, "rate": 100},
	{"category": "Energy Drinks", "rate_type": PERCENTAGE, "rate": 100},
	{
		"category": "Sweetened Drinks (8 g or more sugar per 100 ml)",
		"rate_type": PER_LITRE,
		"rate": 1.09,
	},
	{
		"category": "Sweetened Drinks (5 g to under 8 g sugar per 100 ml)",
		"rate_type": PER_LITRE,
		"rate": 0.79,
	},
]
