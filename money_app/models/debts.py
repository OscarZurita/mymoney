from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from ..formatting import format_money
from .tags import TagBase


# Someone the user shares expenses with. Like a tag, a person belongs to a single
# user and is matched by name ignoring case, which is what TagBase provides.
class Person(TagBase):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="people",
    )

    class Meta(TagBase.Meta):
        verbose_name_plural = "people"


class Debt(models.Model):
    class Direction(models.TextChoices):
        # The labels read as a prefix to the person's name: "Owed by Alice".
        OWED_TO_ME = "owed_to_me", "Owed by"
        OWED_BY_ME = "owed_by_me", "Owed to"

    expense = models.ForeignKey(
        "Expense", on_delete=models.CASCADE, related_name="debts"
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

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return (
            f"{self.get_direction_display()} {self.person} {format_money(self.amount)}"
        )

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
        if (
            self.person_id is not None
            and self.expense_id is not None
            and self.person.user_id != self.expense.user_id
        ):
            raise ValidationError({"person": "This person belongs to another user."})
