"""Tests for Pydantic input model validation."""

import pytest
from pydantic import ValidationError

from src.models.schemas import (
    BulkTransactionUpdateInput,
    DeleteTransactionInput,
    ScheduledTransactionFrequency,
    SetCategoryTargetInput,
    TransactionClearedStatus,
    TransactionFlagColor,
    UpdateCategoryMetadataInput,
    UpdateScheduledTransactionInput,
    UpdateTransactionInput,
)


class TestUpdateTransactionInput:
    def test_valid_single_field(self):
        inp = UpdateTransactionInput(
            transaction_description="HEB", memo="new memo"
        )
        assert inp.memo == "new memo"

    def test_valid_multiple_fields(self):
        inp = UpdateTransactionInput(
            transaction_description="HEB",
            memo="note",
            category_name="Dining",
            amount=50.0,
        )
        assert inp.amount == 50.0
        assert inp.category_name == "Dining"

    def test_requires_at_least_one_update_field(self):
        with pytest.raises(ValidationError, match="At least one field"):
            UpdateTransactionInput(transaction_description="HEB")

    def test_requires_transaction_description(self):
        with pytest.raises(ValidationError):
            UpdateTransactionInput(memo="test")  # type: ignore[call-arg]

    def test_flag_color_enum_validation(self):
        inp = UpdateTransactionInput(
            transaction_description="HEB", flag_color="blue"
        )
        assert inp.flag_color == TransactionFlagColor.BLUE

    def test_invalid_flag_color_rejected(self):
        with pytest.raises(ValidationError):
            UpdateTransactionInput(
                transaction_description="HEB", flag_color="pink"
            )

    def test_cleared_enum_validation(self):
        inp = UpdateTransactionInput(
            transaction_description="HEB", cleared="cleared"
        )
        assert inp.cleared == TransactionClearedStatus.CLEARED

    def test_strips_whitespace(self):
        inp = UpdateTransactionInput(
            transaction_description="  HEB  ", memo="  note  "
        )
        assert inp.transaction_description == "HEB"
        assert inp.memo == "note"

    def test_forbids_extra_fields(self):
        with pytest.raises(ValidationError):
            UpdateTransactionInput(
                transaction_description="HEB",
                memo="test",
                unknown_field="bad",  # type: ignore[call-arg]
            )

    def test_memo_empty_string_is_valid(self):
        inp = UpdateTransactionInput(
            transaction_description="HEB", memo=""
        )
        assert inp.memo == ""


class TestScheduledTransactionFrequency:
    def test_valid_frequency(self):
        assert ScheduledTransactionFrequency("monthly") == ScheduledTransactionFrequency.MONTHLY

    def test_invalid_frequency_rejected(self):
        with pytest.raises(ValueError):
            ScheduledTransactionFrequency("biweekly")


class TestUpdateCategoryMetadataInput:
    def test_valid_new_name(self):
        inp = UpdateCategoryMetadataInput(category_name="Groceries", new_name="Food")
        assert inp.new_name == "Food"

    def test_valid_note(self):
        inp = UpdateCategoryMetadataInput(category_name="Groceries", note="Weekly budget")
        assert inp.note == "Weekly budget"

    def test_requires_at_least_one_field(self):
        with pytest.raises(ValidationError, match="At least one"):
            UpdateCategoryMetadataInput(category_name="Groceries")

    def test_strips_whitespace(self):
        inp = UpdateCategoryMetadataInput(
            category_name="  Groceries  ", new_name="  Food  "
        )
        assert inp.category_name == "Groceries"
        assert inp.new_name == "Food"


class TestUpdateScheduledTransactionInput:
    def test_valid_single_field(self):
        inp = UpdateScheduledTransactionInput(
            scheduled_transaction_description="Netflix", amount=20.0
        )
        assert inp.amount == 20.0

    def test_requires_at_least_one_field(self):
        with pytest.raises(ValidationError, match="At least one"):
            UpdateScheduledTransactionInput(
                scheduled_transaction_description="Netflix"
            )

    def test_valid_frequency(self):
        inp = UpdateScheduledTransactionInput(
            scheduled_transaction_description="Netflix", frequency="weekly"
        )
        assert inp.frequency == ScheduledTransactionFrequency.WEEKLY


class TestBulkTransactionUpdateInput:
    def test_approved_true_accepted(self):
        item = BulkTransactionUpdateInput(
            transaction_description="HEB", approved=True
        )
        assert item.approved is True

    def test_approved_false_accepted(self):
        item = BulkTransactionUpdateInput(
            transaction_description="HEB", approved=False
        )
        assert item.approved is False

    def test_approved_none_by_default(self):
        item = BulkTransactionUpdateInput(
            transaction_description="HEB", category_name="Groceries"
        )
        assert item.approved is None

    def test_all_fields_together(self):
        item = BulkTransactionUpdateInput(
            transaction_description="HEB",
            category_name="Groceries",
            memo="weekly",
            approved=True,
        )
        assert item.approved is True
        assert item.category_name == "Groceries"
        assert item.memo == "weekly"

    def test_strips_whitespace(self):
        item = BulkTransactionUpdateInput(
            transaction_description="  HEB  ", approved=True
        )
        assert item.transaction_description == "HEB"

    def test_requires_at_least_one_update_field(self):
        with pytest.raises(ValidationError, match="At least one field"):
            BulkTransactionUpdateInput(transaction_description="HEB")

    def test_forbids_extra_fields(self):
        with pytest.raises(ValidationError):
            BulkTransactionUpdateInput(
                transaction_description="HEB",
                approved=True,
                unknown="bad",  # type: ignore[call-arg]
            )


class TestDeleteTransactionInput:
    def test_valid(self):
        inp = DeleteTransactionInput(transaction_description="HEB")
        assert inp.transaction_description == "HEB"

    def test_strips_whitespace(self):
        inp = DeleteTransactionInput(transaction_description="  HEB  ")
        assert inp.transaction_description == "HEB"


class TestSetCategoryTargetInput:
    def test_valid_target_amount_only(self):
        inp = SetCategoryTargetInput(category_name="Groceries", target_amount=500.0)
        assert inp.target_amount == 500.0
        assert inp.target_date is None
        assert inp.clear_target is False

    def test_valid_target_amount_with_date(self):
        inp = SetCategoryTargetInput(
            category_name="Vacation", target_amount=2000.0, target_date="2026-06-01"
        )
        assert inp.target_amount == 2000.0
        assert inp.target_date == "2026-06-01"

    def test_valid_clear_target(self):
        inp = SetCategoryTargetInput(category_name="Groceries", clear_target=True)
        assert inp.clear_target is True
        assert inp.target_amount is None

    def test_rejects_both_target_and_clear(self):
        with pytest.raises(ValidationError, match="Cannot set both"):
            SetCategoryTargetInput(
                category_name="Groceries", target_amount=500.0, clear_target=True
            )

    def test_rejects_neither_target_nor_clear(self):
        with pytest.raises(ValidationError, match="Either target_amount"):
            SetCategoryTargetInput(category_name="Groceries")

    def test_rejects_date_without_amount(self):
        with pytest.raises(ValidationError, match="target_date requires"):
            SetCategoryTargetInput(
                category_name="Groceries", target_date="2026-06-01", clear_target=True
            )

    def test_rejects_negative_amount(self):
        with pytest.raises(ValidationError):
            SetCategoryTargetInput(category_name="Groceries", target_amount=-100.0)

    def test_rejects_zero_amount(self):
        with pytest.raises(ValidationError):
            SetCategoryTargetInput(category_name="Groceries", target_amount=0)

    def test_strips_whitespace(self):
        inp = SetCategoryTargetInput(
            category_name="  Groceries  ", target_amount=500.0
        )
        assert inp.category_name == "Groceries"

    def test_forbids_extra_fields(self):
        with pytest.raises(ValidationError):
            SetCategoryTargetInput(
                category_name="Groceries",
                target_amount=500.0,
                unknown="bad",  # type: ignore[call-arg]
            )
