from django import template

register = template.Library()


@register.filter
def to_percent(value):
    try:
        return round(float(value) * 100)
    except (TypeError, ValueError):
        return 0
