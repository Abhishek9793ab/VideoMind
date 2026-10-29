
import bleach
import markdown

from django import template
from django.utils.safestring import mark_safe

register = template.Library()

ALLOWED_TAGS = set(bleach.sanitizer.ALLOWED_TAGS) | {
    "p", "br", "hr",
    "h1", "h2", "h3", "h4",
    "ul", "ol", "li",
    "strong", "em", "del",
    "blockquote", "pre", "code",
    "table", "thead", "tbody", "tr", "th", "td",
}

ALLOWED_ATTRIBUTES = {
    "a": ["href", "title"],
    "code": ["class"],
    "pre": ["class"],
    "th": ["align"],
    "td": ["align"],
}


@register.filter(name="study_markdown")
def study_markdown(value):
    """Render Markdown as sanitized HTML for study notes and chat."""

    if not value:
        return ""

    source = str(value).strip()

    # Remove accidental Markdown fences around the entire response.
    lines = source.splitlines()

    if (
        len(lines) >= 2
        and lines[0].strip().startswith("```")
        and lines[-1].strip() == "```"
    ):
        source = "\n".join(lines[1:-1]).strip()

    rendered = markdown.markdown(
        source,
        extensions=["extra", "sane_lists", "fenced_code"],
    )

    clean_html = bleach.clean(
        rendered,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols={"http", "https", "mailto"},
        strip=True,
    )

    return mark_safe(clean_html)
