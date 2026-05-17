import json
import bleach
import markdown as md
from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def pretty_json(value):
    try:
        parsed = json.loads(value) if isinstance(value, str) else value
        return json.dumps(parsed, indent=2)
    except (json.JSONDecodeError, TypeError):
        return value


_MARKDOWN_ALLOWED_TAGS = {
    'p', 'br', 'strong', 'em', 'u', 'del', 's', 'code', 'pre',
    'ul', 'ol', 'li', 'blockquote',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'a', 'img', 'hr', 'table', 'thead', 'tbody', 'tr', 'th', 'td',
}
_MARKDOWN_ALLOWED_ATTRS = {
    'a': ['href', 'title', 'rel'],
    'img': ['src', 'alt', 'title'],
}


@register.filter(name='markdown')
def render_markdown(value):
    if not value:
        return ''
    html = md.markdown(value, extensions=['fenced_code', 'tables', 'nl2br', 'sane_lists'])
    cleaned = bleach.clean(html, tags=_MARKDOWN_ALLOWED_TAGS, attributes=_MARKDOWN_ALLOWED_ATTRS, strip=True)
    return mark_safe(cleaned)
