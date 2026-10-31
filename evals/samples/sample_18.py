def total_amount(orders):
    total = 0
    for order in orders:
        total += order["amount"]
    return total
