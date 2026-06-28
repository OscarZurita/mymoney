from django.utils import timezone
from django.conf import settings
from django.db import models
from .models import Category
from .tags import ExpenseTag, IncomeTag, InvestmentTag
from django.core.exceptions import ValidationError

from ..formatting import format_money

class Transaction(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE,
        related_name = "%(class)ss"
    )
    
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
    )
    
    description = models.CharField(max_length = 255, blank=True)
    date = models.DateField("Date spent", default=timezone.localdate, blank=True)
    amount = models.DecimalField(max_digits=16, decimal_places=2)
    
    class Meta:
        abstract = True
        ordering = ["-date"]
        indexes = [models.Index(fields = ["user", "date"], name = "%(class)s_user_date_index")]
    
    def __str__(self):
        return f"{self.description or f'{self.__class__.__name__} of {self.amount} on {self.date}'} {format_money(self.amount)}"


class Expense(Transaction):
    tags = models.ManyToManyField(
        ExpenseTag,
        blank=True,
        related_name="expenses",
    )
    
    def clean(self):
        if self.category.type != Category.Type.EXPENSE:
            raise ValidationError
        
class Income(Transaction):
    tags = models.ManyToManyField(
        IncomeTag,
        blank=True,
        related_name="incomes",
    )
    
    def clean(self):
        if self.category.type != Category.Type.INCOME:
            raise ValidationError
        
class Investment(Transaction):
    tags = models.ManyToManyField(
        InvestmentTag,
        blank=True,
        related_name="investments",
    )
    
    def clean(self):
        if self.category.type != Category.Type.INVESTMENT:
            raise ValidationError
    