# Copyright (c) 2025, BrainWise and contributors
# For license information, please see license.txt

import unittest
from unittest.mock import Mock, patch

from pos_next.api.customers import (
	_get_customer_assignment_context,
	create_customer,
	get_customers,
	get_default_loyalty_program_from_settings,
	set_contact_primary_email,
	set_contact_primary_mobile,
	sync_primary_contact,
	update_customer,
)


class TestCustomersAPI(unittest.TestCase):
	@patch("pos_next.api.customers.frappe.logger")
	@patch("pos_next.api.customers.frappe.get_all")
	@patch("pos_next.api.customers.frappe.db.rollback")
	def test_get_customers_applies_search_term_filters(self, mock_db, mock_get_all, mock_logger):
		mock_logger.return_value = Mock()
		mock_get_all.return_value = []

		get_customers(search_term="john", limit=10)

		mock_get_all.assert_called_once()
		kwargs = mock_get_all.call_args.kwargs
		self.assertEqual(kwargs["filters"], {"disabled": 0})
		self.assertEqual(
			kwargs["or_filters"],
			[
				["Customer", "name", "like", "%john%"],
				["Customer", "customer_name", "like", "%john%"],
				["Customer", "mobile_no", "like", "%john%"],
				["Customer", "email_id", "like", "%john%"],
			],
		)

	@patch("pos_next.api.customers.frappe.db.rollback")
	def test_get_default_loyalty_program_from_settings_uses_explicit_pos_profile(self, mock_db):
		mock_db.get_value.return_value = "LOYALTY-A"

		result = get_default_loyalty_program_from_settings(pos_profile="POS-A")

		self.assertEqual(result, "LOYALTY-A")
		mock_db.get_value.assert_called_once_with(
			"POS Settings",
			{"enabled": 1, "pos_profile": "POS-A"},
			"default_loyalty_program",
		)

	@patch("pos_next.api.customers.frappe.get_cached_value")
	@patch("pos_next.api.customers.frappe.get_all")
	def test_get_default_loyalty_program_from_settings_skips_ambiguous_company_context(
		self,
		mock_get_all,
		mock_get_cached_value,
	):
		mock_get_all.return_value = [
			Mock(pos_profile="POS-1", default_loyalty_program="LOYALTY-A"),
			Mock(pos_profile="POS-2", default_loyalty_program="LOYALTY-B"),
		]
		mock_get_cached_value.side_effect = ["Company A", "Company A"]

		result = get_default_loyalty_program_from_settings(company="Company A")

		self.assertIsNone(result)

	@patch(
		"pos_next.api.customers.frappe.local",
		new=Mock(form_dict={"company": "Company A", "pos_profile": "POS-A"}),
	)
	@patch(
		"pos_next.api.customers.frappe.flags",
		new=Mock(pos_next_customer_company=None, pos_next_customer_pos_profile=None),
	)
	def test_get_customer_assignment_context_uses_request_context(self):
		company, pos_profile = _get_customer_assignment_context()

		self.assertEqual(company, "Company A")
		self.assertEqual(pos_profile, "POS-A")

	@patch(
		"pos_next.api.customers.frappe.flags",
		new=Mock(pos_next_customer_company=None, pos_next_customer_pos_profile=None),
	)
	@patch("pos_next.api.customers.resolve_existing_customer", return_value=None)
	@patch("pos_next.api.customers.frappe.get_doc")
	@patch("pos_next.api.customers.get_default_loyalty_program_from_settings")
	@patch("pos_next.api.customers.frappe.has_permission")
	def test_create_customer_uses_pos_profile_for_loyalty_assignment(
		self,
		mock_has_permission,
		mock_get_loyalty,
		mock_get_doc,
		_mock_resolve,
	):
		mock_has_permission.return_value = True
		mock_get_loyalty.return_value = "LOYALTY-A"

		customer_doc = Mock()
		customer_doc.as_dict.return_value = {"name": "CUST-0001", "loyalty_program": "LOYALTY-A"}
		mock_get_doc.return_value = customer_doc

		result = create_customer(
			customer_name="John Doe",
			customer_group="Individual",
			territory="All Territories",
			pos_profile="POS-A",
		)

		mock_get_loyalty.assert_called_once_with(company=None, pos_profile="POS-A")
		customer_doc.insert.assert_called_once_with()
		self.assertEqual(result["loyalty_program"], "LOYALTY-A")


	@patch(
		"pos_next.api.customers.frappe.flags",
		new=Mock(pos_next_customer_company=None, pos_next_customer_pos_profile=None),
	)
	@patch("pos_next.api.customers.resolve_existing_customer")
	@patch("pos_next.api.customers.frappe.get_doc")
	@patch("pos_next.api.customers.get_default_loyalty_program_from_settings")
	@patch("pos_next.api.customers.validate_customer_create")
	@patch("pos_next.api.customers.frappe.has_permission")
	def test_create_customer_returns_existing_without_insert(
		self,
		mock_has_permission,
		_mock_validate,
		mock_get_loyalty,
		mock_get_doc,
		mock_resolve,
	):
		mock_has_permission.return_value = True
		existing = {
			"name": "CUST-2026-68541",
			"customer_name": "ZZ Test POSSync1",
			"mobile_no": "+964-7754539344",
			"email_id": "pos.9647754539344@pos.miraaya",
		}
		mock_resolve.return_value = {
			"message": "A customer with this email already exists.",
			"existing_customer": existing,
		}

		result = create_customer(
			customer_name="ZZ Test Dup Email Warn",
			email_id="pos.9647754539344@pos.miraaya",
			mobile_no="+964-7011998877",
			customer_group="Individual",
			territory="All Territories",
		)

		self.assertTrue(result["already_exists"])
		self.assertEqual(result["message"], "A customer with this email already exists.")
		self.assertEqual(result["existing_customer"]["name"], "CUST-2026-68541")
		mock_get_loyalty.assert_not_called()
		mock_get_doc.assert_not_called()

	@patch(
		"pos_next.api.customers.frappe.flags",
		new=Mock(pos_next_customer_company=None, pos_next_customer_pos_profile=None),
	)
	@patch("pos_next.api.customers.resolve_existing_customer")
	@patch("pos_next.api.customers.frappe.db.rollback")
	@patch("pos_next.api.customers.after_customer_insert")
	@patch("pos_next.api.customers.prepare_customer_doc", return_value=True)
	@patch("pos_next.api.customers.frappe.get_doc")
	@patch("pos_next.api.customers.get_default_loyalty_program_from_settings")
	@patch("pos_next.api.customers.validate_customer_create")
	@patch("pos_next.api.customers.frappe.has_permission")
	def test_create_customer_rolls_back_when_existing_found_after_insert(
		self,
		mock_has_permission,
		_mock_validate,
		mock_get_loyalty,
		mock_get_doc,
		_mock_prepare,
		mock_after_insert,
		mock_rollback,
		mock_resolve,
	):
		from pos_next.integrations.registry import ExistingCustomerFound

		mock_has_permission.return_value = True
		mock_get_loyalty.return_value = None
		mock_resolve.side_effect = [
			None,
			{
				"message": "A customer with this phone already exists.",
				"existing_customer": {
					"name": "CUST-2026-68541",
					"customer_name": "ZZ Test POSSync1",
					"mobile_no": "+964-7754539344",
				},
			},
		]
		customer_doc = Mock()
		mock_get_doc.return_value = customer_doc
		mock_after_insert.side_effect = ExistingCustomerFound(
			"A customer with this phone already exists."
		)

		result = create_customer(
			customer_name="Someone Else",
			mobile_no="+964-7754539344",
			customer_group="Individual",
			territory="All Territories",
		)

		mock_rollback.assert_called_once_with()
		self.assertTrue(result["already_exists"])
		self.assertEqual(result["message"], "A customer with this phone already exists.")
		self.assertEqual(result["existing_customer"]["name"], "CUST-2026-68541")


	@patch(
		"pos_next.api.customers.frappe.flags",
		new=Mock(pos_next_customer_company=None, pos_next_customer_pos_profile=None),
	)
	@patch("pos_next.api.customers.resolve_existing_customer")
	@patch("pos_next.api.customers.frappe.get_doc")
	@patch("pos_next.api.customers.get_default_loyalty_program_from_settings")
	@patch("pos_next.api.customers.validate_customer_create")
	@patch("pos_next.api.customers.frappe.has_permission")
	def test_create_customer_returns_existing_phone_without_insert(
		self,
		mock_has_permission,
		_mock_validate,
		mock_get_loyalty,
		mock_get_doc,
		mock_resolve,
	):
		mock_has_permission.return_value = True
		existing = {
			"name": "CUST-2026-68541",
			"customer_name": "ZZ Test POSSync1",
			"mobile_no": "+964-7754539344",
			"email_id": "pos.9647754539344@pos.miraaya",
		}
		mock_resolve.return_value = {
			"message": "A customer with this phone already exists.",
			"existing_customer": existing,
		}

		result = create_customer(
			customer_name="ZZ Test Dup Phone",
			email_id="other@example.com",
			mobile_no="+964-7754539344",
			customer_group="Individual",
			territory="All Territories",
		)

		self.assertTrue(result["already_exists"])
		self.assertEqual(result["message"], "A customer with this phone already exists.")
		self.assertEqual(result["existing_customer"]["name"], "CUST-2026-68541")
		mock_get_loyalty.assert_not_called()
		mock_get_doc.assert_not_called()

	@patch(
		"pos_next.api.customers.frappe.flags",
		new=Mock(pos_next_customer_company=None, pos_next_customer_pos_profile=None),
	)
	@patch("pos_next.api.customers.resolve_existing_customer", return_value=None)
	@patch("pos_next.api.customers.frappe.db.rollback")
	@patch("pos_next.api.customers.after_customer_insert")
	@patch("pos_next.api.customers.prepare_customer_doc", return_value=True)
	@patch("pos_next.api.customers.frappe.get_doc")
	@patch("pos_next.api.customers.get_default_loyalty_program_from_settings")
	@patch("pos_next.api.customers.validate_customer_create")
	@patch("pos_next.api.customers.frappe.has_permission")
	def test_create_customer_rolls_back_duplicate_email_after_insert(
		self,
		mock_has_permission,
		_mock_validate,
		mock_get_loyalty,
		mock_get_doc,
		_mock_prepare,
		mock_after_insert,
		mock_rollback,
		_mock_resolve,
	):
		from pos_next.integrations.registry import ExistingCustomerFound

		mock_has_permission.return_value = True
		mock_get_loyalty.return_value = None
		existing = {
			"name": "CUST-2026-68541",
			"customer_name": "ZZ Test POSSync1",
			"email_id": "pos.9647754539344@pos.miraaya",
		}
		customer_doc = Mock()
		customer_doc.name = "CUST-NEW"
		mock_get_doc.return_value = customer_doc
		mock_after_insert.side_effect = ExistingCustomerFound(
			"A customer with this email already exists.",
			existing_customer=existing,
		)

		result = create_customer(
			customer_name="Someone Else",
			email_id="pos.9647754539344@pos.miraaya",
			customer_group="Individual",
			territory="All Territories",
		)

		mock_rollback.assert_called_once_with()
		self.assertTrue(result["already_exists"])
		self.assertEqual(result["message"], "A customer with this email already exists.")
		self.assertEqual(result["existing_customer"]["name"], "CUST-2026-68541")
		self.assertNotEqual(result.get("name"), "CUST-NEW")



class _Row(dict):
	def __getattr__(self, key):
		try:
			return self[key]
		except KeyError as exc:
			raise AttributeError(key) from exc

	def __setattr__(self, key, value):
		self[key] = value


class _Contact:
	def __init__(self, email="old@example.com", mobile="+964-7000000000"):
		self.email_ids = [_Row(email_id=email, is_primary=1)]
		self.phone_nos = [_Row(phone=mobile, is_primary_mobile_no=1)]
		self.email_id = email
		self.mobile_no = mobile
		self.first_name = "Old"
		self.last_name = "Name"
		self.saved = False

	def append(self, field, values):
		row = _Row(**values)
		getattr(self, field).append(row)
		return row

	def remove(self, row):
		for field in ("email_ids", "phone_nos"):
			rows = getattr(self, field)
			if row in rows:
				rows.remove(row)

	def save(self, ignore_permissions=False):
		self.saved = True


class TestContactPrimaryHelpers(unittest.TestCase):
	def test_set_contact_primary_email_replaces_existing_primary(self):
		contact = _Contact(email="old@example.com")
		changed = set_contact_primary_email(contact, "new@example.com")
		self.assertTrue(changed)
		self.assertEqual(len(contact.email_ids), 1)
		self.assertEqual(contact.email_ids[0].email_id, "new@example.com")
		self.assertEqual(contact.email_ids[0].is_primary, 1)

	def test_set_contact_primary_mobile_replaces_existing_primary(self):
		contact = _Contact(mobile="+964-7000000000")
		changed = set_contact_primary_mobile(contact, "+964-7111111111")
		self.assertTrue(changed)
		self.assertEqual(len(contact.phone_nos), 1)
		self.assertEqual(contact.phone_nos[0].phone, "+964-7111111111")
		self.assertEqual(contact.phone_nos[0].is_primary_mobile_no, 1)


class TestUpdateCustomer(unittest.TestCase):
	def setUp(self):
		# @frappe.whitelist() reads frappe.local.flags.in_test
		import frappe
		from types import SimpleNamespace
		if not hasattr(frappe.local, "flags"):
			frappe.local.flags = SimpleNamespace(in_test=True)
		else:
			frappe.local.flags.in_test = True

	def _customer_doc(self):
		doc = Mock()
		doc.name = "CUST-2026-68545"
		doc.customer_name = "ZZ Test"
		doc.email_id = "old@example.com"
		doc.mobile_no = "+964-7000000000"
		doc.customer_primary_contact = "CONTACT-1"
		doc.customer_group = "Individual"
		doc.territory = "All Territories"
		doc.custom_first_name = "ZZ"
		doc.custom_last_name = "Test"
		doc.custom_email = "old@example.com"
		doc.custom_is_publish = 1
		doc.get = lambda key, default=None: getattr(doc, key, default)
		doc.has_permission.return_value = True
		doc.as_dict.return_value = {"name": doc.name, "customer_name": "ZZ Test New", "email_id": "new@example.com"}
		return doc

	@patch("pos_next.api.customers.resolve_existing_customer", return_value=None)
	@patch("pos_next.api.customers.get_customer_sync_error", return_value=None)
	@patch("pos_next.api.customers.after_customer_update")
	@patch("pos_next.api.customers.sync_primary_contact")
	@patch("pos_next.api.customers.validate_customer_create")
	@patch("pos_next.api.customers.frappe.get_hooks", return_value=["magento.after_update"])
	@patch("pos_next.api.customers.frappe.get_meta")
	@patch("pos_next.api.customers.frappe.get_doc")
	@patch("pos_next.api.customers.frappe.has_permission", return_value=True)
	def test_update_customer_syncs_contact_then_saves(
		self,
		_perm,
		mock_get_doc,
		mock_get_meta,
		_hooks,
		mock_validate,
		mock_sync,
		mock_after,
		_sync_error,
		mock_resolve,
	):
		customer = self._customer_doc()
		mock_get_doc.return_value = customer
		mock_get_meta.return_value = Mock(has_field=lambda name: True)
		flags = Mock(skip_magento_customer_sync=False)
		with patch("pos_next.api.customers.frappe.flags", flags):
			result = update_customer(
				name="CUST-2026-68545",
				customer_name="ZZ Test New",
				email_id="new@example.com",
				mobile_no="+964-7111111111",
				custom_first_name="ZZ",
				custom_last_name="Test New",
			)

		mock_sync.assert_called_once()
		kwargs = mock_sync.call_args.kwargs
		self.assertEqual(kwargs["email_id"], "new@example.com")
		self.assertEqual(kwargs["mobile_no"], "+964-7111111111")
		self.assertEqual(kwargs["first_name"], "ZZ")
		self.assertEqual(kwargs["last_name"], "Test New")
		customer.save.assert_called_once_with()
		self.assertEqual(customer.email_id, "new@example.com")
		self.assertEqual(customer.custom_email, "new@example.com")
		self.assertEqual(customer.mobile_no, "+964-7111111111")
		self.assertEqual(customer.custom_first_name, "ZZ")
		self.assertEqual(customer.custom_last_name, "Test New")
		self.assertTrue(flags.skip_magento_customer_sync is False)
		mock_after.assert_called_once()
		self.assertEqual(result["email_id"], "new@example.com")
		customer.reload.assert_called_once_with()
		# The changed email/phone is checked against other customers, never this one.
		self.assertEqual(mock_resolve.call_args.kwargs["exclude_customer"], "CUST-2026-68545")

	@patch("pos_next.api.customers.frappe.get_doc")
	def test_sync_primary_contact_updates_and_saves_contact(self, mock_get_doc):
		customer = self._customer_doc()
		contact = _Contact()
		mock_get_doc.return_value = contact
		changed = sync_primary_contact(
			customer,
			email_id="new@example.com",
			mobile_no="+964-7111111111",
			first_name="New",
			last_name="Person",
		)
		self.assertTrue(changed)
		self.assertTrue(contact.saved)
		self.assertEqual(contact.email_ids[0].email_id, "new@example.com")
		self.assertEqual(contact.phone_nos[0].phone, "+964-7111111111")
		self.assertEqual(contact.first_name, "New")
		self.assertEqual(contact.last_name, "Person")
		self.assertEqual(contact.email_id, "new@example.com")
		self.assertEqual(contact.mobile_no, "+964-7111111111")

	@patch("pos_next.api.customers.resolve_existing_customer", return_value=None)
	@patch("pos_next.api.customers.get_customer_sync_error", return_value=None)
	@patch("pos_next.api.customers.after_customer_update")
	@patch("pos_next.api.customers.sync_primary_contact")
	@patch("pos_next.api.customers.validate_customer_create")
	@patch("pos_next.api.customers.frappe.get_hooks", return_value=["magento.after_update"])
	@patch("pos_next.api.customers.frappe.get_meta")
	@patch("pos_next.api.customers.frappe.get_doc")
	@patch("pos_next.api.customers.frappe.has_permission", return_value=True)
	def test_update_customer_raises_magento_rejection(
		self,
		_perm,
		mock_get_doc,
		mock_get_meta,
		_hooks,
		_validate,
		mock_sync,
		mock_after,
		_sync_error,
		mock_resolve,
	):
		from pos_next.integrations.registry import ExternalCustomerRejected

		customer = self._customer_doc()
		mock_get_doc.return_value = customer
		mock_get_meta.return_value = Mock(has_field=lambda name: True)
		mock_after.side_effect = ExternalCustomerRejected(
			"A customer with the same email already exists in an associated website."
		)
		flags = Mock(skip_magento_customer_sync=False)
		with patch("pos_next.api.customers.frappe.flags", flags):
			with self.assertRaises(ExternalCustomerRejected) as ctx:
				update_customer(
					name="CUST-2026-68545",
					email_id="taken@example.com",
					custom_first_name="ZZ",
					custom_last_name="Test",
				)
		self.assertIn("already exists", str(ctx.exception))
		customer.save.assert_called_once_with()
		# Flag must be restored even when Magento rejects the update.
		self.assertFalse(flags.skip_magento_customer_sync)
