def get_sales_totals(boxes: list[dict]) -> dict:
	"""Box 8: totals of boxes 1a-1g to 7."""
	return {
		"amount": sum(box["amount"] for box in boxes),
		"vat_amount": sum(box["vat_amount"] for box in boxes),
		"adjustment": sum(box["adjustment"] for box in boxes),
	}


def get_expense_totals(boxes: list[dict]) -> dict:
	"""Box 11: totals of boxes 9 and 10."""
	return get_sales_totals(boxes)


def get_total_due_tax(sales_totals: dict) -> float:
	"""Box 12: the VAT and adjustment columns of box 8."""
	return sales_totals["vat_amount"] + sales_totals["adjustment"]


def get_total_recoverable_tax(expense_totals: dict) -> float:
	"""Box 13: the recoverable VAT and adjustment columns of box 11."""
	return expense_totals["vat_amount"] + expense_totals["adjustment"]


def get_payable_tax(total_due: float, total_recoverable: float) -> float:
	"""Box 14: due minus recoverable. Negative means tax is recoverable."""
	return total_due - total_recoverable
