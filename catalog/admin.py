from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Watch, UserProfile


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
    list_editable = (
        "price",
        "badge",
        "is_active",
        "is_hero",
        "is_featured",
        "sort_order",
    )


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    extra = 0


class UserAdmin(BaseUserAdmin):
    inlines = [UserProfileInline]
    list_display = ("username", "email", "get_phone", "date_joined", "is_staff")
    search_fields = ("username", "email", "profile__phone")
    list_select_related = ("profile",)

    @admin.display(description="Телефон")
    def get_phone(self, obj):
        if hasattr(obj, "profile") and obj.profile:
            return obj.profile.phone or ""
        return ""


admin.site.unregister(User)
admin.site.register(User, UserAdmin)
