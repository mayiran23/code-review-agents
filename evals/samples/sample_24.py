def calc_total(items, tax_rate):
    return sum(i["price"] for i in items) * (1 + tax_rate)
