from django.contrib import admin

from .formatting import format_money
from .models import Category, Expense

admin.site.site_header = "Expense registration"
admin.site.site_title = "Expense registration area"
admin.site.index_title = "Welcome to the expense registration admin area"

@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ("description", "formatted_amount", "category", "user", "date")
    list_filter = ("category", "user", "tags")
    search_fields = ("description", "user__username", "tags__name")
    filter_horizontal = ("tags",)

    @admin.display(ordering="amount", description="Amount")
    def formatted_amount(self, obj):
        return format_money(obj.amount)


admin.site.register(Category)

#TODO add Income, Investment, ExpenseTag, IncomeTag, InvestmentTag to admin.py