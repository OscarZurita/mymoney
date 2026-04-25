from django.contrib import admin
from .models import Category, Expense

admin.site.site_header = "Expense registration"
admin.site.site_title = "Expense registration area"
admin.site.index_title = "Welcome to the expense registration admin area"

@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ("description", "amount", "category", "owner", "date")
    list_filter = ("category", "owner")
    search_fields = ("description", "owner__username")


admin.site.register(Category)
