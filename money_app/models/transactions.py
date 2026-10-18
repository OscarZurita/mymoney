from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, OuterRef, Subquery, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from ..formatting import format_money
from .debts import Debt
from .models import Category
from .tags import ExpenseTag, IncomeTag, InvestmentTag


class Transaction(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="%(class)ss"
    )

    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
    )

    description = models.CharField(max_length=255, blank=True)
    date = models.DateField("Date spent", default=timezone.localdate, blank=True)
    amount = models.DecimalField(max_digits=16, decimal_places=2)

    class Meta:
        abstract = True
        ordering = ["-date"]
        indexes = [
            models.Index(fields=["user", "date"], name="%(class)s_user_date_index")
        ]

    def __str__(self):
        return f"{self.description or f'{self.__class__.__name__} of {self.amount} on {self.date}'} {format_money(self.amount)}"


class ExpenseQuerySet(models.QuerySet):
    def with_share(self):
        """Annotate `share`: the amount minus what others owe the user for it.

        Spending statistics sum `share`, not `amount`, so money the user fronted
        for others never counts as their spending, paid back yet or not.
        """
        owed_to_me = (
            Debt.objects.filter(
                expense=OuterRef("pk"), direction=Debt.Direction.OWED_TO_ME
            )
            .values("expense")
            .annotate(total=Sum("amount"))
            .values("total")
        )
        return self.annotate(
            share=F("amount") - Coalesce(Subquery(owed_to_me), Decimal("0"))
        )


class Expense(Transaction):
    tags = models.ManyToManyField(
        ExpenseTag,
        blank=True,
        related_name="expenses",
    )

    objects = ExpenseQuerySet.as_manager()

    def clean(self):
        if self.category_id and not self.category.matches_transaction_type(
            Category.Type.EXPENSE
        ):
            raise ValidationError(
                {"category": "Category does not match this transaction type."}
            )


class Income(Transaction):
    tags = models.ManyToManyField(
        IncomeTag,
        blank=True,
        related_name="incomes",
    )

    def clean(self):
        if self.category_id and not self.category.matches_transaction_type(
            Category.Type.INCOME
        ):
            raise ValidationError(
                {"category": "Category does not match this transaction type."}
            )


class Investment(Transaction):
    tags = models.ManyToManyField(
        InvestmentTag,
        blank=True,
        related_name="investments",
    )

    def clean(self):
        if self.category_id and not self.category.matches_transaction_type(
            Category.Type.INVESTMENT
        ):
            raise ValidationError(
                {"category": "Category does not match this transaction type."}
            )
