from django import template

register = template.Library()


@register.filter
def mul(value, arg):
    """将值乘以参数"""
    try:
        return int(value) * int(arg)
    except (ValueError, TypeError):
        return 0

