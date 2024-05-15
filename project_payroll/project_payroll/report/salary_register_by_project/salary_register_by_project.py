# Copyright (c) 2024, Ala Alsalam and contributors
# For license information, please see license.txt


import frappe
from frappe import _
from frappe.utils import flt

import erpnext
import json

salary_slip = frappe.qb.DocType("Salary Slip")
salary_detail = frappe.qb.DocType("Salary Detail")
salary_component = frappe.qb.DocType("Salary Component")
employee_project = frappe.qb.DocType("Employee Project")

def execute(filters=None):
	if not filters:
		filters = {}

	currency = None
	if filters.get("currency"):
		currency = filters.get("currency")
	company_currency = erpnext.get_company_currency(filters.get("company"))

	salary_slips = get_salary_slips(filters, company_currency)
	if not salary_slips:
		return [], []

	# projects
	emp_projects = get_employees_projects(salary_slips,filters)

	if emp_projects:
		ssp_map = get_salary_slip_projects_details(salary_slips)
		# for e in ssp_map:
		# 	frappe.msgprint(str(e))
		# columns = get_projects_columns(columns, emp_projects)
  
	earning_types, ded_types = get_earning_and_deduction_types(salary_slips)
	columns = get_columns(earning_types, ded_types, emp_projects)
	


	ss_earning_map = get_salary_slip_details(salary_slips, currency, company_currency, "earnings")
	ss_ded_map = get_salary_slip_details(salary_slips, currency, company_currency, "deductions")

	doj_map = get_employee_doj_map()

	data = []
	for ss in salary_slips:
		row = {
			"salary_slip_id": ss.name,
			"employee": ss.employee,
			"employee_name": ss.employee_name,
			"data_of_joining": doj_map.get(ss.employee),
			"branch": ss.branch,
			"department": ss.department,
			"designation": ss.designation,
			"company": ss.company,
			"start_date": ss.start_date,
			"end_date": ss.end_date,
			"leave_without_pay": ss.leave_without_pay,
			"payment_days": ss.payment_days,
			"currency": currency or company_currency,
			"total_loan_repayment": ss.total_loan_repayment,
		}

		update_column_width(ss, columns)
		for p in emp_projects:
			row.update({frappe.scrub(p): ssp_map.get(ss.name, {}).get(p)})
			row.update({frappe.scrub(p + " Amount"): ssp_map.get(ss.name, {}).get(frappe.scrub(p + " Amount"))})
   
		for e in earning_types:
			row.update({frappe.scrub(e): ss_earning_map.get(ss.name, {}).get(e)})

		for d in ded_types:
			row.update({frappe.scrub(d): ss_ded_map.get(ss.name, {}).get(d)})
		
		

		if currency == company_currency:
			row.update(
				{
					"gross_pay": flt(ss.gross_pay) * flt(ss.exchange_rate),
					"total_deduction": flt(ss.total_deduction) * flt(ss.exchange_rate),
					"net_pay": flt(ss.net_pay) * flt(ss.exchange_rate),
				}
			)

		else:
			row.update(
				{"gross_pay": ss.gross_pay, "total_deduction": ss.total_deduction, "net_pay": ss.net_pay}
			)

		data.append(row)

	return columns, data


def get_earning_and_deduction_types(salary_slips):
	salary_component_and_type = {_("Earning"): [], _("Deduction"): []}

	for salary_compoent in get_salary_components(salary_slips):
		component_type = get_salary_component_type(salary_compoent)
		salary_component_and_type[_(component_type)].append(salary_compoent)

	return sorted(salary_component_and_type[_("Earning")]), sorted(
		salary_component_and_type[_("Deduction")]
	)

# def get_employees_projects(salary_slips):
# 	return (
# 		frappe.qb.from_(employee_project)
# 		.where((employee_project.percentage != 0) & (employee_project.parent.isin([d.name for d in salary_slips])))
# 		.select(employee_project.project)
# 		.distinct()
# 	).run(pluck=True)

def get_employees_projects(salary_slips, filters):
    salary_slip_names = [d.get('name') for d in salary_slips]

    query = frappe.qb.from_(employee_project).select(employee_project.project)

    if filters.get("project"):
        query = query.where(employee_project.project == filters.get("project"))

    projects = (
        query
        .where((employee_project.percentage != 0) & (employee_project.parent.isin(salary_slip_names)))
        .distinct()
        .run(pluck=True)
    )

    return projects


def get_salary_slip_projects_details(salary_slips):
	salary_slips = [ss.name for ss in salary_slips]

	result = (
		frappe.qb.from_(salary_slip)
		.join(employee_project)
		.on(salary_slip.name == employee_project.parent)
		.where((employee_project.parent.isin(salary_slips)) )
		.select(
      		employee_project.parent,
			employee_project.project,
			employee_project.percentage,
			employee_project.amount

		)
	).run(as_dict=1)

	ssp_map = {}

	for d in result:
		ssp_map.setdefault(d.parent, frappe._dict()).setdefault(d.project, 0.0)
		ssp_map.setdefault(d.parent, frappe._dict()).setdefault(frappe.scrub(f"{d.project} Amount"), 0.0)
		# d.parent.setdefault(frappe.scrub(f"{d.project} Amount"), 0.0)
  
		ssp_map[d.parent][d.project] += d.percentage
		ssp_map[d.parent][frappe.scrub(f"{d.project} Amount")] += d.amount
	# frappe.msgprint(json.dumps(ssp_map))

	# for d in ssp_map:
	# 	frappe.msgprint("----------------1----------------")
	# 	frappe.msgprint(d[project])
	# 	frappe.msgprint("----------------2----------------")
  
	return ssp_map

def get_projects_columns(columns, projects):

	for project in projects:
		columns.append(
			{
				"label": project,
				"fieldname": frappe.scrub(project),
				"fieldtype": "percent",
				"width": 120,
			}
		)
	
	return columns

# def get_payroll_project(salary_slips):
# 	_salary_structure_assignment = frappe.db.get_value(
# 		"Salary Structure Assignment",
# 		{
# 			"employee": self.employee,
# 			"salary_structure": self.salary_structure,
# 			"from_date": ("<=", self.actual_start_date),
# 			"docstatus": 1,
# 		},
# 		"*",
# 		order_by="from_date desc",
# 		as_dict=True,
# 	)
# 	payroll_project = []
	
# 	return payroll_project

def update_column_width(ss, columns):
	if ss.branch is not None:
		columns[3].update({"width": 120})
	if ss.department is not None:
		columns[4].update({"width": 120})
	if ss.designation is not None:
		columns[5].update({"width": 120})
	if ss.leave_without_pay is not None:
		columns[9].update({"width": 120})


def get_columns(earning_types, ded_types,emp_projects):
	columns = [
		{
			"label": _("Salary Slip ID"),
			"fieldname": "salary_slip_id",
			"fieldtype": "Link",
			"options": "Salary Slip",
			"width": 150,
		},
		{
			"label": _("Employee"),
			"fieldname": "employee",
			"fieldtype": "Link",
			"options": "Employee",
			"width": 120,
		},
		{
			"label": _("Employee Name"),
			"fieldname": "employee_name",
			"fieldtype": "Data",
			"width": 140,
		},
		{
			"label": _("Date of Joining"),
			"fieldname": "data_of_joining",
			"fieldtype": "Date",
			"width": 80,
		},
		{
			"label": _("Branch"),
			"fieldname": "branch",
			"fieldtype": "Link",
			"options": "Branch",
			"width": -1,
		},
		{
			"label": _("Department"),
			"fieldname": "department",
			"fieldtype": "Link",
			"options": "Department",
			"width": -1,
		},
		{
			"label": _("Designation"),
			"fieldname": "designation",
			"fieldtype": "Link",
			"options": "Designation",
			"width": 120,
		},
		# {
		# 	"label": _("Company"),
		# 	"fieldname": "company",
		# 	"fieldtype": "Link",
		# 	"options": "Company",
		# 	"width": 120,
		# },
		{
			"label": _("Start Date"),
			"fieldname": "start_date",
			"fieldtype": "Data",
			"width": 80,
		},
		{
			"label": _("End Date"),
			"fieldname": "end_date",
			"fieldtype": "Data",
			"width": 80,
		},
		# {
		# 	"label": _("Leave Without Pay"),
		# 	"fieldname": "leave_without_pay",
		# 	"fieldtype": "Float",
		# 	"width": 50,
		# },
		# {
		# 	"label": _("Payment Days"),
		# 	"fieldname": "payment_days",
		# 	"fieldtype": "Float",
		# 	"width": 120,
		# },
	]
	for project in emp_projects:
		columns.append(
			{
				"label": project,
				"fieldname": frappe.scrub(project),
				"fieldtype": "Percent",
				"width": 120,
			})
		columns.append(
  			{
				"label": f"{project} Amount",
				"fieldname": frappe.scrub(f"{project} Amount"),
				"fieldtype": "Float",
				"width": 120,
			}
		)
	for earning in earning_types:
		columns.append(
			{
				"label": earning,
				"fieldname": frappe.scrub(earning),
				"fieldtype": "Float",
				# "options": "currency",
				"width": 120,
			}
		)

	columns.append(
		{
			"label": _("Gross Pay"),
			"fieldname": "gross_pay",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 120,
		}
	)

	for deduction in ded_types:
		columns.append(
			{
				"label": deduction,
				"fieldname": frappe.scrub(deduction),
				"fieldtype": "Float",
				# "options": "currency",
				"width": 120,
			}
		)

	columns.extend(
		[
			# {
			# 	"label": _("Loan Repayment"),
			# 	"fieldname": "total_loan_repayment",
			# 	"fieldtype": "Currency",
			# 	"options": "currency",
			# 	"width": 120,
			# },
			{
				"label": _("Total Deduction"),
				"fieldname": "total_deduction",
				"fieldtype": "Currency",
				"options": "currency",
				"width": 120,
			},
			{
				"label": _("Net Pay"),
				"fieldname": "net_pay",
				"fieldtype": "Currency",
				"options": "currency",
				"width": 120,
			},
			{
				"label": _("Currency"),
				"fieldtype": "Data",
				"fieldname": "currency",
				"options": "Currency",
				"hidden": 1,
			},
		]
	)
	return columns


def get_salary_components(salary_slips):
	return (
		frappe.qb.from_(salary_detail)
		.where((salary_detail.amount != 0) & (salary_detail.parent.isin([d.name for d in salary_slips])))
		.select(salary_detail.salary_component)
		.distinct()
	).run(pluck=True)


def get_salary_component_type(salary_component):
	return frappe.db.get_value("Salary Component", salary_component, "type", cache=True)

def get_salary_slips(filters, company_currency):
    doc_status = {"Draft": 0, "Submitted": 1, "Cancelled": 2}

    query = frappe.qb.from_(salary_slip).select(salary_slip.star)

    if filters.get("docstatus"):
        query = query.where(salary_slip.docstatus == doc_status[filters.get("docstatus")])

    if filters.get("from_date"):
        query = query.where(salary_slip.start_date >= filters.get("from_date"))

    if filters.get("to_date"):
        query = query.where(salary_slip.end_date <= filters.get("to_date"))

    if filters.get("company"):
        query = query.where(salary_slip.company == filters.get("company"))

    if filters.get("employee"):
        query = query.where(salary_slip.employee == filters.get("employee"))

    if filters.get("currency") and filters.get("currency") != company_currency:
        query = query.where(salary_slip.currency == filters.get("currency"))

    if filters.get("salary_structure"):
        query = query.where(salary_slip.salary_structure == filters.get("salary_structure"))

    if filters.get("branch"):
        query = query.where(salary_slip.branch == filters.get("branch"))

    if filters.get("project"):
         query = query.join(employee_project).on(employee_project.parent == salary_slip.name)
         query = query.where(employee_project.project == filters.get("project"))

    salary_slips = query.run(as_dict=1)

    return salary_slips or []
# def get_salary_slips(filters, company_currency):
# 	doc_status = {"Draft": 0, "Submitted": 1, "Cancelled": 2}

# 	query = frappe.qb.from_(salary_slip).select(salary_slip.star)

# 	if filters.get("docstatus"):
# 		query = query.where(salary_slip.docstatus == doc_status[filters.get("docstatus")])

# 	if filters.get("from_date"):
# 		query = query.where(salary_slip.start_date >= filters.get("from_date"))

# 	if filters.get("to_date"):
# 		query = query.where(salary_slip.end_date <= filters.get("to_date"))

# 	if filters.get("company"):
# 		query = query.where(salary_slip.company == filters.get("company"))

# 	if filters.get("employee"):
# 		query = query.where(salary_slip.employee == filters.get("employee"))

# 	if filters.get("currency") and filters.get("currency") != company_currency:
# 		query = query.where(salary_slip.currency == filters.get("currency"))
# 	if filters.get("salary_structure"):
# 		query = query.where(salary_slip.salary_structure == filters.get("salary_structure"))
# 	if filters.get("branch"):
# 		query = query.where(salary_slip.branch == filters.get("branch"))
# 	if filters.get("project"):
# 		pass

	
	
# 	salary_slips = query.run(as_dict=1)

# 	return salary_slips or []

def get_employee_doj_map():
	employee = frappe.qb.DocType("Employee")

	result = (frappe.qb.from_(employee).select(employee.name, employee.date_of_joining)).run()

	return frappe._dict(result)


def get_salary_slip_details(salary_slips, currency, company_currency, component_type):
	salary_slips = [ss.name for ss in salary_slips]

	result = (
		frappe.qb.from_(salary_slip)
		.join(salary_detail)
		.on(salary_slip.name == salary_detail.parent)
		.where((salary_detail.parent.isin(salary_slips)) & (salary_detail.parentfield == component_type))
		.select(
			salary_detail.parent,
			salary_detail.salary_component,
			salary_detail.amount,
			salary_slip.exchange_rate,
		)
	).run(as_dict=1)

	ss_map = {}

	for d in result:
		ss_map.setdefault(d.parent, frappe._dict()).setdefault(d.salary_component, 0.0)
		if currency == company_currency:
			ss_map[d.parent][d.salary_component] += flt(d.amount) * flt(
				d.exchange_rate if d.exchange_rate else 1
			)
		else:
			ss_map[d.parent][d.salary_component] += flt(d.amount)

	return ss_map
