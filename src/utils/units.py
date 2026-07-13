def display_weight(weight_int: int) -> str:
    """تحويل 725 → '72.5kg'"""
    return f"{weight_int / 10:.1f}kg"

def kg_to_storage(kg: float) -> int:
    return int(kg * 10)