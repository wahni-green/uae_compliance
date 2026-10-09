# Seeded from secondary sources (the only FTA-hosted list is from 2018 and includes zones removed in
# 2021: Dubai Textile City, Al Quoz). Admin-editable; re-verify against the FTA legislation page.
# See docs/UAE_VERIFICATION.md section 3.
REMARKS = "Seeded from secondary sources; verify against the current FTA Cabinet Decision list."

_ZONES = {
	"Abu Dhabi": [
		"Khalifa Port Free Trade Zone",
		"Abu Dhabi Airport Free Zone",
		"Khalifa Industrial Zone Abu Dhabi",
		"Al Ain Airport Free Zone",
		"Al Butain Airport Free Zone",
	],
	"Dubai": [
		"Jebel Ali Free Zone (North-South)",
		"Dubai Cars and Automotive Zone",
		"Al Qusais Free Zone",
		"Dubai Aviation City",
		"Dubai Airport Free Zone",
		"International Humanitarian City",
		"Dubai Commercity",
	],
	"Sharjah": ["Hamriyah Free Zone", "Sharjah Airport International Free Zone"],
	"Ajman": ["Ajman Free Zone"],
	"Umm Al Quwain": [
		"Umm Al Quwain Free Trade Zone (Ahmed bin Rashid Port)",
		"Umm Al Quwain Free Trade Zone (Sheikh Mohammed bin Zayed Road)",
	],
	"Ras Al Khaimah": [
		"Ras Al Khaimah Free Trade Zone",
		"Ras Al Khaimah Maritime City",
		"Al Hamra Industrial Zone",
		"Al Ghail Industrial Zone",
		"Al Hulaila Industrial Zone",
	],
	"Fujairah": ["Fujairah Free Zone", "Fujairah Oil Industry Zone"],
}

DESIGNATED_ZONES = [
	{"zone_name": zone, "emirate": emirate, "is_active": 1, "remarks": REMARKS}
	for emirate, zones in _ZONES.items()
	for zone in zones
]
