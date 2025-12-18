from django.contrib import admin
from .models import Watch


@admin.register(Watch)
class WatchAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "price",
        "badge",
        "is_active",
        "is_hero",
        "is_featured",
        "sort_order",
    )
    list_filter = ("is_active", "is_hero", "is_featured", "badge")
    search_fields = ("name", "description", "tag")
    list_editable = ("price", "badge", "is_active", "is_hero", "is_featured", "sort_order")
