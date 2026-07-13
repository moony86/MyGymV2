from decimal import Decimal, InvalidOperation
from typing import Union

class WeightFormatter:
    @staticmethod
    def to_decimal(value: Union[int, float, str, Decimal]) -> Decimal:
        if isinstance(value, Decimal):
            return value
        try:
            return Decimal(str(value))
        except InvalidOperation:
            raise ValueError(f"Invalid weight value: {value}")

    @staticmethod
    def to_storage(kg: Union[float, Decimal]) -> Decimal:
        return WeightFormatter.to_decimal(kg)

    @staticmethod
    def from_storage(weight: Union[Decimal, int, float]) -> Decimal:
        return WeightFormatter.to_decimal(weight)

    @staticmethod
    def display(weight: Union[Decimal, int, float]) -> str:
        d = WeightFormatter.to_decimal(weight)
        return f"{d}kg"

    @staticmethod
    def display_one_decimal(weight: Union[Decimal, int, float]) -> str:
        d = WeightFormatter.to_decimal(weight)
        return f"{d.quantize(Decimal('0.1'))}kg"

class UnitsService:
    weight = WeightFormatter()
