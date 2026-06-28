from django.conf import settings
from django.db import models

from ..formatting import format_money

class Category(models.Model):
    class Type(models.TextChoices):
        EXPENSE = "expense", "Expense"
        INCOME = "income", "Income"
        INVESTMENT = "investment", "Investment"
    
    name = models.CharField(max_length=100, unique=True)
    type = models.CharField(max_length = 20, choices = Type.choices)
    
    class Meta:
        unique_together = [("name", "type")]
        verbose_name_plural = "categories"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.type})"
    
    
class YearGoal(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete = models.CASCADE,
        related_name="year_goals",
    )
    year = models.IntegerField()
    amount = models.DecimalField(max_digits=16, decimal_places=2)
    
    class Meta:
        unique_together = ("user", "year")

    def __str__(self):
        return format_money(self.amount)
