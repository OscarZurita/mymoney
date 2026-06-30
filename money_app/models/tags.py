from django.conf import settings
from django.db import models


def normalize_tag_name(value):
    return " ".join((value or "").split())


def normalize_tag_key(value):
    return normalize_tag_name(value).casefold()


class TagBase(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="%(class)s_tags",
    )
    name = models.CharField(max_length=100)
    normalized_name = models.CharField(max_length=100, editable=False)

    class Meta:
        abstract = True
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "normalized_name"],
                name="%(app_label)s_%(class)s_user_normalized_name_unique",
            )
        ]

    def save(self, *args, **kwargs):
        self.name = normalize_tag_name(self.name)
        self.normalized_name = normalize_tag_key(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name
    
    
class ExpenseTag(TagBase):
    class Meta(TagBase.Meta):
        pass


class IncomeTag(TagBase):
    class Meta(TagBase.Meta):
        pass


class InvestmentTag(TagBase):
    class Meta(TagBase.Meta):
        pass