from __future__ import annotations

from unittest.mock import patch

from frappe.tests.utils import FrappeTestCase

from pos_next.pos_next.utils.pos_closing_print import (
    _collect_parent_targets,
    get_items_sold,
)


class TestPOSClosingPrint(FrappeTestCase):
    def test_collect_parent_targets_prefers_sales_invoice(self):
        targets = _collect_parent_targets(
            [
                {"sales_invoice": "SINV-0001", "pos_invoice": "POSINV-0001"},
                {"pos_invoice": "POSINV-0002"},
                {"sales_invoice": "SINV-0002"},
            ]
        )

        self.assertEqual(
            targets,
            {
                ("SINV-0001", "Sales Invoice"),
                ("POSINV-0002", "POS Invoice"),
                ("SINV-0002", "Sales Invoice"),
            },
        )

    @patch("pos_next.pos_next.utils.pos_closing_print._fetch_items_for_targets")
    def test_get_items_sold_returns_float_values(self, mock_fetch):
        mock_fetch.return_value = [
            {
                "item_code": "ITEM-001",
                "item_name": "Latte",
                "qty": "2",
                "amount": "150.50",
            }
        ]

        doc = {"pos_transactions": [{"sales_invoice": "SINV-0001"}]}
        result = get_items_sold(doc)

        self.assertEqual(
            result,
            [
                {
                    "item_code": "ITEM-001",
                    "item_name": "Latte",
                    "qty": 2.0,
                    "amount": 150.5,
                }
            ],
        )
        mock_fetch.assert_called_once_with({("SINV-0001", "Sales Invoice")})

    @patch("pos_next.pos_next.utils.pos_closing_print._fetch_items_for_targets")
    def test_get_items_sold_returns_empty_when_no_transactions(self, mock_fetch):
        doc = {"pos_transactions": []}
        result = get_items_sold(doc)

        self.assertEqual(result, [])
        mock_fetch.assert_not_called()
