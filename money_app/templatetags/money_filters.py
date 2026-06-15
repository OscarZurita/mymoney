from django import template

from money_app.formatting import format_money


register = template.Library()


@register.filter
def money(value):
    return format_money(value)
