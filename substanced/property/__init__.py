import colander

from zope.interface import implementer

from pyramid.threadlocal import get_current_registry
from pyramid.compat import is_nonstr_iter

from ..interfaces import IPropertySheet
from ..event import ObjectModified

@implementer(IPropertySheet)
class PropertySheet(object):
    """ Convenience base class for concrete property sheet implementations """

    # XXX probably should be decorator for set and get
    permissions = (
        ('view', 'sdi.view'),
        ('change', 'sdi.edit-properties'),
        )

    schema = None

    def __init__(self, context, request):
        self.context = context
        self.request = request

    def get(self):
        context = self.context
        result = {}
        for child in self.schema:
            name = child.name
            val = getattr(context, name, colander.null)
            result[name] = val
        return result

    def set(self, struct, omit=()):
        if not is_nonstr_iter(omit):
            omit = (omit,)
        for k in struct:
            if not k in omit:
                setattr(self.context, k, struct[k])

    def after_set(self):
        event = ObjectModified(self.context)
        self.request.registry.subscribers((event, self.context), None)
        self.request.flash_with_undo('Updated properties', 'success')

def is_propertied(resource, registry=None):
    if registry is None:
        registry = get_current_registry()
    sheets = registry.content.metadata(resource, 'propertysheets', None)
    return sheets is not None

class _PropertiedPredicate(object):
    is_propertied = staticmethod(is_propertied) # for testing
    
    def __init__(self, val, config):
        self.val = bool(val)
        self.registry = config.registry

    def text(self):
        return 'propertied = %s' % self.val

    phash = text

    def __call__(self, context, request):
        return self.is_propertied(context, self.registry) == self.val

def includeme(config): # pragma: no cover
    config.add_view_predicate('propertied', _PropertiedPredicate)
