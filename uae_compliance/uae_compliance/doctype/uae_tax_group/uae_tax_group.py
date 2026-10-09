import frappe
from frappe import _
from frappe.model.document import Document

from uae_compliance.uae_compliance.utils.company import UAE


class UAETaxGroup(Document):
	"""Two or more related persons registered as one taxable person for VAT (Decree-Law Art 14, ER
	Arts 9-12). The group files one return, through its representative member, and supplies between
	its members are disregarded."""

	def validate(self):
		members = [row.company for row in self.members]

		if len(members) != len(set(members)):
			frappe.throw(_("A company can only be a member of the group once."))

		if len(members) < 2:
			frappe.throw(_("A tax group needs at least two members."))

		if self.representative_member not in members:
			frappe.throw(_("The representative member must be one of the members."))

		for company in members:
			if frappe.get_cached_value("Company", company, "country") != UAE:
				frappe.throw(_("{0} is not a UAE company.").format(company))

			other = frappe.db.get_value(
				"UAE Tax Group Member",
				{"company": company, "parenttype": "UAE Tax Group", "parent": ["!=", self.name]},
				"parent",
			)
			if other:
				frappe.throw(
					_("{0} is already a member of the tax group {1}.").format(company, other),
					title=_("Already in a Tax Group"),
				)

	def on_update(self):
		"""Mirror the membership on each company, which is how the rest of the app finds its group."""
		members = {row.company for row in self.members}
		for company in members:
			frappe.db.set_value("Company", company, "uae_tax_group", self.name, update_modified=False)

		for company in frappe.get_all("Company", filters={"uae_tax_group": self.name}, pluck="name"):
			if company not in members:
				frappe.db.set_value("Company", company, "uae_tax_group", None, update_modified=False)

	def on_trash(self):
		for company in frappe.get_all("Company", filters={"uae_tax_group": self.name}, pluck="name"):
			frappe.db.set_value("Company", company, "uae_tax_group", None, update_modified=False)
