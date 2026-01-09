from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver


# =========================
# WATCH
# =========================
class Watch(models.Model):
    name = models.CharField("Название", max_length=255)

    tag = models.CharField(
        "Тег над картинкой",
        max_length=255,
        blank=True,
        help_text="Например: NOIR · AUTOMATIC",
    )

    currency = models.CharField(
        "Валюта",
        max_length=10,
        default="сум",
        help_text="Например: сум, ₽, $, €",
    )

    description = models.TextField("Описание", blank=True)

    price = models.IntegerField(
        "Цена",
        help_text="Хранится как целое число, без копеек",
    )

    badge = models.CharField(
        "Бейдж",
        max_length=50,
        blank=True,
        help_text='Например: "Bestseller", "New", "Limited"',
    )

    image = models.ImageField(
        "Фото",
        upload_to="watches/",
        blank=True,
        null=True,
    )

    is_active = models.BooleanField("Показывать на сайте", default=True)
    is_hero = models.BooleanField("Показывать в hero-блоке", default=False)
    is_featured = models.BooleanField("Показывать в подборке", default=False)

    sort_order = models.PositiveIntegerField(
        "Порядок сортировки",
        default=0,
        help_text="Меньше число — выше в списке",
    )

    class Meta:
        ordering = ["sort_order", "id"]
        verbose_name = "Часы"
        verbose_name_plural = "Часы"

    def __str__(self):
        return self.name


# =========================
# USER PROFILE
# =========================
class UserProfile(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    location = models.CharField("Локация", max_length=255, blank=True)
    phone = models.CharField("Телефон", max_length=32, blank=True)

    def __str__(self):
        return f"Профиль {self.user.username}"


@receiver(post_save, sender=User)
def create_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_profile(sender, instance, **kwargs):
    if hasattr(instance, "profile"):
        instance.profile.save()


# =========================
# ORDER
# =========================
class Order(models.Model):
    STATUS_CHOICES = [
        ("awaiting_payment", "Ожидает оплаты"),
        ("new", "Оплачен (на проверке)"),
        ("accepted", "Оплата подтверждена"),
        ("in_progress", "В пути"),
        ("delivered", "Доставлен"),
        ("cancelled", "Отменён"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Пользователь",
    )

    created_at = models.DateTimeField("Создан", auto_now_add=True)

    location = models.CharField("Локация (адрес текстом)", max_length=255)
    latitude = models.FloatField("Широта", null=True, blank=True)
    longitude = models.FloatField("Долгота", null=True, blank=True)

    phone = models.CharField("Телефон", max_length=32)

    status = models.CharField(
        "Статус",
        max_length=30,
        choices=STATUS_CHOICES,
        default="awaiting_payment",  # ✅ ИСПРАВЛЕНО
    )

    payment_screenshot = models.ImageField(
        "Скриншот оплаты",
        upload_to="payments/",
        null=True,
        blank=True,
    )

    admin_comment = models.TextField(
        "Комментарий администратора",
        blank=True,
        help_text="Например: Оплата подтверждена / Не совпала сумма",
    )

    uzum_payment_id = models.CharField(
        "ID оплаты Uzum",
        max_length=100,
        blank=True,
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Заказ"
        verbose_name_plural = "Заказы"

    def __str__(self):
        return f"Заказ #{self.id} ({self.get_status_display()})"

    @property
    def total_amount(self):
        return sum(item.total_price for item in self.items.all())


# =========================
# ORDER ITEM
# =========================
class OrderItem(models.Model):
    order = models.ForeignKey(
        Order,
        related_name="items",
        on_delete=models.CASCADE,
        verbose_name="Заказ",
    )
    watch = models.ForeignKey(
        Watch,
        on_delete=models.PROTECT,
        verbose_name="Часы",
    )
    quantity = models.PositiveIntegerField("Количество", default=1)
    price = models.DecimalField(
        "Цена за единицу",
        max_digits=10,
        decimal_places=2,
    )

    class Meta:
        verbose_name = "Позиция заказа"
        verbose_name_plural = "Позиции заказа"

    def __str__(self):
        return f"{self.watch.name} x {self.quantity}"

    @property
    def total_price(self):
        return self.price * self.quantity
