import json
from django import template

register = template.Library()


@register.filter
def pretty_json(value):
    try:
        parsed = json.loads(value) if isinstance(value, str) else value
        return json.dumps(parsed, indent=2)
    except (json.JSONDecodeError, TypeError):
        return value
