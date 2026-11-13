def discounted_amount(price_minor: int, discount_percent: int) -> int:
    if price_minor < 0:
        raise ValueError("price_minor cannot be negative")
    if not 0 <= discount_percent <= 100:
        raise ValueError("discount_percent must be between 0 and 100")

    return (price_minor * (100 - discount_percent) + 50) // 100
