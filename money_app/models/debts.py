from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
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
    # Empty while the debt is open.
    settled_on = models.DateField(null=True, blank=True)

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

    def set_settled(self, settled):
        if not settled:
            self.settled_on = None
        elif self.settled_on is None:
            self.settled_on = timezone.localdate()

    def clean(self):
        transaction = self.transaction
        if (
            self.person_id is not None
            and transaction is not None
            and self.person.user_id != transaction.user_id
        ):
            raise ValidationError({"person": "This person belongs to another user."})
