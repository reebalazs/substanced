import colander
import deform.widget

from hypatia.interfaces import IIndex
from hypatia.query import parse_query

from pyramid.httpexceptions import HTTPFound

from pyramid.view import view_defaults

from ...objectmap import find_objectmap
from ...interfaces import ICatalog, IFolder

from ...catalog import logger
from ...catalog.discriminators import (
    AllowedDiscriminator,
    CatalogViewDiscriminator,
    )
from ...catalog.indexes import (
    IndexSchema,
    PermissionsSchemaNode,
    )
from ...form import FormView
from ...schema import (
    Schema,
    NameSchemaNode,
    )
    
from .. import mgmt_view

@mgmt_view(
    name='add_catalog_service',
    tab_condition=False,
    permission='sdi.add-services',
    )
def add_catalog_service(context, request):
    catalog = request.registry.content.create('Catalog')
    context['catalog'] = catalog
    return HTTPFound(location=request.mgmt_path(context))

def context_is_an_index(context, request):
    return request.registry.content.metadata(context, 'is_index', False)

class AddIndexSchema(IndexSchema):
    name = NameSchemaNode(editing=context_is_an_index,
                          insert_before='sd_category')
    reindex = colander.SchemaNode(
        colander.Bool(),
        default=True,
        )

class _AddIndexView(FormView):
    schema = AddIndexSchema()
    buttons = ('add',)
    def add_success(self, appstruct):
        registry = self.request.registry
        name = appstruct['name']
        index = self.makeindex(appstruct, registry)
        self.context[name] = index
        index.sd_category = appstruct['category']
        if appstruct['reindex']:
            self.context.reindex(indexes=(name,), registry=registry)
        return HTTPFound(location=self.request.mgmt_path(self.context))

    def makeindex(self, appstruct, registry):
        name = appstruct['name']
        discriminator = CatalogViewDiscriminator(name)
        index = registry.content.create(self.index_type_name, discriminator)
        return index

    @property
    def title(self):
        return 'Add %s' % self.index_type_name

@mgmt_view(
    context=ICatalog,
    name='add_path_index',
    tab_condition=False,
    permission='sdi.add-content',
    renderer='substanced.sdi:templates/form.pt'
    )
class AddPathIndexView(_AddIndexView):
    title = 'Add Path Index'
    def makeindex(self, appstruct, registry):
        index = registry.content.create('Path Index')
        return index
        
@mgmt_view(
    context=ICatalog,
    name='add_field_index',
    tab_condition=False,
    permission='sdi.add-content',
    renderer='substanced.sdi:templates/form.pt'
    )
class AddFieldIndexView(_AddIndexView):
    index_type_name = 'Field Index'

@mgmt_view(
    context=ICatalog,
    name='add_keyword_index',
    tab_condition=False,
    permission='sdi.add-content',
    renderer='substanced.sdi:templates/form.pt'
    )
class AddKeywordIndexView(_AddIndexView):
    index_type_name = 'Keyword Index'

@mgmt_view(
    context=ICatalog,
    name='add_text_index',
    tab_condition=False,
    permission='sdi.add-content',
    renderer='substanced.sdi:templates/form.pt'
    )
class AddTextIndexView(_AddIndexView):
    index_type_name = 'Text Index'

class AddAllowedIndexSchema(AddIndexSchema):
    permissions = PermissionsSchemaNode(missing=())

@mgmt_view(
    context=ICatalog,
    name='add_allowed_index',
    tab_condition=False,
    permission='sdi.add-content',
    renderer='substanced.sdi:templates/form.pt'
    )
class AddAllowedIndexView(_AddIndexView):
    schema = AddAllowedIndexSchema()
    title = 'Add Allowed Index'

    def makeindex(self, appstruct, registry):
        permissions = tuple(sorted(appstruct['permissions']))
        discriminator = AllowedDiscriminator(permissions)
        index = registry.content.create('Allowed Index', discriminator)
        return index
        
class Facets(colander.SequenceSchema):
    facet = colander.SchemaNode(
        colander.String(),
        )

class AddFacetIndexSchema(AddIndexSchema):
    facets = Facets(missing=())

@mgmt_view(
    context=ICatalog,
    name='add_facet_index',
    tab_condition=False,
    permission='sdi.add-content',
    renderer='substanced.sdi:templates/form.pt'
    )
class AddFacetIndexView(_AddIndexView):
    schema = AddFacetIndexSchema()
    title = 'Add Facet Index'

    def makeindex(self, appstruct, registry):
        name = appstruct['name']
        discriminator = CatalogViewDiscriminator(name)
        facets = tuple(appstruct['facets'])
        index = registry.content.create('Facet Index', discriminator, facets)
        return index
        
@view_defaults(
    name='manage_catalog',
    context=ICatalog,
    renderer='templates/catalog.pt',
    permission='sdi.manage-catalog'
    )
class ManageCatalog(object):
    def __init__(self, context, request):
        self.context = context
        self.request = request

    @property
    def redir_location(self):
        return self.request.mgmt_path(self.context, '@@manage_catalog')
        
    @mgmt_view(request_method='GET', tab_title='Manage')
    def view(self):
        cataloglen = len(self.context.objectids)
        return dict(cataloglen=cataloglen)

    @mgmt_view(request_method='POST', request_param='reindex', check_csrf=True)
    def reindex(self):
        self.context.reindex()
        self.request.session.flash('Catalog reindexed')
        return HTTPFound(location=self.redir_location)

@view_defaults(
    name='manage_index',
    context=IIndex,
    renderer='templates/index.pt',
    permission='sdi.manage-catalog')
class ManageIndex(object):
    def __init__(self, context, request):
        self.context = context
        self.request = request

    @property
    def redir_location(self):
        return self.request.mgmt_path(self.context, '@@manage_index')

    @mgmt_view(request_method='GET', tab_title='Manage')
    def view(self):
        index = self.context
        indexed = index.indexed_count()
        not_indexed = index.not_indexed_count()
        index_name = index.__name__
        return dict(
            indexed=indexed,
            not_indexed=not_indexed,
            index_name=index_name,
            index_type = index.__class__.__name__,
            )

    @mgmt_view(request_method='POST', request_param='reindex', check_csrf=True)
    def reindex(self):
        index_name = self.context.__name__
        catalog  = self.context.__parent__
        if ICatalog.providedBy(catalog):
            catalog.reindex(indexes=[index_name])
            self.request.session.flash('Index "%s" reindexed' % index_name,
                                       'success')
        else:
            self.request.session.flash(
                'Cannot reindex an index unless it is contained in a catalog',
                'error'
                )
        return HTTPFound(location=self.redir_location)

class SearchSchema(Schema):
    cqe_expression = colander.SchemaNode(
        colander.String(),
        widget = deform.widget.TextAreaWidget(rows=10, cols=120),
        title='CQE Expression',
        )

@mgmt_view(context=ICatalog, name='search_catalog', 
           permission='sdi.manage-catalog', 
           renderer='templates/search.pt', tab_title='Search')
class SearchCatalogView(FormView):
    schema = SearchSchema(title='Expression')
    buttons = ('search',)
    catalog_results = None
    logger = logger
    parse_query = staticmethod(parse_query) # for testing
    find_objectmap = staticmethod(find_objectmap) # for testing

    def search_success(self, appstruct):
        """ Accept a CQE expression and a permitted value and return a 
        sequence of object renderings """
        self.request.session['catalogsearch.appstruct'] = appstruct
        context = self.context
        return HTTPFound(
            location=self.request.mgmt_path(context, '@@search_catalog')
            )

    def show(self, form):
        appstruct = self.request.session.pop('catalogsearch.appstruct',
                                             colander.null)
        searchresults = ()
        if appstruct:
            expr = appstruct['cqe_expression']
            try:
                q = self.parse_query(expr, self.context)
                resultset = q.execute().all(resolve=False)
            except Exception as e:
                self.logger.exception('During search')
                cls_name = e.__class__.__name__
                msg = 'Query failed (%s: %s)' % (cls_name, e.args[0])
                self.request.session.flash(msg, 'error')
            else:
                objectmap = self.find_objectmap(self.context)
                resolve = objectmap.object_for
                searchresults = list([(oid, resolve(oid)) for oid in resultset])
                if not searchresults:
                    searchresults = [('', 'No results')]
                self.request.session.flash('Query succeeded', 'success')
        return {
            'searchresults':searchresults,
            'form':form.render(appstruct=appstruct),
            }

# reindex button handler

@mgmt_view(
    context=IFolder,
    content_type='Catalog',
    name='contents',
    request_param='form.reindex',
    request_method='POST',
    renderer='substanced.sdi:templates/contents.pt',
    permission='sdi.manage-contents',
    tab_condition=False,
    )
def reindex_indexes(context, request):
    toreindex = request.POST.getall('item-modify')
    if toreindex:
        context.reindex(indexes=toreindex, registry=request.registry)
        request.session.flash(
            'Reindex of selected indexes succeeded',
            'success'
            )
    else:
        request.session.flash(
            'No indexes selected to reindex',
            'error'
            )
        
    return HTTPFound(request.mgmt_path(context, '@@contents'))

