# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt


import unicodedata
from datetime import date

import frappe
from frappe import _, msgprint
from frappe.model.naming import make_autoname
from frappe.query_builder import Order
from frappe.query_builder.functions import Sum
from frappe.utils import (
	add_days,
	ceil,
	cint,
	cstr,
	date_diff,
	floor,
	flt,
	formatdate,
	get_first_day,
	get_link_to_form,
	getdate,
	money_in_words,
	rounded,
)
from frappe.utils.background_jobs import enqueue

import erpnext
from erpnext.accounts.utils import get_fiscal_year
from erpnext.setup.doctype.employee.employee import get_holiday_list_for_employee
from erpnext.utilities.transaction_base import TransactionBase

from hrms.hr.utils import validate_active_employee
from hrms.payroll.doctype.additional_salary.additional_salary import get_additional_salaries
from hrms.payroll.doctype.employee_benefit_application.employee_benefit_application import (
	get_benefit_component_amount,
)
from hrms.payroll.doctype.employee_benefit_claim.employee_benefit_claim import (
	get_benefit_claim_amount,
	get_last_payroll_period_benefits,
)
from hrms.payroll.doctype.payroll_entry.payroll_entry import get_start_end_dates
from hrms.payroll.doctype.payroll_period.payroll_period import (
	get_payroll_period,
	get_period_factor,
)
from hrms.payroll.doctype.salary_slip.salary_slip_loan_utils import (
	cancel_loan_repayment_entry,
	make_loan_repayment_entry,
	set_loan_repayment,
)
from hrms.payroll.utils import sanitize_expression
from hrms.utils.holiday_list import get_holiday_dates_between

# cache keys
HOLIDAYS_BETWEEN_DATES = "holidays_between_dates"
LEAVE_TYPE_MAP = "leave_type_map"
SALARY_COMPONENT_VALUES = "salary_component_values"
TAX_COMPONENTS_BY_COMPANY = "tax_components_by_company"

from hrms.payroll.doctype.salary_slip.salary_slip import SalarySlip

class SalarySlipCustom(SalarySlip):
	def validate(self):
		self.status = self.get_status()
		validate_active_employee(self.employee)
		self.validate_dates()
		self.check_existing()

		if not self.salary_slip_based_on_timesheet:
			self.get_date_details()

		if not (len(self.get("earnings")) or len(self.get("deductions"))):
			# get details from salary structure
			
			self.get_emp_and_working_day_details()
		else:
			self.get_working_days_details(lwp=self.leave_without_pay)
		
		# frappe.msgprint("zizo")
		self.set_salary_structure_assignment()
		self.calculate_net_pay()
		self.compute_year_to_date()
		self.compute_month_to_date()
		self.compute_component_wise_year_to_date()

		self.add_leave_balances()

		max_working_hours = frappe.db.get_single_value(
			"Payroll Settings", "max_working_hours_against_timesheet"
		)
		if max_working_hours:
			if self.salary_slip_based_on_timesheet and (self.total_working_hours > int(max_working_hours)):
				frappe.msgprint(
					_("Total working hours should not be greater than max working hours {0}").format(
						max_working_hours
					),
					alert=True,
				)
		self.custom_actual_working_days = self.get_days_from_joining()
    
		self.calculate_net_pay()

		# projects
		self.calculate_net_pay_for_projects()
  
	def get_days_from_joining(self):
		return frappe.utils.date_diff(self.posting_date, frappe.get_value("Employee",self.employee,"date_of_joining"))

	# projects
	def calculate_net_pay_for_projects(self):
		self.add_employee_projects()
		
	def add_employee_projects(self):
		
		ssa = self.get_structure_assignment()

		if ssa.get("custom_projects"):
			for struct_proj_row in ssa.get("custom_projects"):
				amount = self.base_net_pay * struct_proj_row.percentage /100
				self.update_employee_project_row(struct_proj_row, amount)
		# else:
		# 	frappe.msgprint("No Project in This Salary Structure Assignment")
   
	def update_employee_project_row(
		self,
		project_row_data,
		amount
	):
		project_row = None
		for d in self.get("custom_projects"):
			if d.project != project_row_data.project:
				continue
			project_row = d
			break

		if not project_row:
			project_row = self.append(
					"custom_projects",
					{
						"project": project_row_data.project,
						"percentage": project_row_data.percentage
					}
				)
		project_row.amount =  amount

	def get_structure_assignment(self):
		ss = frappe.qb.DocType("Salary Structure")
		ssa = frappe.qb.DocType("Salary Structure Assignment")

		query = (
			frappe.qb.from_(ssa)
			.join(ss)
			.on(ssa.salary_structure == ss.name)
			.select(ssa.name)
			.where(
				(ssa.docstatus == 1)
				& (ss.docstatus == 1)
				& (ss.is_active == "Yes")
				& (ssa.employee == self.employee)
				& (
					(ssa.from_date <= self.start_date)
					| (ssa.from_date <= self.end_date)
					| (ssa.from_date <= self.joining_date)
				)
			)
			.orderby(ssa.from_date, order=Order.desc)
			.limit(1)
		)

		if not self.salary_slip_based_on_timesheet and self.payroll_frequency:
			query = query.where(ss.payroll_frequency == self.payroll_frequency)

		st_name = query.run()

		if st_name:
			return frappe.get_doc("Salary Structure Assignment",st_name[0][0])


	

