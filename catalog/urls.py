from django.urls import path
from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("catalog/", views.catalog_page, name="catalog"),

    # API часов
    path("api/watches/hero/", views.hero_watch, name="hero_watch"),
    path("api/watches/featured/", views.watches_featured, name="watches_featured"),
    path("api/watches/all/", views.watches_all, name="watches_all"),

    # корзина
    path("cart/", views.cart_detail, name="cart_detail"),
    path("cart/add/<int:watch_id>/", views.cart_add, name="cart_add"),
    path("cart/remove/<int:watch_id>/", views.cart_remove, name="cart_remove"),

    # оформление и оплата
    path("checkout/", views.checkout, name="checkout"),
    path("payment/<int:order_id>/", views.payment_page, name="payment_page"),  # ✅ ВАЖНО
    path("payment/callback/", views.payment_callback, name="payment_callback"),

    # аккаунт
    path("account/", views.account, name="account"),

]
