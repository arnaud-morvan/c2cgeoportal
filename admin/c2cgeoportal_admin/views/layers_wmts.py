from functools import partial
from pyramid.httpexceptions import HTTPFound, HTTPNotFound
from pyramid.view import view_defaults
from pyramid.view import view_config

from sqlalchemy import inspect, insert, delete, update
from zope.sqlalchemy import mark_changed

from c2cgeoform.schema import GeoFormSchemaNode
from c2cgeoform.views.abstract_views import ListField, ItemAction
from deform import ValidationFailure
from deform.widget import FormWidget

from c2cgeoportal_admin import _
from c2cgeoportal_admin.schemas.dimensions import dimensions_schema_node
from c2cgeoportal_commons.models.main import \
    LayerWMTS, LayerWMS, LayerGroup, OGCServer, TreeItem
from c2cgeoportal_admin.schemas.metadata import metadatas_schema_node
from c2cgeoportal_admin.schemas.interfaces import interfaces_schema_node
from c2cgeoportal_admin.schemas.restriction_areas import restrictionareas_schema_node
from c2cgeoportal_admin.schemas.treeitem import parent_id_node
from c2cgeoportal_admin.views.dimension_layers import DimensionLayerViews

_list_field = partial(ListField, LayerWMTS)

base_schema = GeoFormSchemaNode(LayerWMTS, widget=FormWidget(fields_template='layer_fields'))
base_schema.add(dimensions_schema_node.clone())
base_schema.add(metadatas_schema_node.clone())
base_schema.add(interfaces_schema_node.clone())
base_schema.add(restrictionareas_schema_node.clone())
base_schema.add_unique_validator(LayerWMTS.name, LayerWMTS.id)
base_schema.add(parent_id_node(LayerGroup))


@view_defaults(match_param='table=layers_wmts')
class LayerWmtsViews(DimensionLayerViews):
    _list_fields = DimensionLayerViews._list_fields + [
        _list_field('url'),
        _list_field('layer'),
        _list_field('style'),
        _list_field('matrix_set'),
        _list_field('image_type'),
    ] + DimensionLayerViews._extra_list_fields
    _id_field = 'id'
    _model = LayerWMTS
    _base_schema = base_schema

    def _base_query(self, query=None):
        return super()._base_query(
            self._request.dbsession.query(LayerWMTS).distinct())

    @view_config(route_name='c2cgeoform_index',
                 renderer='../templates/index.jinja2')
    def index(self):
        return super().index()

    @view_config(route_name='c2cgeoform_grid',
                 renderer='json')
    def grid(self):
        return super().grid()

    def _item_actions(self, item):
        actions = super()._item_actions(item)
        if inspect(item).persistent:
            actions.insert(next((i for i, v in enumerate(actions) if v.name() == 'delete')), ItemAction(
                name='convert_to_wms',
                label=_('Convert to WMS'),
                icon='glyphicon icon-l_wmts',
                url=self._request.route_url(
                    'convert_to_wms',
                    id=getattr(item, self._id_field)
                )
            ))
        return actions

    @view_config(route_name='c2cgeoform_item',
                 request_method='GET',
                 renderer='../templates/edit.jinja2')
    def view(self):
        if self._is_new():
            dbsession = self._request.dbsession
            default_wmts = LayerWMTS.get_default(dbsession)
            if default_wmts:
                return self.copy(default_wmts, excludes=['name', 'layer'])
        return super().edit()

    @view_config(route_name='c2cgeoform_item',
                 request_method='POST',
                 renderer='../templates/edit.jinja2')
    def save(self):
        return super().save()

    @view_config(route_name='c2cgeoform_item',
                 request_method='DELETE',
                 renderer='json')
    def delete(self):
        return super().delete()

    @view_config(route_name='c2cgeoform_item_duplicate',
                 request_method='GET',
                 renderer='../templates/edit.jinja2')
    def duplicate(self):
        return super().duplicate()

    def _convert_to_wmts_form(self):
        return self._form(title=_('Convert WMS layer to WMTS layer'))

    @view_config(route_name='convert_to_wmts',
                 request_method='GET',
                 match_param='table=layers_wms',
                 renderer='../templates/edit.jinja2')
    def convert_to_wmts_edit(self):
        obj = self._request.dbsession.query(LayerWMS).get(self._request.matchdict.get('id'))
        if obj is None:
            raise HTTPNotFound()

        form = self._convert_to_wmts_form()

        dict_ = {}
        default_wmts = LayerWMTS.get_default(self._request.dbsession)
        if default_wmts:
            dict_.update({
                'url': default_wmts.url,
                'matrix_set': default_wmts.matrix_set
            })
        dict_.update(form.schema.dictify(obj))
        dict_.update({
            'image_type': obj.ogc_server.image_type,
        })

        self._populate_widgets(form.schema)
        rendered = form.render(dict_,
                               request=self._request,
                               actions=[])

        return {
            'form': rendered,
            'deform_dependencies': form.get_widget_resources()
        }

    @view_config(route_name='convert_to_wmts',
                 request_method='POST',
                 match_param='table=layers_wms',
                 renderer='../templates/edit.jinja2')
    def convert_to_wmts_save(self):
        src = self._request.dbsession.query(LayerWMS).get(self._request.matchdict.get('id'))
        if src is None:
            raise HTTPNotFound()

        try:
            form = self._convert_to_wmts_form()
            form_data = self._request.POST.items()
            self._appstruct = form.validate(form_data)

            dbsession = self._request.dbsession
            with dbsession.no_autoflush:
                d = delete(LayerWMS.__table__)
                d = d.where(LayerWMS.__table__.c.id == src.id)
                i = insert(LayerWMTS.__table__)
                i = i.values({
                    'id': src.id,
                    'layer': src.layer,
                    'image_type': src.ogc_server.image_type,
                    'style': src.style,
                    'url': '',
                    'matrix_set': ''
                })
                u = update(TreeItem.__table__)
                u = u.where(TreeItem.__table__.c.id == src.id)
                u = u.values({'type': 'l_wmts'})
                dbsession.execute(d)
                dbsession.execute(i)
                dbsession.execute(u)
                dbsession.expunge(src)

                dbsession.flush()
                mark_changed(dbsession)

            obj = dbsession.query(LayerWMTS).get(src.id)

            with self._request.dbsession.no_autoflush:
                obj = form.schema.objectify(self._appstruct, obj)

            self._obj = self._request.dbsession.merge(obj)
            self._request.dbsession.flush()
            return HTTPFound(
                self._request.route_url(
                    'c2cgeoform_item',
                    table='layers_wmts',
                    action='edit',
                    id=obj.id,
                    _query=[('msg_col', 'submit_ok')]))

        except ValidationFailure as e:
            # FIXME see https://github.com/Pylons/deform/pull/243
            self._populate_widgets(form.schema)
            rendered = e.field.widget.serialize(
                e.field,
                e.cstruct,
                request=self._request,
                actions=[])
            return {
                'form': rendered,
                'deform_dependencies': form.get_widget_resources()
            }
