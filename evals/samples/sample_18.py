def total_amount(orders):
    total = 0
    for o in orders:
        total += o["amount"]
    return total
