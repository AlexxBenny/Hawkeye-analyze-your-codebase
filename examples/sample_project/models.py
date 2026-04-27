"""Domain models."""


class User:
    def __init__(self, name: str, email: str):
        self.name = name
        self.email = email

    def display_name(self) -> str:
        return self.name.title()


class Product:
    def __init__(self, name: str, price: float):
        self.name = name
        self.price = price

    def is_affordable(self, budget: float) -> bool:
        return self.price <= budget


class Order:
    def __init__(self, user: User, items: list[Product]):
        self.user = user
        self.items = items

    @property
    def total(self) -> float:
        return sum(item.price for item in self.items)
