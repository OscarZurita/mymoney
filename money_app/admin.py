from django.contrib import admin
from .models import Category, Expense, Tag

admin.site.site_header = "Expense registration"
admin.site.site_title = "Expense registration area"
admin.site.index_title = "Welcome to the expense registration admin area"

@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ("description", "amount", "category", "owner", "date")
    list_filter = ("category", "owner", "tags")
    search_fields = ("description", "owner__username", "tags__name")
    filter_horizontal = ("tags",)


admin.site.register(Category)


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("name", "owner")
    list_filter = ("owner",)
    search_fields = ("name", "owner__username")
