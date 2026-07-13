import pytest
from decimal import Decimal
from src.services.units_service import WeightFormatter, UnitsService

class TestWeightFormatter:
    def test_to_decimal_from_int(self):
        assert WeightFormatter.to_decimal(725) == Decimal("725")

    def test_to_decimal_from_float(self):
        assert WeightFormatter.to_decimal(72.5) == Decimal("72.5")

    def test_to_decimal_from_string(self):
        assert WeightFormatter.to_decimal("72.50") == Decimal("72.50")

    def test_to_decimal_from_decimal(self):
        d = Decimal("72.5")
        assert WeightFormatter.to_decimal(d) == d

    def test_to_storage(self):
        assert WeightFormatter.to_storage(72.5) == Decimal("72.5")

    def test_from_storage(self):
        assert WeightFormatter.from_storage(Decimal("72.5")) == Decimal("72.5")

    def test_display(self):
        assert WeightFormatter.display(Decimal("72.5")) == "72.5kg"

    def test_display_one_decimal(self):
        assert WeightFormatter.display_one_decimal(Decimal("72.50")) == "72.5kg"

    def test_invalid_weight(self):
        with pytest.raises(ValueError):
            WeightFormatter.to_decimal("not-a-number")

class TestUnitsService:
    def test_weight_formatter_access(self):
        assert isinstance(UnitsService().weight, WeightFormatter)
