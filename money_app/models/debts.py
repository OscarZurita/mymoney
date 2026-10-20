from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Max, OuterRef, Q, Subquery, Sum
from django.db.models.functions import Coalesce
from django.db.transaction import atomic
from django.utils import timezone

from ..formatting import format_money
from .tags import TagBase


# Someone the user shares expenses with or borrows from. Like a tag, a person
# belongs to a single user and is matched by name ignoring case, which is what
# TagBase provides.
class Person(TagBase):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="people",
    )

    class Meta(TagBase.Meta):
        verbose_name_plural = "people"


class DebtQuerySet(models.QuerySet):
    def for_user(self, user):
        """The user's debts, from their expenses and their incomes.

        A debt has no user of its own: it belongs to whoever owns its transaction.
        """
        return self.filter(Q(expense__user=user) | Q(income__user=user))

    def with_repaid(self):
        """Annotate `repaid` and `remaining`: what was paid back, and what is left."""
        repaid = (
            Repayment.objects.filter(debt=OuterRef("pk"))
            .values("debt")
            .annotate(total=Sum("amount"))
            .values("total")
        )
        return self.annotate(repaid=Coalesce(Subquery(repaid), Decimal("0"))).annotate(
            remaining=F("amount") - F("repaid")
        )


class Debt(models.Model):
    class Direction(models.TextChoices):
        # The labels read as a prefix to the person's name: "Owed by Alice".
        OWED_TO_ME = "owed_to_me", "Owed by"
        OWED_BY_ME = "owed_by_me", "Owed to"

    # A debt belongs to either an expense or an income.
    expense = models.ForeignKey(
        "Expense",
        on_delete=models.CASCADE,
        related_name="debts",
        null=True,
        blank=True,
    )
    income = models.ForeignKey(
        "Income",
        on_delete=models.CASCADE,
        related_name="debts",
        null=True,
        blank=True,
    )
    # RESTRICT rather than PROTECT: a person who still has debts can't be deleted
    # on their own, but deleting the user removes both through their cascades.
    person = models.ForeignKey(Person, on_delete=models.RESTRICT, related_name="debts")
    direction = models.CharField(
        max_length=20, choices=Direction.choices, default=Direction.OWED_TO_ME
    )
    amount = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    # Empty while the debt is open. Once its repayments add up to its amount, the
    # date of the latest one. update_settled_on() keeps it in step with them.
    settled_on = models.DateField(null=True, blank=True, editable=False)

    objects = DebtQuerySet.as_manager()

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(expense__isnull=False, income__isnull=True)
                | Q(expense__isnull=True, income__isnull=False),
                name="money_app_debt_expense_or_income",
            ),
            # Someone lent the user an income, so the user is the one who owes it.
            models.CheckConstraint(
                condition=Q(income__isnull=True) | Q(direction="owed_by_me"),
                name="money_app_debt_income_owed_by_me",
            ),
        ]

    def __str__(self):
        return (
            f"{self.get_direction_display()} {self.person} {format_money(self.amount)}"
        )

    @property
    def transaction(self):
        return self.expense or self.income

    @property
    def is_owed_to_me(self):
        return self.direction == self.Direction.OWED_TO_ME

    @property
    def is_settled(self):
        return self.settled_on is not None

    def pay_off(self, date=None):
        """Repay what is left of the debt, today unless another date is given."""
        repayments = self.repayments.aggregate(
            total=Sum("amount", default=Decimal("0"))
        )
        remaining = self.amount - repayments["total"]
        if remaining > 0:
            self.repayments.create(amount=remaining, date=date or timezone.localdate())

    def reopen(self):
        """Undo the latest repayment of a settled debt, which reopens it.

        Returns the repayment, or None when the debt was open already.
        """
        if not self.is_settled:
            return None
        latest = self.repayments.latest()
        latest.delete()
        return latest

    def update_settled_on(self):
        """Settle or reopen the debt to match its repayments, and save that."""
        repayments = self.repayments.aggregate(
            total=Sum("amount", default=Decimal("0")), latest=Max("date")
        )
        self.settled_on = (
            repayments["latest"] if repayments["total"] >= self.amount else None
        )
        self.save(update_fields=["settled_on"])

    def clean(self):
        transaction = self.transaction
        if (
            self.person_id is not None
            and transaction is not None
            and self.person.user_id != transaction.user_id
        ):
            raise ValidationError({"person": "This person belongs to another user."})


# Money paid back on a debt: by the person to the user when they owe it, by the
# user to the person otherwise. Repayments never change statistics.
class Repayment(models.Model):
    debt = models.ForeignKey(Debt, on_delete=models.CASCADE, related_name="repayments")
    date = models.DateField(default=timezone.localdate)
    amount = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )

    class Meta:
        ordering = ["-date", "-id"]
        get_latest_by = ["date", "id"]

    def __str__(self):
        return f"{format_money(self.amount)} on {self.date}"

    # Whether the debt is settled follows from its repayments.
    def save(self, *args, **kwargs):
        with atomic():
            super().save(*args, **kwargs)
            self.debt.update_settled_on()

    def delete(self, *args, **kwargs):
        with atomic():
            deleted = super().delete(*args, **kwargs)
            self.debt.update_settled_on()
        return deleted

    def clean(self):
        if self.debt_id is None or self.amount is None:
            return
        repaid = self.debt.repayments.exclude(pk=self.pk).aggregate(
            total=Sum("amount", default=Decimal("0"))
        )["total"]
        remaining = self.debt.amount - repaid
        if self.amount > remaining:
            raise ValidationError(
                {"amount": f"Only {format_money(remaining)} is left to pay."}
            )
