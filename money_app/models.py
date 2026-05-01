from django.conf import settings
from django.db import models
from django.utils import timezone

# Create your models here.


def normalize_tag_name(value):
    return " ".join((value or "").split())


def normalize_tag_key(value):
    return normalize_tag_name(value).casefold()

class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        verbose_name_plural = "categories"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Tag(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="tags",
    )
    name = models.CharField(max_length=100)
    normalized_name = models.CharField(max_length=100, editable=False)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "normalized_name"],
                name="money_app_tag_owner_normalized_name_unique",
            )
        ]

    def save(self, *args, **kwargs):
        self.name = normalize_tag_name(self.name)
        self.normalized_name = normalize_tag_key(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Expense(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="expenses",
        null=True,
        blank=True,
    )
    description = models.CharField(max_length=255, blank=True)
    date = models.DateField("Date spent", default=timezone.localdate, blank=True)
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="expenses",
    )
    tags = models.ManyToManyField(
        Tag,
        blank=True,
        related_name="expenses",
    )
    
    class Meta:
        ordering = ["-date"]

    def __str__(self):
        return f"{self.description or 'Expense'} {self.amount}"
    
class YearGoal(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete = models.CASCADE,
        related_name="year_goals",
    )
    year = models.IntegerField()
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    
    class Meta:
        unique_together = ("owner", "year")

    def __str__(self):
        return f"{self.user} - {self.year} - {self.amount}"
