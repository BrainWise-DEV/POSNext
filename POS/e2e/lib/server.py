"""Server-side helper for the UIT run-3 Playwright specs (admin setup + verification).

Run from frappe-bench/sites:  ../env/bin/python <this file> <command> '<json args>'
Prints one JSON document on stdout. Never prints secrets.
Every write is appended to CHANGE_LOG (UIT_CHANGE_LOG env, default e2e/artifacts/changes.log)
with the old value, so each change can be restored and audited.
"""

import datetime
import json
import os
import sys

import frappe

SITE = os.environ.get("UIT_SITE", "pos-dev")
HERE = os.path.dirname(os.path.abspath(__file__))
CHANGE_LOG = os.environ.get("UIT_CHANGE_LOG", os.path.join(HERE, "..", "artifacts", "changes.log"))
ERR_PREFIX = "_PNXT_UIT3_"

SII_FIELDS = [
	"name", "idx", "item_code", "qty", "uom", "conversion_factor", "price_list_rate", "rate", "amount",
	"discount_percentage", "discount_amount", "pricing_rules", "is_free_item",
	"posnext_discount_source", "posnext_fnf_discount_amount", "posnext_fnf_percentage",
	"posnext_fnf_program", "posnext_fnf_replaced_discount", "posnext_coupon_code", "posnext_coupon_share",
]
SI_FIELDS = [
	"name", "docstatus", "status", "customer", "pos_profile", "is_pos", "is_return", "return_against",
	"coupon_code", "discount_amount", "additional_discount_percentage", "apply_discount_on",
	"net_total", "total_taxes_and_charges", "grand_total", "rounded_total", "rounding_adjustment",
	"paid_amount", "change_amount", "outstanding_amount", "write_off_amount", "creation", "owner",
	"posa_pos_opening_shift" ,
]


def _log_change(kind, target, old, new):
	os.makedirs(os.path.dirname(CHANGE_LOG), exist_ok=True)
	with open(CHANGE_LOG, "a") as fh:
		fh.write(json.dumps({
			"at": datetime.datetime.now().isoformat(timespec="seconds"), "kind": kind,
			"target": target, "old": old, "new": new,
		}, default=str) + "\n")


def _si_fields():
	meta = frappe.get_meta("Sales Invoice")
	return [f for f in SI_FIELDS if f == "name" or meta.has_field(f) or f in ("docstatus", "creation", "owner")]


def invoice(name):
	si = frappe.db.get_value("Sales Invoice", name, _si_fields(), as_dict=True)
	if not si:
		return {"missing": name}
	items = frappe.get_all("Sales Invoice Item", filters={"parent": name}, fields=SII_FIELDS, order_by="idx")
	pays = frappe.get_all("Sales Invoice Payment", filters={"parent": name}, fields=["mode_of_payment", "amount"], order_by="idx")
	usg = frappe.get_all("Friends and Family Usage", filters={"invoice": name},
		fields=["amount", "qty", "period_key", "is_return", "is_cancelled", "invoice_item"])
	logs = frappe.get_all("Friends and Family Log", filters={"reference_name": name},
		fields=["log_type", "reason", "item_code", "discount_amount", "capped", "cap_hit", "comparison_outcome", "competing_source", "message"],
		order_by="creation")
	otu = frappe.get_all("One Time Customer Offer Usage", filters={"sales_invoice": name}, fields=["name", "pricing_rule", "customer"])
	ois = frappe.get_all("Offline Invoice Sync", filters={"sales_invoice": name}, fields=["offline_id", "status"])
	collected = sum(p.amount for p in pays) - (si.change_amount or 0)
	due = si.rounded_total or si.grand_total
	return {
		"si": si, "items": items, "payments": pays, "usage": usg, "logs": logs, "one_time": otu,
		"offline_sync": ois, "collected": collected, "due": due,
		"paid_equals_due": abs(collected - due) < 0.005 or (due == 0 and not pays),
		"coupon_share_total": sum((i.posnext_coupon_share or 0) for i in items),
	}


def latest(customer=None, since=None, n=5, owner=None):
	f = {}
	if customer:
		f["customer"] = customer
	if since:
		f["creation"] = [">=", since]
	if owner:
		f["owner"] = owner
	return frappe.get_all("Sales Invoice", filters=f, fields=["name", "docstatus", "status", "grand_total", "rounded_total", "is_return", "customer", "creation"], order_by="creation desc", limit=n)


def errors(since):
	import frappe.deferred_insert
	frappe.deferred_insert.save_to_db()
	frappe.db.commit()
	return frappe.get_all("Error Log", filters={"creation": [">=", since]}, fields=["name", "method", "creation", "error"], order_by="creation")


def errors_brief(since):
	return [{"name": e.name, "method": e.method, "head": (e.error or "")[:300]} for e in errors(since)]


def coupons():
	return {c.name: c.used for c in frappe.get_all("POS Coupon", filters={"name": ["like", "UIT-%"]}, fields=["name", "used"])}


def usage_total(customer):
	return frappe.get_all("Friends and Family Usage Total", filters={"customer": customer}, fields=["period_key", "base_amount"])


def get(doctype, name, fields):
	return frappe.db.get_value(doctype, name, fields, as_dict=True)


def set_value(doctype, name, values):
	"""Direct write of scalar fields, logged with old values. Returns the old values."""
	doc = frappe.get_doc(doctype, name)
	old = {k: doc.get(k) for k in values}
	doc.update(values)
	doc.flags.ignore_permissions = True
	doc.save()
	frappe.db.commit()
	_clear()
	_log_change("set", f"{doctype}/{name}", old, values)
	return old


def ff_set(values):
	doc = frappe.get_single("Friends and Family Settings")
	old = {k: doc.get(k) for k in values}
	frappe.set_user("Administrator")
	from pos_next.ui_test_seed import set_ff
	set_ff(**values)
	_log_change("set_ff", "Friends and Family Settings", old, values)
	return old


def ff_reset():
	frappe.set_user("Administrator")
	from pos_next.ui_test_seed import reset_ff
	changed = reset_ff()
	_log_change("reset_ff", "Friends and Family Settings", None, "seeded")
	return {"changed": changed}


def ff_table(field, rows, values=None):
	"""Replace a child table of F&F Settings (rows = list of dicts), plus optional scalars, in ONE save
	(the scope and its table must change together: the settings validate them as a pair)."""
	doc = frappe.get_single("Friends and Family Settings")
	if values:
		doc.update(values)
	old = [{k: v for k, v in r.as_dict().items() if k not in ("name", "parent", "parenttype", "parentfield", "idx", "creation", "modified", "owner", "modified_by", "docstatus", "doctype")} for r in doc.get(field)]
	doc.set(field, [])
	for r in rows:
		doc.append(field, r)
	doc.save(ignore_permissions=True)
	frappe.db.commit()
	_clear()
	_log_change("ff_table", f"F&F Settings.{field}", old, rows)
	return old


def _clear():
	try:
		frappe.get_attr("posnext_promotions.promotions.friends_and_family_eligibility.clear_cache")()
	except Exception:
		try:
			frappe.get_attr("promotions.friends_and_family_eligibility.clear_cache")()
		except Exception:
			pass
	frappe.clear_cache()


def snapshot(path):
	def doc_img(dt, name):
		d = frappe.get_doc(dt, name).as_dict(no_default_fields=True)
		return json.loads(json.dumps(d, default=str))
	img = {
		"ff": doc_img("Friends and Family Settings", "Friends and Family Settings"),
		"pos_settings": {n: doc_img("POS Settings", n) for n in frappe.get_all("POS Settings", filters={"name": ["like", "UIT-%"]}, pluck="name")},
		"profiles": {n: doc_img("POS Profile", n) for n in frappe.get_all("POS Profile", filters={"name": ["like", "UIT-%"]}, pluck="name")},
		"coupons": {n: doc_img("POS Coupon", n) for n in frappe.get_all("POS Coupon", filters={"name": ["like", "UIT-%"]}, pluck="name")},
		"rules": {n: doc_img("Pricing Rule", n) for n in frappe.get_all("Pricing Rule", filters={"name": ["like", "UIT-%"]}, pluck="name")},
	}
	with open(path, "w") as fh:
		json.dump(img, fh, indent=1, sort_keys=True)
	return {"saved": path}


IGNORE = {"modified", "modified_by", "creation", "owner", "name", "used", "idx", "parent", "_user_tags", "_comments", "_liked_by", "_assign"}


def _strip(v):
	if isinstance(v, dict):
		return {k: _strip(x) for k, x in v.items() if k not in IGNORE}
	if isinstance(v, list):
		return [_strip(x) for x in v]
	return v


def diff(path):
	"""Compare the live settings with a snapshot file; returns the differing top-level fields."""
	with open(path) as fh:
		old = json.load(fh)
	tmp = path + ".now"
	snapshot(tmp)
	with open(tmp) as fh:
		now = json.load(fh)
	os.remove(tmp)
	out = []
	for section in old:
		o, n = old[section], now[section]
		if section == "ff":
			o, n = {"ff": o}, {"ff": n}
		for key in set(o):  # docs created by a spec (e.g. UIT-PR-BUY1) are not settings drift
			a, b = _strip(o.get(key) or {}), _strip(n.get(key) or {})
			for f in set(a) | set(b):
				if a.get(f) != b.get(f):
					out.append({"section": section, "doc": key, "field": f, "snapshot": a.get(f), "now": b.get(f)})
	return out


def restore(path, section, docname, fields=None):
	"""Restore fields (or the whole doc incl. child tables) of one snapshot doc."""
	with open(path) as fh:
		old = json.load(fh)
	img = old["ff"] if section == "ff" else old[section][docname]
	dt = {"ff": "Friends and Family Settings", "pos_settings": "POS Settings", "profiles": "POS Profile", "coupons": "POS Coupon", "rules": "Pricing Rule"}[section]
	doc = frappe.get_doc(dt, docname if section != "ff" else dt)
	meta = frappe.get_meta(dt)
	for f in (fields or [df.fieldname for df in meta.fields]):
		df = meta.get_field(f)
		if not df or f in ("used",):
			continue
		if df.fieldtype in frappe.model.table_fields:  # (Table is also in no_value_fields: test it first)
			doc.set(f, [])
			for r in img.get(f) or []:
				doc.append(f, {k: v for k, v in r.items() if k not in ("name", "parent", "parentfield", "parenttype", "idx", "doctype")})
		elif df.fieldtype not in frappe.model.no_value_fields:
			doc.set(f, img.get(f))
	doc.flags.ignore_permissions = True
	doc.save()
	frappe.db.commit()
	_clear()
	_log_change("restore", f"{dt}/{docname}", None, fields or "all")
	return {"restored": f"{dt}/{docname}"}


def drafts(user=None):
	f = {"docstatus": 0, "customer": ["like", "UIT-%"]}
	if user:
		f["owner"] = user
	return frappe.get_all("Sales Invoice", filters=f, fields=["name", "customer", "owner", "grand_total"])


def shifts():
	return frappe.get_all("POS Opening Shift", filters={"pos_profile": ["like", "UIT-%"]}, fields=["name", "user", "pos_profile", "status", "docstatus"])


def py(code):
	"""Ad-hoc admin code: the snippet sets `result`."""
	scope = {"frappe": frappe, "result": None}
	exec(code, scope)
	frappe.db.commit()
	return scope["result"]


COMMANDS = {f.__name__: f for f in (invoice, latest, errors, errors_brief, coupons, usage_total, get, set_value, ff_set, ff_reset, ff_table, snapshot, diff, restore, drafts, shifts, py)}


def main():
	cmd = sys.argv[1]
	args = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
	frappe.init(site=SITE)
	frappe.connect()
	frappe.set_user("Administrator")
	try:
		out = COMMANDS[cmd](**args) if isinstance(args, dict) else COMMANDS[cmd](*args)
		frappe.db.commit()
	finally:
		frappe.destroy()
	sys.stdout.write("\n@@JSON@@" + json.dumps(out, default=str))


if __name__ == "__main__":
	main()
