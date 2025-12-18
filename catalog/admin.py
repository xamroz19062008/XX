from django.contrib import admin
from .models import Watch
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import Profile 
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
class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    extra = 0
class UserAdmin(BaseUserAdmin):
    inlines = [ProfileInline]
    list_display = ("username", "email", "get_phone", "date_joined", "is_staff")
    search_fields = ("username", "email", "profile__phone")

    def get_phone(self, obj):
        return getattr(obj.profile, "phone", "")
    get_phone.short_description = "Телефон"


admin.site.unregister(User)
admin.site.register(User, UserAdmin)