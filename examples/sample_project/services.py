"""Business logic services."""

from .models import User, Product, Order


class UserService:
    def __init__(self):
        self._users: list[User] = []

    def register(self, name: str, email: str) -> User:
        user = User(name, email)
        self._users.append(user)
        return user

    def find_by_email(self, email: str) -> User | None:
        for user in self._users:
            if user.email == email:
                return user
        return None


class OrderService:
    def __init__(self, user_service: UserService):
        self._user_service = user_service
        self._orders: list[Order] = []

    def create_order(self, email: str, products: list[Product]) -> Order | None:
        user = self._user_service.find_by_email(email)
        if user is None:
            return None
        order = Order(user, products)
        self._orders.append(order)
        return order

    def get_orders_for(self, email: str) -> list[Order]:
        return [
            o for o in self._orders
            if o.user.email == email
        ]
