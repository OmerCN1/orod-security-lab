import jinja2


def render(template_source: str, **values: str) -> str:
    environment = jinja2.Environment(autoescape=False)
    return environment.from_string(template_source).render(**values)
