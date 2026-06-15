from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


MONEY_QUANTIZER = Decimal("0.01")


def quantize_money(value):
    if value is None:
        return None

    decimal_value = value if isinstance(value, Decimal) else Decimal(str(value))
    quantized_value = decimal_value.quantize(MONEY_QUANTIZER, rounding=ROUND_HALF_UP)

    if quantized_value == 0:
        return quantized_value.copy_abs()

    return quantized_value


def format_money(value):
    if value in (None, ""):
        return "0.00"

    try:
        quantized_value = quantize_money(value)
    except (InvalidOperation, TypeError, ValueError):
        return str(value)

    if quantized_value is None:
        return "0.00"

    return format(quantized_value, ".2f")
