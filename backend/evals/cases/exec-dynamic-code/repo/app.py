NAMESPACE_SETUP = "total = price * quantity"


def compute_total(price: int, quantity: int) -> int:
    scope = {"price": price, "quantity": quantity}
    exec(NAMESPACE_SETUP, {}, scope)
    return int(scope["total"])
