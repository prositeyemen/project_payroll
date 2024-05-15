# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt



import frappe
from frappe import _, msgprint

from frappe.utils import (
	flt,
)

from hrms.payroll.doctype.salary_structure_assignment.salary_structure_assignment import SalaryStructureAssignment

class SalaryStructureAssignmentCustom(SalaryStructureAssignment):
	def validate_project_distribution(self):
		if self.get("custom_project"):
			total_percentage = sum([flt(d.percentage) for d in self.get("custom_project", [])])
			if total_percentage > 100:
				frappe.throw(_("The total percentage for the project must be less than or equal to 100"))