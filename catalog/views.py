import json
import urllib.parse
import urllib.request
import urllib.error
from html import escape

from django import forms
from django.conf import settings
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_exempt
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

def index(request):
    return render(request, "index.html")


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
    if order.status == "new":
        return {
            "inline_keyboard": [[
                {"text": "✔ Принять", "callback_data": f"accept:{order.id}"},
                {"text": "✖ Отклонить", "callback_data": f"cancel:{order.id}"},
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
# Отправка заказа в Telegram
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

    coords_line = ""
    map_line = ""
    if order.latitude is not None and order.longitude is not None:
        map_url = f"https://yandex.com/maps/?pt={order.longitude},{order.latitude}&z=16&l=map"
        coords_line = f"<b>Координаты:</b> {order.latitude}, {order.longitude}\n"
        map_line = f"<b>Карта:</b> <a href=\"{map_url}\">Открыть в Яндекс Картах</a>\n"

    text = (
        f"<b>🕒 Новый заказ #{order.id}</b>\n\n"
        f"<b>Телефон:</b> {escape(order.phone)}\n"
        f"<b>Адрес:</b> {escape(order.location)}\n"
        f"{coords_line}"
        f"{map_line}"
        f"\n<b>Товары:</b>\n{items_block}\n"
        f"\n<b>Сумма:</b> {order.total_amount} сум\n"
        f"\nВыберите действие:"
    )

    # ✅ ВАЖНО: для нового заказа должны быть accept/cancel
    keyboard = build_keyboard(order)

    tg_api(
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
            "reply_markup": json.dumps(keyboard),
        },
    )


# =========================
# Оформление заказа
# =========================

def checkout(request):
    cart = Cart(request)

    if request.method == "POST":
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
            errors["cart"] = "Корзина пуста. Добавьте хотя бы одну модель."
        if not location:
            errors["location"] = "Укажите адрес доставки."
        if not phone:
            errors["phone"] = "Укажите номер телефона."
        if lat is None or lon is None:
            errors["map"] = "Выберите точку на карте."

        if errors:
            return render(
                request,
                "cart.html",
                {
                    "cart": cart,
                    "errors": errors,
                    "form": {
                        "location": location,
                        "phone": phone,
                        "latitude": lat_raw,
                        "longitude": lon_raw,
                    },
                },
                status=200,
            )

        # ✅ ВАЖНО: статус должен быть new (а не waiting)
        order = Order.objects.create(
            user=request.user if request.user.is_authenticated else None,
            location=location,
            phone=phone,
            latitude=lat,
            longitude=lon,
            status="new",
        )

        # обновляем профиль
        if request.user.is_authenticated and hasattr(request.user, "profile"):
            profile = request.user.profile
            profile.location = location
            profile.phone = phone
            profile.save()

        for item in cart:
            OrderItem.objects.create(
                order=order,
                watch=item["watch"],
                quantity=item["quantity"],
                price=item["price"],
            )

        cart.clear()

        # отправляем в Telegram
        send_telegram_order_notification(order)

        return redirect("account")

    return redirect("cart_detail")


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

    # защита от повторных кликов на финальных статусах
    if order.status in ("cancelled", "delivered"):
        return JsonResponse({"ok": True})

    # ===== МАШИНА СОСТОЯНИЙ =====
    if action == "cancel" and order.status == "new":
        order.status = "cancelled"
        status_text = "❌ <b>Статус:</b> Отменён"

    elif action == "accept" and order.status == "new":
        order.status = "accepted"
        status_text = "✅ <b>Статус:</b> Принят"

    elif action == "way" and order.status == "accepted":
        order.status = "in_progress"
        status_text = "🚚 <b>Статус:</b> В пути"

    elif action == "deliver" and order.status == "in_progress":
        order.status = "delivered"
        status_text = "📦 <b>Статус:</b> Доставлен"

    else:
        return JsonResponse({"ok": True})

    order.save()

    # ✅ Уведомление пользователю (если есть telegram_id)
    # Не ломает проект, даже если telegram_id нет
    if order.user and hasattr(order.user, "telegram_id") and order.user.telegram_id:
        tg_api("sendMessage", {
            "chat_id": order.user.telegram_id,
            "text": f"Статус вашего заказа №{order.id}: {order.get_status_display()}",
        })

    # ===== ТОВАРЫ =====
    items = order.items.select_related("watch").all()
    items_text = "\n".join(
        f"{i+1}) <b>{escape(item.watch.name)}</b> × {item.quantity} — {item.total_price} сум"
        for i, item in enumerate(items)
    )

    # ===== YANDEX MAPS =====
    map_line = ""
    if order.latitude is not None and order.longitude is not None:
        map_url = f"https://yandex.com/maps/?pt={order.longitude},{order.latitude}&z=16&l=map"
        map_line = f"\n<b>Карта:</b> <a href=\"{map_url}\">Открыть в Яндекс Картах</a>"

    # ===== ТЕКСТ СООБЩЕНИЯ =====
    new_text = (
        f"<b>🕒 Заказ #{order.id}</b>\n\n"
        f"<b>Телефон:</b> {escape(order.phone)}\n"
        f"<b>Адрес:</b> {escape(order.location)}"
        f"{map_line}\n\n"
        f"<b>Товары:</b>\n{items_text}\n\n"
        f"<b>Сумма:</b> {order.total_amount} сум\n\n"
        f"{status_text}"
    )

    # ✅ Динамические кнопки (new → accepted → in_progress → delivered/cancelled)
    keyboard = build_keyboard(order)

    tg_api("editMessageText", {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": new_text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    })

    tg_api("editMessageReplyMarkup", {
        "chat_id": chat_id,
        "message_id": message_id,
        "reply_markup": json.dumps(keyboard),
    })

    return JsonResponse({"ok": True})


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
