from django import template
from django.conf import settings

from capaggregator import __version__

register = template.Library()


@register.simple_tag
def capagg_version():
    return __version__


@register.filter
def django_settings(value):
    return getattr(settings, value, None)
