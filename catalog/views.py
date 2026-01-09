import json
import urllib.parse
import urllib.request
import urllib.error
from html import escape

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_POST

from .cart import Cart
from .models import Watch, Order, OrderItem


# =========================
# Регистрация
# =========================

class SignUpForm(UserCreationForm):
    username = forms.CharField(label="Логин", max_length=150)
    phone = forms.CharField(label="Телефон", max_length=32, required=False)

    class Meta:
        model = User
        fields = ("username", "password1", "password2", "phone")


def signup(request):
    """
    После успешной регистрации НЕ логиним автоматически,
    а отправляем на страницу логина.
    """
    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()

            phone = form.cleaned_data.get("phone", "")
            if hasattr(user, "profile"):
                user.profile.phone = phone
                user.profile.save()

            return redirect("login")
    else:
        form = SignUpForm()

    return render(request, "registration/signup.html", {"form": form})


# =========================
# Страницы
# =========================

@ensure_csrf_cookie
def index(request):
    return render(request, "index.html")


@ensure_csrf_cookie
def catalog_page(request):
    return render(request, "catalog.html")


# =========================
# API часов
# =========================

def _serialize_watch(w: Watch) -> dict:
    return {
        "id": w.id,
        "name": w.name,
        "tag": w.tag,
        "description": w.description,
        "price": w.price,
        "currency": w.currency,
        "badge": w.badge,
        "image_url": w.image.url if w.image else "",
    }


def hero_watch(request):
    watch = (
        Watch.objects.filter(is_active=True, is_hero=True)
        .order_by("sort_order", "id")
        .first()
    )
    if not watch:
        return JsonResponse({"item": None})
    return JsonResponse({"item": _serialize_watch(watch)})


def watches_featured(request):
    watches = (
        Watch.objects.filter(is_active=True, is_featured=True)
        .order_by("sort_order", "id")[:3]
    )
    return JsonResponse({"items": [_serialize_watch(w) for w in watches]})


def watches_all(request):
    watches = Watch.objects.filter(is_active=True).order_by("sort_order", "id")
    return JsonResponse({"items": [_serialize_watch(w) for w in watches]})


# =========================
# Корзина
# =========================

@require_POST
def cart_add(request, watch_id):
    # ✅ НЕЛЬЗЯ покупать без входа
    if not request.user.is_authenticated:
        messages.warning(
            request,
            "Сначала войдите или зарегистрируйтесь, чтобы купить товар."
        )
        return redirect(
            f"{reverse('login')}?next={request.META.get('HTTP_REFERER', '/catalog/')}"
        )

    cart = Cart(request)
    quantity = int(request.POST.get("quantity", 1))
    update = request.POST.get("update") == "1"
    cart.add(watch_id=watch_id, quantity=quantity, update_quantity=update)
    return redirect("cart_detail")


def cart_remove(request, watch_id):
    cart = Cart(request)
    cart.remove(watch_id)
    return redirect("cart_detail")


def cart_detail(request):
    cart = Cart(request)
    form_initial = {}

    if request.user.is_authenticated and hasattr(request.user, "profile"):
        form_initial = {
            "location": request.user.profile.location,
            "phone": request.user.profile.phone,
        }

    return render(request, "cart.html", {"cart": cart, "errors": {}, "form": form_initial})


# =========================
# Telegram helper
# =========================

def tg_api(method: str, payload: dict):
    bot_token = getattr(settings, "TELEGRAM_BOT_TOKEN", None)
    if not bot_token:
        print("❌ TELEGRAM_BOT_TOKEN not set")
        return {"ok": False, "error": "no_bot_token"}

    url = f"https://api.telegram.org/bot{bot_token}/{method}"
    data = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data)

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        print("❌ TELEGRAM API ERROR:", e.code, body)
        return {"ok": False, "error_code": e.code, "body": body}
    except Exception as e:
        print("❌ TELEGRAM API EXCEPTION:", e)
        return {"ok": False, "error": str(e)}


def build_keyboard(order):
    # ✅ Кнопки показываем только после загрузки чека (status == "new")
    if order.status == "new":
        return {
            "inline_keyboard": [[
                {"text": "✅ Подтвердить оплату", "callback_data": f"accept:{order.id}"},
                {"text": "❌ Отклонить оплату", "callback_data": f"cancel:{order.id}"},
            ]]
        }

    if order.status == "accepted":
        return {
            "inline_keyboard": [[
                {"text": "🚚 В пути", "callback_data": f"way:{order.id}"},
            ]]
        }

    if order.status == "in_progress":
        return {
            "inline_keyboard": [[
                {"text": "📦 Доставлен", "callback_data": f"deliver:{order.id}"},
            ]]
        }

    return {"inline_keyboard": []}


# =========================
# Отправка заказа в Telegram (С ФОТО ЧЕКА)
# =========================

def send_telegram_order_notification(order: Order):
    chat_id = getattr(settings, "TELEGRAM_CHAT_ID", None)
    bot_token = getattr(settings, "TELEGRAM_BOT_TOKEN", None)
    if not bot_token or not chat_id:
        return

    items = order.items.select_related("watch").all()
    lines = []
    for i, item in enumerate(items, start=1):
        lines.append(f"{i}) {escape(item.watch.name)} × {item.quantity} — {item.total_price} сум")
    items_block = "\n".join(lines) if lines else "—"

    map_line = ""
    if order.latitude is not None and order.longitude is not None:
        map_url = f"https://yandex.com/maps/?pt={order.longitude},{order.latitude}&z=16&l=map"
        map_line = f"\n<b>Карта:</b> <a href=\"{map_url}\">Открыть в Яндекс Картах</a>"

    status_text = f"<b>Статус:</b> {escape(order.get_status_display())}"

    full_text = (
        f"<b>🧾 Чек оплаты по заказу #{order.id}</b>\n\n"
        f"<b>Телефон:</b> {escape(order.phone)}\n"
        f"<b>Адрес:</b> {escape(order.location)}"
        f"{map_line}\n\n"
        f"<b>Товары:</b>\n{items_block}\n\n"
        f"<b>Сумма:</b> {order.total_amount} сум\n\n"
        f"{status_text}\n\n"
        f"Выберите действие:"
    )

    keyboard = build_keyboard(order)

    # ✅ Если есть скрин — отправляем фото
    if order.payment_screenshot and hasattr(order.payment_screenshot, "url"):
        try:
            # делаем абсолютную ссылку на картинку
            photo_url = f"https://www.timepiece.uz{order.payment_screenshot.url}"

            # caption в Telegram ограничен ~1024 символами, поэтому кладём туда коротко
            caption = (
                f"<b>🧾 Чек оплаты #{order.id}</b>\n"
                f"<b>Сумма:</b> {order.total_amount} сум\n"
                f"<b>Тел:</b> {escape(order.phone)}\n"
                f"<b>Адрес:</b> {escape(order.location)}\n"
                f"<b>Статус:</b> {escape(order.get_status_display())}"
            )

            tg_api(
                "sendPhoto",
                {
                    "chat_id": chat_id,
                    "photo": photo_url,  # важно: публичный URL
                    "caption": caption,
                    "parse_mode": "HTML",
                    "reply_markup": json.dumps(keyboard),
                },
            )

            # Дополнительно (по желанию) можно отдельно отправить полный текст списком товаров:
            tg_api(
                "sendMessage",
                {
                    "chat_id": chat_id,
                    "text": full_text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
            )
            return

        except Exception as e:
            print("❌ sendPhoto failed:", e)
            # упадём в sendMessage ниже

    # ✅ Если скрина нет — просто текст
    tg_api(
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": full_text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
            "reply_markup": json.dumps(keyboard),
        },
    )


# =========================
# Оформление заказа
# =========================

@login_required(login_url="login")
def checkout(request):
    """
    ШАГ 1:
    Создаём заказ со статусом "awaiting_payment" (Ожидает оплаты),
    НЕ отправляем в Telegram.
    """
    cart = Cart(request)

    if request.method != "POST":
        return redirect("cart_detail")

    location = (request.POST.get("location") or "").strip()
    phone = (request.POST.get("phone") or "").strip()
    lat_raw = (request.POST.get("latitude") or "").strip()
    lon_raw = (request.POST.get("longitude") or "").strip()

    # координаты в float
    try:
        lat = float(lat_raw) if lat_raw else None
        lon = float(lon_raw) if lon_raw else None
    except ValueError:
        lat = None
        lon = None

    errors = {}
    if not cart:
        errors["cart"] = "Корзина пуста"
    if not location:
        errors["location"] = "Укажите адрес"
    if not phone:
        errors["phone"] = "Укажите телефон"
    if lat is None or lon is None:
        errors["map"] = "Выберите точку на карте."

    if errors:
        return render(
            request,
            "cart.html",
            {"cart": cart, "errors": errors, "form": request.POST},
        )

    # ✅ ВАЖНО: заказ создаём как "Ожидает оплаты"
    order = Order.objects.create(
        user=request.user,
        location=location,
        phone=phone,
        latitude=lat,
        longitude=lon,
        status="awaiting_payment",  # ✅ ИСПРАВЛЕНО
    )

    # можно обновить профиль
    if hasattr(request.user, "profile"):
        request.user.profile.location = location
        request.user.profile.phone = phone
        request.user.profile.save()

    for item in cart:
        OrderItem.objects.create(
            order=order,
            watch=item["watch"],
            quantity=item["quantity"],
            price=item["price"],
        )

    cart.clear()

    return redirect("payment_page", order_id=order.id)


@login_required
def payment_page(request, order_id):
    """
    ШАГ 2:
    Показываем карту, просим скриншот оплаты.
    ✅ Защита от повторной загрузки: если чек уже есть — запрещаем.
    """
    order = Order.objects.filter(id=order_id, user=request.user).first()
    if not order:
        return redirect("account")

    # ✅ Если заказ уже выше стадии оплаты — назад в аккаунт
    if order.status in ("accepted", "in_progress", "delivered", "cancelled"):
        return redirect("account")

    if request.method == "POST":
        # ✅ Защита от повторной загрузки
        if order.payment_screenshot:
            messages.error(request, "Чек уже загружен. Повторная загрузка запрещена.")
            return redirect("account")

        screenshot = request.FILES.get("payment_screenshot")
        if not screenshot:
            messages.error(request, "Загрузите скриншот оплаты")
            return redirect("payment_page", order_id=order.id)

        order.payment_screenshot = screenshot

        # ✅ После загрузки чека: статус "new" = "Оплачен (на проверке)"
        order.status = "new"
        order.save()

        # ✅ Теперь отправляем в Telegram (и фото, и товары)
        send_telegram_order_notification(order)

        messages.success(request, "Оплата отправлена на проверку")
        return redirect("account")

    return render(request, "payment.html", {
        "order": order,
        "card_number": "5614 6835 1277 8028",
    })


# =========================
# Telegram Webhook
# =========================

@csrf_exempt
@require_POST
def telegram_webhook(request):
    try:
        update = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"ok": True})

    cb = update.get("callback_query")
    if not cb:
        return JsonResponse({"ok": True})

    data = cb.get("data", "")
    cb_id = cb.get("id")
    msg = cb.get("message", {})
    chat_id = msg.get("chat", {}).get("id")
    message_id = msg.get("message_id")

    # убираем "часики"
    if cb_id:
        tg_api("answerCallbackQuery", {"callback_query_id": cb_id})

    if not data or ":" not in data:
        return JsonResponse({"ok": True})

    action, order_id = data.split(":", 1)
    order = Order.objects.filter(id=order_id).first()
    if not order:
        return JsonResponse({"ok": True})

    if order.status in ("cancelled", "delivered"):
        return JsonResponse({"ok": True})

    # ✅ Отклонить оплату можно только когда чек загружен (status == "new")
    if action == "cancel" and order.status == "new":
        order.status = "cancelled"
        order.admin_comment = order.admin_comment or "Оплата отклонена"
        status_text = "❌ <b>Статус:</b> Оплата отклонена / Отменён"

        # ✅ Уведомление клиенту (если у вас где-то хранится chat_id)
        _notify_client_if_possible(order, f"❌ Оплата по заказу №{order.id} отклонена. Свяжитесь с продавцом.")

    # ✅ Подтвердить оплату -> accepted
    elif action == "accept" and order.status == "new":
        order.status = "accepted"
        order.admin_comment = order.admin_comment or "Оплата подтверждена"
        status_text = "✅ <b>Статус:</b> Оплата подтверждена"

        # ✅ Авто-уведомление клиенту (если есть chat_id)
        _notify_client_if_possible(order, f"✅ Оплата по заказу №{order.id} подтверждена. Спасибо!")

    elif action == "way" and order.status == "accepted":
        order.status = "in_progress"
        status_text = "🚚 <b>Статус:</b> В пути"
        _notify_client_if_possible(order, f"🚚 Заказ №{order.id} в пути.")

    elif action == "deliver" and order.status == "in_progress":
        order.status = "delivered"
        status_text = "📦 <b>Статус:</b> Доставлен"
        _notify_client_if_possible(order, f"📦 Заказ №{order.id} доставлен.")

    else:
        return JsonResponse({"ok": True})

    order.save()

    items = order.items.select_related("watch").all()
    items_text = "\n".join(
        f"{i+1}) <b>{escape(item.watch.name)}</b> × {item.quantity} — {item.total_price} сум"
        for i, item in enumerate(items)
    )

    map_line = ""
    if order.latitude is not None and order.longitude is not None:
        map_url = f"https://yandex.com/maps/?pt={order.longitude},{order.latitude}&z=16&l=map"
        map_line = f"\n<b>Карта:</b> <a href=\"{map_url}\">Открыть в Яндекс Картах</a>"

    new_text = (
        f"<b>🧾 Заказ #{order.id}</b>\n\n"
        f"<b>Телефон:</b> {escape(order.phone)}\n"
        f"<b>Адрес:</b> {escape(order.location)}"
        f"{map_line}\n\n"
        f"<b>Товары:</b>\n{items_text}\n\n"
        f"<b>Сумма:</b> {order.total_amount} сум\n\n"
        f"{status_text}"
    )

    keyboard = build_keyboard(order)

    # ✅ Если это сообщение было sendPhoto — editMessageCaption, иначе editMessageText
    # Мы не знаем точно, поэтому пробуем caption, а если не ок — text.
    resp = tg_api("editMessageCaption", {
        "chat_id": chat_id,
        "message_id": message_id,
        "caption": new_text,
        "parse_mode": "HTML",
        "reply_markup": json.dumps(keyboard),
    })

    if not resp.get("ok"):
        tg_api("editMessageText", {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": new_text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
            "reply_markup": json.dumps(keyboard),
        })

    return JsonResponse({"ok": True})


def _notify_client_if_possible(order: Order, text: str):
    """
    ✅ Авто-уведомление клиенту при принятии оплаты
    ВАЖНО: у Django-юзера по умолчанию НЕТ telegram_id.
    Поэтому уведомляем только если вы где-то сохранили chat_id.

    Варианты:
    - order.user.profile.telegram_chat_id (если вы добавите поле)
    - settings.TEST_CLIENT_CHAT_ID (для теста)
    """
    try:
        if not order.user:
            return
        profile = getattr(order.user, "profile", None)
        client_chat_id = None

        if profile and hasattr(profile, "telegram_chat_id"):
            client_chat_id = getattr(profile, "telegram_chat_id")

        # fallback для теста
        if not client_chat_id:
            client_chat_id = getattr(settings, "TEST_CLIENT_CHAT_ID", None)

        if client_chat_id:
            tg_api("sendMessage", {"chat_id": client_chat_id, "text": text})
    except Exception:
        return


# =========================
# Callback оплаты (пока заглушка)
# =========================

@csrf_exempt
def payment_callback(request):
    return JsonResponse({"result": "ok"})


# =========================
# Аккаунт / выход
# =========================

@login_required
def account(request):
    orders = Order.objects.filter(user=request.user).order_by("-created_at")
    return render(request, "account.html", {"user": request.user, "orders": orders})


def logout_view(request):
    logout(request)
    return redirect("index")
