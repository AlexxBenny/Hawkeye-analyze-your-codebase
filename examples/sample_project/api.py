"""API layer — depends on services."""

from .services import UserService, OrderService
from .models import Product


def handle_register(name: str, email: str) -> dict:
    svc = UserService()
    user = svc.register(name, email)
    return {"status": "ok", "user": user.display_name()}


def handle_order(email: str, product_names: list[str]) -> dict:
    user_svc = UserService()
    order_svc = OrderService(user_svc)
    products = [Product(name=n, price=9.99) for n in product_names]
    order = order_svc.create_order(email, products)
    if order is None:
        return {"status": "error", "message": "User not found"}
    return {"status": "ok", "total": order.total}
