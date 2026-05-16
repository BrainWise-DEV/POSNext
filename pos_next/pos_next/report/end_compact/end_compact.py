import frappe
from frappe import _
from frappe.utils import today, flt, get_first_day

def execute(filters=None):
	columns = [
		{
			"label": _("Mode of Payment"),
			"fieldname": "mode_of_payment",
			"fieldtype": "Data",
			"width": 180
		}
	]

	users = []
	if filters.get("pos_profile"):
		pos_profile = frappe.get_doc("POS Profile", filters.get("pos_profile"))
		for row in pos_profile.applicable_for_users:
			if row.user:
				user_full_name = frappe.db.get_value("User", row.user, "full_name")
				users.append(row.user)
				columns.append({
					"label": _(user_full_name or row.user),
					"fieldname": row.user,
					"fieldtype": "Currency",
					"width": 120
				})

	columns.extend([
		{
			"label": _("Total"),
			"fieldname": "total",
			"fieldtype": "Currency",
			"width": 120
		},
		{
			"label": _("PMT BILL"),
			"fieldname": "pmt_bill",
			"fieldtype": "Int",
			"width": 100
		},
		{
			"label": _("Sales Person"),
			"fieldname": "sales_person",
			"fieldtype": "Data",
			"width": 150
		},
		{
			"label": _("Allocated Amount"),
			"fieldname": "allocated_amount",
			"fieldtype": "Currency",
			"width": 120
		},
		{
			"label": _("Allocated Percentage"),
			"fieldname": "allocated_percentage",
			"fieldtype": "Percent",
			"width": 100
		}
	])

	data = get_data(filters, users)
	
	if data:
		totals = {}
		overall_total = 0
		for col in columns:
			fn = col.get("fieldname")
			if fn == "mode_of_payment": continue
			
			total_val = 0
			for row in data:
				val = row.get(fn)
				if isinstance(val, (int, float)):
					total_val += val
			totals[fn] = total_val
			if fn == "total":
				overall_total = total_val

		empty_row = {"mode_of_payment": " "}
		for col in columns:
			if col.get("fieldname") != "mode_of_payment":
				empty_row[col.get("fieldname")] = None
		data.append(empty_row)
		
		total_bills = totals.get("pmt_bill") or 0
		total_row = {"mode_of_payment": f"<strong>{total_bills}</strong>"}
		
		for col in columns:
			fn = col.get("fieldname")
			if fn == "mode_of_payment":
				continue
			
			total_val = totals.get(fn) or 0
			
			if col.get("fieldtype") == "Currency":
				formatted = frappe.format(total_val, col)
				total_row[fn] = f"<strong>{formatted}</strong>"
			elif col.get("fieldtype") in ["Int", "Float", "Percent"]:
				total_row[fn] = f"<strong>{total_val}</strong>"
			else:
				total_row[fn] = total_val
		
		total_row["sales_person"] = ""
		total_row["allocated_percentage"] = ""
		
		data.append(total_row)

		col2_fn = columns[1].get("fieldname") if len(columns) > 1 else "total"
		col3_fn = columns[2].get("fieldname") if len(columns) > 2 else "allocated_percentage"
		col4_fn = columns[3].get("fieldname") if len(columns) > 3 else "pmt_bill"
		col5_fn = columns[4].get("fieldname") if len(columns) > 4 else "sales_person"

		cat_spacer = empty_row.copy()
		cat_spacer["_is_category_row"] = True
		cat_spacer["_category_columns"] = ["mode_of_payment", col2_fn, col3_fn, col4_fn, col5_fn]
		data.append(cat_spacer)

		header_row = {
			"mode_of_payment": f"<strong>{_('Category-Type')}</strong>",
			col2_fn: f"<strong>{_('Date Total')}</strong>",
			col3_fn: f"<strong>{_('Tot %')}</strong>",
			col4_fn: f"<strong>{_('Month Total')}</strong>",
			col5_fn: f"<strong>{_('Tot %')}</strong>",
			"_is_category_row": True,
			"_category_columns": ["mode_of_payment", col2_fn, col3_fn, col4_fn, col5_fn]
		}
		for col in columns:
			fn = col.get("fieldname")
			if fn not in ["mode_of_payment", col2_fn, col3_fn, col4_fn, col5_fn, "_is_category_row", "_category_columns"]:
				header_row[fn] = ""
		data.append(header_row)

		all_item_groups = frappe.get_all("Item Group", 
			fields=["name", "parent_item_group", "is_group"], 
			order_by="lft asc")
		
		first_day = get_first_day(today())
		
		conditions = ""
		if filters.get("pos_profile"):
			conditions += " AND si.pos_profile = %(pos_profile)s"

		daily_sales = frappe.db.sql(f"""
			SELECT isi.item_group, SUM(isi.amount) as amount
			FROM `tabSales Invoice` si JOIN `tabSales Invoice Item` isi ON isi.parent = si.name
			WHERE si.docstatus = 1 AND si.is_pos = 1 AND si.posting_date = '{today()}' {conditions}
			GROUP BY isi.item_group
		""", filters, as_dict=1)

		monthly_sales = frappe.db.sql(f"""
			SELECT isi.item_group, SUM(isi.amount) as amount
			FROM `tabSales Invoice` si JOIN `tabSales Invoice Item` isi ON isi.parent = si.name
			WHERE si.docstatus = 1 AND si.is_pos = 1 AND si.posting_date BETWEEN '{first_day}' AND '{today()}' {conditions}
			GROUP BY isi.item_group
		""", filters, as_dict=1)

		daily_map = {d.item_group: d.amount for d in daily_sales}
		monthly_map = {d.item_group: d.amount for d in monthly_sales}
		
		daily_totals = {ig.name: daily_map.get(ig.name, 0) for ig in all_item_groups}
		monthly_totals = {ig.name: monthly_map.get(ig.name, 0) for ig in all_item_groups}
		
		for ig in reversed(all_item_groups):
			if ig.parent_item_group:
				if ig.parent_item_group in daily_totals: daily_totals[ig.parent_item_group] += daily_totals[ig.name]
				if ig.parent_item_group in monthly_totals: monthly_totals[ig.parent_item_group] += monthly_totals[ig.name]
		
		daily_section_total = round(sum(daily_totals[ig.name] for ig in all_item_groups if not ig.parent_item_group))
		monthly_section_total = round(sum(monthly_totals[ig.name] for ig in all_item_groups if not ig.parent_item_group))

		levels = {}
		parent_map = {ig.name: ig.parent_item_group for ig in all_item_groups}
		def get_level(group_name):
			if not group_name: return -1
			if group_name in levels: return levels[group_name]
			level = get_level(parent_map.get(group_name)) + 1
			levels[group_name] = level
			return level

		for ig in all_item_groups:
			d_val = daily_totals.get(ig.name, 0)
			m_val = monthly_totals.get(ig.name, 0)
			d_pct = (d_val / daily_section_total * 100) if daily_section_total else 0
			m_pct = (m_val / monthly_section_total * 100) if monthly_section_total else 0
			
			row = {
				"mode_of_payment": ig.name,
				col2_fn: d_val,
				col3_fn: d_pct,
				col4_fn: m_val,
				col5_fn: m_pct,
				"indent": get_level(ig.name),
				"is_group": int(ig.is_group or 0),
				"_is_category_row": True,
				"_percentage_columns": [col3_fn, col5_fn],
				"_category_columns": ["mode_of_payment", col2_fn, col3_fn, col4_fn, col5_fn]
			}
			for col in columns:
				fn = col.get("fieldname")
				if fn not in ["mode_of_payment", col2_fn, col3_fn, col4_fn, col5_fn, "indent", "is_group", "_is_category_row", "_percentage_columns", "_category_columns"]:
					row[fn] = ""
			data.append(row)

		gross_row = {
			"mode_of_payment": f"<strong>{_('Gross Amount')}</strong>",
			col2_fn: daily_section_total,
			col3_fn: "",
			col4_fn: monthly_section_total,
			col5_fn: "",
			"_is_category_row": True,
			"_percentage_columns": [col3_fn, col5_fn],
			"_category_columns": ["mode_of_payment", col2_fn, col3_fn, col4_fn, col5_fn]
		}
		for col in columns:
			fn = col.get("fieldname")
			if fn not in ["mode_of_payment", col2_fn, col3_fn, col4_fn, col5_fn, "_is_category_row", "_percentage_columns", "_category_columns"]:
				gross_row[fn] = ""
		data.append(gross_row)

	return columns, data

def get_data(filters, users):
	modes = frappe.get_all("Mode of Payment", filters={"enabled": 1}, pluck="name")
	
	report_data = {}
	for mode in modes:
		report_data[mode] = {
			"mode_of_payment": mode,
			"total": 0,
			"pmt_bill": 0,
			"sales_person": [],
			"allocated_amount": 0,
			"allocated_percentage": 0,
			"sales_team_count": 0
		}
		for user in users:
			report_data[mode][user] = 0

	conditions = ""
	if filters.get("pos_profile"):
		conditions += " AND si.pos_profile = %(pos_profile)s"

	raw_data = frappe.db.sql(f"""
		SELECT 
			sip.mode_of_payment,
			si.owner as user,
			SUM(sip.amount) as amount,
			COUNT(DISTINCT si.name) as invoice_count
		FROM 
			`tabSales Invoice` si
		JOIN 
			`tabSales Invoice Payment` sip ON sip.parent = si.name
		WHERE 
			si.docstatus = 1
			AND si.is_pos = 1
			AND si.status IN ('Paid', 'Partially Paid', 'Credit Note Issued', 'Return')
			AND si.posting_date = '{today()}'
			{conditions}
		GROUP BY 
			sip.mode_of_payment, si.owner
	""", filters, as_dict=1)

	invoices = frappe.db.sql(f"""
		SELECT 
			si.name, si.grand_total, sip.mode_of_payment, sip.amount as payment_amount
		FROM 
			`tabSales Invoice` si
		JOIN 
			`tabSales Invoice Payment` sip ON sip.parent = si.name
		WHERE 
			si.docstatus = 1
			AND si.is_pos = 1
			AND si.status IN ('Paid', 'Partially Paid', 'Credit Note Issued', 'Return')
			AND si.posting_date = '{today()}'
			{conditions}
	""", filters, as_dict=1)

	for inv in invoices:
		sales_team = frappe.get_all("Sales Team", filters={"parent": inv.name}, 
			fields=["sales_person", "allocated_amount", "allocated_percentage"])
		
		mode = inv.get("mode_of_payment")
		if mode in report_data and inv.get("grand_total"):
			proportion = inv.get("payment_amount") / inv.get("grand_total")
			
			for st in sales_team:
				if st.sales_person not in report_data[mode]["sales_person"]:
					report_data[mode]["sales_person"].append(st.sales_person)
				
				report_data[mode]["allocated_amount"] += (st.allocated_amount or 0) * proportion
				report_data[mode]["allocated_percentage"] += (st.allocated_percentage or 0)
				report_data[mode]["sales_team_count"] += 1

	returns_without_payments = frappe.db.sql(f"""
		SELECT 
			si.name, si.return_against, si.owner as user, si.grand_total
		FROM 
			`tabSales Invoice` si
		LEFT JOIN 
			`tabSales Invoice Payment` sip ON sip.parent = si.name
		WHERE 
			si.docstatus = 1
			AND si.is_pos = 1
			AND si.is_return = 1
			AND si.posting_date = '{today()}'
			AND sip.name IS NULL
			{conditions}
	""", filters, as_dict=1)

	for ret in returns_without_payments:
		if ret.return_against:
			orig_payments = frappe.get_all("Sales Invoice Payment", 
				filters={"parent": ret.return_against}, 
				fields=["mode_of_payment"])
			
			if orig_payments:
				mode = orig_payments[0].get("mode_of_payment")
				raw_data.append({
					"mode_of_payment": mode,
					"user": ret.user,
					"amount": ret.grand_total, 
					"invoice_count": 0 
				})
	
	for d in raw_data:
		mode = d.get("mode_of_payment")
		if mode in report_data:
			user = d.get("user")
			amount = d.get("amount") or 0
			invoice_count = d.get("invoice_count") or 0

			if user in report_data[mode]:
				report_data[mode][user] += amount
			
			report_data[mode]["total"] += amount
			report_data[mode]["pmt_bill"] += invoice_count

	for mode in report_data:
		report_data[mode]["sales_person"] = ", ".join(report_data[mode]["sales_person"])
		if report_data[mode]["sales_team_count"]:
			report_data[mode]["allocated_percentage"] = report_data[mode]["allocated_percentage"] / report_data[mode]["sales_team_count"]
		else:
			report_data[mode]["allocated_percentage"] = 0
		
	return list(report_data.values())
