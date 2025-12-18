from decimal import Decimal
from .models import Watch

CART_SESSION_ID = "cart"


class Cart:
    def __init__(self, request):
        self.session = request.session
        cart = self.session.get(CART_SESSION_ID)
        if not cart:
            cart = self.session[CART_SESSION_ID] = {}
        self.cart = cart

    def add(self, watch_id, quantity=1, update_quantity=False):
        watch = Watch.objects.get(id=watch_id)
        watch_id_str = str(watch_id)

        if watch_id_str not in self.cart:
            self.cart[watch_id_str] = {
                "quantity": 0,
                "price": str(watch.price),  # Watch.price — IntegerField
            }

        if update_quantity:
            self.cart[watch_id_str]["quantity"] = quantity
        else:
            self.cart[watch_id_str]["quantity"] += quantity

        self.save()

    def remove(self, watch_id):
        watch_id_str = str(watch_id)
        if watch_id_str in self.cart:
            del self.cart[watch_id_str]
            self.save()

    def clear(self):
        self.session[CART_SESSION_ID] = {}
        self.session.modified = True

    def save(self):
        self.session[CART_SESSION_ID] = self.cart
        self.session.modified = True

    def __iter__(self):
        watch_ids = self.cart.keys()
        watches = Watch.objects.filter(id__in=watch_ids)

        for watch in watches:
            item = self.cart[str(watch.id)]
            item["watch"] = watch
            item["price"] = Decimal(item["price"])
            item["total_price"] = item["price"] * item["quantity"]
            yield item

    def get_total_price(self):
        total = Decimal("0")
        for item in self:
            total += item["total_price"]
        return total
