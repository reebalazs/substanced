import itertools
import re

import colander


from pyramid.httpexceptions import HTTPFound
from pyramid.view import view_defaults

from ...folder import FolderKeyError
from ...form import FormView
from ...interfaces import IFolder
from ...objectmap import find_objectmap
from ...schema import Schema
from ...util import oid_of

from .. import (
    mgmt_view,
    sdi_add_views,
    sdi_folder_contents,
    default_sdi_buttons,
    default_sdi_columns,
    )

_marker = object()

def rename_duplicated_resource(context, name):
    """Finds next available name inside container by appending
    dash and positive number.
    """
    if name not in context:
        return name

    m = re.search(r'-(\d+)$', name)
    if m:
        new_id = int(m.groups()[0]) + 1
        new_name = name.rsplit('-', 1)[0] + u'-%d' % new_id
    else:
        new_name = name + u'-1'

    if new_name in context:
        return rename_duplicated_resource(context, new_name)
    else:
        return new_name

@colander.deferred
def name_validator(node, kw):
    context = kw['request'].context

    def namecheck(node, value):
        try:
            context.check_name(value)
        except Exception as e:
            raise colander.Invalid(node, e.args[0], value)

    return colander.All(
        colander.Length(min=1, max=100),
        namecheck,
        )

class AddFolderSchema(Schema):
    name = colander.SchemaNode(
        colander.String(),
        validator=name_validator,
        )

@mgmt_view(
    context=IFolder,
    name='add_folder',
    tab_condition=False,
    permission='sdi.add-content',
    renderer='substanced.sdi:templates/form.pt'
    )
class AddFolderView(FormView):
    title = 'Add Folder'
    schema = AddFolderSchema()
    buttons = ('add',)

    def add_success(self, appstruct):
        registry = self.request.registry
        name = appstruct['name']
        folder = registry.content.create('Folder')
        self.context[name] = folder
        return HTTPFound(location=self.request.mgmt_path(self.context))

@view_defaults(
    context=IFolder,
    name='contents',
    renderer='templates/contents.pt'
    )
class FolderContentsViews(object):

    sdi_add_views = staticmethod(sdi_add_views) # for testing
    sdi_folder_contents = staticmethod(sdi_folder_contents) # for testing

    def __init__(self, context, request):
        self.context = context
        self.request = request

    def _buttons(self, context, request):
        buttons = default_sdi_buttons(context, request)
        custom_buttons = request.registry.content.metadata(
            context, 'buttons', _marker)
        if custom_buttons is None:
            return []
        if custom_buttons is not _marker:
            buttons = custom_buttons(context, request, buttons)
        return buttons

    def _column_headers(self, context, request):
        headers = []
        non_sortable = [0]
        non_filterable = [0]

        columns = default_sdi_columns(self, None, request)

        custom_columns = request.registry.content.metadata(
            context, 'columns', _marker)

        if custom_columns is None:
            return headers, non_sortable, non_filterable

        if custom_columns is not _marker:
            columns = custom_columns(context, None, request, columns)
        
        for order, column in enumerate(columns):
            headers.append(column['name'])
            sortable = column.get('sortable', True)
            if not sortable:
                non_sortable.append(order + 1)
            filterable = column.get('filterable', True)
            if not filterable:
                non_filterable.append(order + 1)

        return headers, non_sortable, non_filterable

    @mgmt_view(
        request_method='GET',
        permission='sdi.view'
        )
    def show(self):
        request = self.request
        context = self.context

        headers, non_sortable, non_filterable = self._column_headers(
            context, request
            )
        buttons = self._buttons(context, request)

        addables = self.sdi_add_views(context, request)

        seq = self.sdi_folder_contents(context, request) # generator

        # We need an accurate length but len(self.context) will not take into
        # account hidden items. To gen an accurate length we tee the generator
        # and exaust one copy to produce a sum, we use the other copy as the
        # items we pass to the template.  This is probably unsat for huge
        # folders, but at least has a slight advantage over doing
        # len(list(seq)) because we don't unnecessarily create a large data
        # structure in memory.
        items, items_copy = itertools.tee(seq)
        num_items = sum(1 for _ in items_copy) 

        return dict(
            items=items, # NB: do not use "seq" here, we teed it above
            num_items=num_items,
            addables=addables,
            headers=headers,
            buttons=buttons,
            non_filterable=non_filterable,
            non_sortable=non_sortable,
            )

    @mgmt_view(
        request_method='POST',
        request_param="form.delete",
        permission='sdi.manage-contents',
        tab_condition=False,
        check_csrf=True
        )
    def delete(self):
        request = self.request
        context = self.context
        todelete = request.POST.getall('item-modify')
        deleted = 0
        for name in todelete:
            v = context.get(name)
            if v is not None:
                del context[name]
                deleted += 1
        if not deleted:
            msg = 'No items deleted'
            request.session.flash(msg)
        elif deleted == 1:
            msg = 'Deleted 1 item'
            request.flash_with_undo(msg)
        else:
            msg = 'Deleted %s items' % deleted
            request.flash_with_undo(msg)
        return HTTPFound(request.mgmt_path(context, '@@contents'))

    @mgmt_view(
        request_method='POST',
        request_param="form.duplicate",
        permission='sdi.manage-contents',
        tab_condition=False,
        check_csrf=True
        )
    def duplicate(self):
        request = self.request
        context = self.context
        toduplicate = request.POST.getall('item-modify')
        for name in toduplicate:
            newname = rename_duplicated_resource(context, name)
            context.copy(name, context, newname)
        if not len(toduplicate):
            msg = 'No items duplicated'
            request.session.flash(msg)
        elif len(toduplicate) == 1:
            msg = 'Duplicated 1 item'
            request.flash_with_undo(msg)
        else:
            msg = 'Duplicated %s items' % len(toduplicate)
            request.flash_with_undo(msg)
        return HTTPFound(request.mgmt_path(context, '@@contents'))

    @mgmt_view(
        request_method='POST',
        request_param="form.rename",
        permission='sdi.manage-contents',
        renderer='templates/rename.pt',
        tab_condition=False,
        check_csrf=True
        )
    def rename(self):
        request = self.request
        context = self.context
        torename = request.POST.getall('item-modify')
        if not torename:
            request.session.flash('No items renamed')
            return HTTPFound(request.mgmt_path(context, '@@contents'))
        return dict(torename=[context.get(name)
                              for name in torename
                              if name in context])

    @mgmt_view(
        request_method='POST',
        request_param="form.rename_finish",
        name="rename",
        permission='sdi.manage-contents',
        tab_condition=False,
        check_csrf=True
        )
    def rename_finish(self):
        request = self.request
        context = self.context

        if self.request.POST.get('form.rename_finish') == "cancel":
            request.session.flash('No items renamed')
            return HTTPFound(request.mgmt_path(context, '@@contents'))

        torename = request.POST.getall('item-rename')
        try:
            for old_name in torename:
                new_name = request.POST.get(old_name)
                context.rename(old_name, new_name)
        except FolderKeyError as e:
            self.request.session.flash(e.args[0], 'error')
            raise HTTPFound(request.mgmt_path(context, '@@contents'))

        if len(torename) == 1:
            msg = 'Renamed 1 item'
            request.flash_with_undo(msg)
        else:
            msg = 'Renamed %s items' % len(torename)
            request.flash_with_undo(msg)
        return HTTPFound(request.mgmt_path(context, '@@contents'))

    @mgmt_view(
        request_method='POST',
        request_param="form.copy",
        permission='sdi.view',
        tab_condition=False,
        check_csrf=True
        )
    def copy(self):
        request = self.request
        context = self.context
        tocopy = request.POST.getall('item-modify')

        if tocopy:
            l = []
            for name in tocopy:
                obj = context.get(name)
                if obj is not None:
                    l.append(oid_of(obj))
            request.session['tocopy'] = l
            request.session.flash('Choose where to copy the items:', 'info')
        else:
            request.session.flash('No items to copy')

        return HTTPFound(request.mgmt_path(context, '@@contents'))

    @mgmt_view(
        request_method='POST',
        request_param="form.copy_finish",
        permission='sdi.manage-contents',
        tab_condition=False,
        check_csrf=True
        )
    def copy_finish(self):
        request = self.request
        context = self.context
        objectmap = find_objectmap(context)
        tocopy = request.session['tocopy']
        del request.session['tocopy']

        if self.request.POST.get('form.copy_finish') == "cancel":
            request.session.flash('No items copied')
            return HTTPFound(request.mgmt_path(context, '@@contents'))

        try:
            for oid in tocopy:
                obj = objectmap.object_for(oid)
                obj.__parent__.copy(obj.__name__, context)
        except FolderKeyError as e:
            self.request.session.flash(e.args[0], 'error')
            raise HTTPFound(request.mgmt_path(context, '@@contents'))

        if len(tocopy) == 1:
            msg = 'Copied 1 item'
            request.flash_with_undo(msg)
        else:
            msg = 'Copied %s items' % len(tocopy)
            request.flash_with_undo(msg)

        return HTTPFound(request.mgmt_path(context, '@@contents'))

    @mgmt_view(
        request_method='POST',
        request_param="form.move",
        permission='sdi.view',
        tab_condition=False,
        check_csrf=True
        )
    def move(self):
        request = self.request
        context = self.context
        tomove = request.POST.getall('item-modify')

        if tomove:
            l = []
            for name in tomove:
                obj = context.get(name)
                if obj is not None:
                    l.append(oid_of(obj))
            request.session['tomove'] = l
            request.session.flash('Choose where to move the items:', 'info')
        else:
            request.session.flash('No items to move')

        return HTTPFound(request.mgmt_path(context, '@@contents'))

    @mgmt_view(
        request_method='POST',
        request_param="form.move_finish",
        permission='sdi.manage-contents',
        tab_condition=False,
        check_csrf=True
        )
    def move_finish(self):
        request = self.request
        context = self.context
        objectmap = find_objectmap(context)
        tomove = request.session['tomove']
        del request.session['tomove']

        if self.request.POST.get('form.move_finish') == "cancel":
            request.session.flash('No items moved')
            return HTTPFound(request.mgmt_path(context, '@@contents'))

        try:
            for oid in tomove:
                obj = objectmap.object_for(oid)
                obj.__parent__.move(obj.__name__, context)
        except FolderKeyError as e:
            self.request.session.flash(e.args[0], 'error')
            raise HTTPFound(request.mgmt_path(context, '@@contents'))

        if len(tomove) == 1:
            msg = 'Moved 1 item'
            request.flash_with_undo(msg)
        else:
            msg = 'Moved %s items' % len(tomove)
            request.flash_with_undo(msg)

        return HTTPFound(request.mgmt_path(context, '@@contents'))

