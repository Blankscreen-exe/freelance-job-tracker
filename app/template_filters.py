"""Custom Jinja2 template filters"""

def nl2br(value):
    """Convert newlines to <br> tags for HTML display"""
    if value is None:
        return ""
    # Handle different line ending styles
    text = str(value)
    text = text.replace('\r\n', '\n')  # Normalize Windows line endings
    text = text.replace('\r', '\n')     # Normalize Mac line endings
    return text.replace('\n', '<br>\n')

def register_template_filters(templates):
    """Register custom filters with a Jinja2Templates instance"""
    templates.env.filters['nl2br'] = nl2br

def get_templates(directory):
    """Create and configure a Jinja2Templates instance with custom filters"""
    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory=directory)
    register_template_filters(templates)
    return templates
