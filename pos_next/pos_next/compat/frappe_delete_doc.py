"""Backport linked-doc helpers required by Frappe CRM on Framework < 15.110."""

import frappe
from frappe.model.delete_doc import DocStatus, get_dynamic_link_map


def ensure_delete_doc_linked_helpers():
	"""Expose get_linked_docs / get_dynamic_linked_docs on frappe.model.delete_doc."""
	import frappe.model.delete_doc as delete_doc

	if hasattr(delete_doc, "get_linked_docs") and hasattr(delete_doc, "get_dynamic_linked_docs"):
		return

	delete_doc.get_linked_docs = get_linked_docs
	delete_doc.get_dynamic_linked_docs = get_dynamic_linked_docs


def get_linked_docs(doc, method="Delete") -> list[dict]:
	"""Return documents statically linked to the given document."""
	from frappe.model.rename_doc import get_link_fields

	link_fields = get_link_fields(doc.doctype)
	ignored_doctypes = set()

	if method == "Cancel" and (doc_ignore_flags := doc.get("ignore_linked_doctypes")):
		ignored_doctypes.update(doc_ignore_flags)
	if method == "Delete":
		ignored_doctypes.update(frappe.get_hooks("ignore_links_on_delete"))

	linked_docs = []

	for lf in link_fields:
		link_dt, link_field, issingle = lf["parent"], lf["fieldname"], lf["issingle"]
		if link_dt in ignored_doctypes or (link_field == "amended_from" and method == "Cancel"):
			continue

		try:
			meta = frappe.get_meta(link_dt)
		except frappe.DoesNotExistError:
			frappe.clear_last_message()
			continue

		if issingle:
			if frappe.db.get_single_value(link_dt, link_field) == doc.name:
				linked_docs.append(
					{"doc": doc.name, "reference_doctype": link_dt, "reference_docname": link_dt}
				)
			continue

		fields = ["name", "docstatus"]
		if meta.istable:
			fields.extend(["parent", "parenttype"])

		for item in frappe.db.get_values(link_dt, {link_field: doc.name}, fields, as_dict=True):
			item_parent = getattr(item, "parent", None)
			linked_parent_doctype = item.parenttype if item_parent else link_dt

			if linked_parent_doctype in ignored_doctypes:
				continue

			if method != "Delete" and (method != "Cancel" or not DocStatus(item.docstatus).is_submitted()):
				continue
			if link_dt == doc.doctype and (item_parent or item.name) == doc.name:
				continue

			linked_docs.append(
				{
					"doc": doc.name,
					"reference_doctype": linked_parent_doctype,
					"reference_docname": item_parent or item.name,
				}
			)

	return linked_docs


def get_dynamic_linked_docs(doc, method="Delete") -> list[dict]:
	"""Return documents dynamically linked to the given document."""
	linked_docs = []

	for df in get_dynamic_link_map().get(doc.doctype, []):
		ignore_linked_doctypes = doc.get("ignore_linked_doctypes") or []

		if df.parent in frappe.get_hooks("ignore_links_on_delete") or (
			df.parent in ignore_linked_doctypes and method == "Cancel"
		):
			continue

		meta = frappe.get_meta(df.parent)
		if meta.issingle:
			refdoc = frappe.db.get_singles_dict(df.parent)
			if (
				refdoc.get(df.options) == doc.doctype
				and refdoc.get(df.fieldname) == doc.name
				and (
					(method == "Delete" and not DocStatus(refdoc.docstatus).is_cancelled())
					or (method == "Cancel" and DocStatus(refdoc.docstatus).is_submitted())
				)
			):
				linked_docs.append(
					{
						"doc": doc.name,
						"reference_doctype": df.parent,
						"reference_docname": df.parent,
						"at_position": "",
					}
				)
		else:
			df["table"] = ", `parent`, `parenttype`, `idx`" if meta.istable else ""
			for refdoc in frappe.db.sql(
				"""select `name`, `docstatus` {table} from `tab{parent}` where
				`{options}`=%s and `{fieldname}`=%s""".format(**df),
				(doc.doctype, doc.name),
				as_dict=True,
			):
				if (method == "Delete" and not DocStatus(refdoc.docstatus).is_cancelled()) or (
					method == "Cancel" and DocStatus(refdoc.docstatus).is_submitted()
				):
					reference_doctype = refdoc.parenttype if meta.istable else df.parent
					reference_docname = refdoc.parent if meta.istable else refdoc.name

					if reference_doctype in frappe.get_hooks("ignore_links_on_delete") or (
						reference_doctype in ignore_linked_doctypes and method == "Cancel"
					):
						continue

					linked_docs.append(
						{
							"doc": doc.name,
							"reference_doctype": reference_doctype,
							"reference_docname": reference_docname,
							"at_position": f"at Row: {refdoc.idx}" if meta.istable else "",
						}
					)

	return linked_docs
