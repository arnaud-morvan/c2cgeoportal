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

from c2cgeoportal_commons.models.main import \
    LayerWMS, LayerWMTS, OGCServer, LayerGroup, TreeItem

from c2cgeoportal_admin import _
from c2cgeoportal_admin.schemas.dimensions import dimensions_schema_node
from c2cgeoportal_admin.schemas.metadata import metadatas_schema_node
from c2cgeoportal_admin.schemas.interfaces import interfaces_schema_node
from c2cgeoportal_admin.schemas.restriction_areas import restrictionareas_schema_node
from c2cgeoportal_admin.schemas.treeitem import parent_id_node
from c2cgeoportal_admin.views.dimension_layers import DimensionLayerViews

_list_field = partial(ListField, LayerWMS)

base_schema = GeoFormSchemaNode(LayerWMS, widget=FormWidget(fields_template='layer_fields'))
base_schema.add(dimensions_schema_node.clone())
base_schema.add(metadatas_schema_node.clone())
base_schema.add(interfaces_schema_node.clone())
base_schema.add(restrictionareas_schema_node.clone())
base_schema.add_unique_validator(LayerWMS.name, LayerWMS.id)
base_schema.add(parent_id_node(LayerGroup))


@view_defaults(match_param='table=layers_wms')
class LayerWmsViews(DimensionLayerViews):
    _list_fields = DimensionLayerViews._list_fields + [
        _list_field('layer'),
        _list_field('style'),
        _list_field('time_mode'),
        _list_field('time_widget'),
        _list_field(
            'ogc_server',
            renderer=lambda layer_wms: layer_wms.ogc_server.name,
            sort_column=OGCServer.name,
            filter_column=OGCServer.name)
    ] + DimensionLayerViews._extra_list_fields
    _id_field = 'id'
    _model = LayerWMS
    _base_schema = base_schema

    def _base_query(self):
        return super()._base_query(
            self._request.dbsession.query(LayerWMS).distinct().
            outerjoin('ogc_server'))

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
                name='convert_to_wmts',
                label=_('Convert to WMTS'),
                icon='glyphicon icon-l_wmts',
                url=self._request.route_url(
                    'convert_to_wmts',
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
            default_wms = LayerWMS.get_default(dbsession)
            if default_wms:
                return self.copy(default_wms, excludes=['name', 'layer'])
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

    def _convert_to_wms_form(self):
        return self._form(title=_('Convert WMTS layer to WMS layer'))

    @view_config(route_name='convert_to_wms',
                 request_method='GET',
                 match_param='table=layers_wmts',
                 renderer='../templates/edit.jinja2')
    def convert_to_wms_edit(self):
        obj = self._request.dbsession.query(LayerWMTS).get(self._request.matchdict.get('id'))
        if obj is None:
            raise HTTPNotFound()

        form = self._convert_to_wms_form()

        dict_ = {}
        default_wms = LayerWMS.get_default(self._request.dbsession)
        if default_wms:
            dict_.update({
                'ogc_server_id': default_wms.ogc_server_id,
                'time_mode': default_wms.time_mode,
                'time_widget': default_wms.time_widget
            })
        dict_.update(form.schema.dictify(obj))

        self._populate_widgets(form.schema)
        rendered = form.render(dict_,
                               request=self._request,
                               actions=[])

        return {
            'form': rendered,
            'deform_dependencies': form.get_widget_resources()
        }

    @view_config(route_name='convert_to_wms',
                 request_method='POST',
                 match_param='table=layers_wmts',
                 renderer='../templates/edit.jinja2')
    def convert_to_wms_save(self):
        src = self._request.dbsession.query(LayerWMTS).get(self._request.matchdict.get('id'))
        if src is None:
            raise HTTPNotFound()

        try:
            form = self._convert_to_wms_form()
            form_data = self._request.POST.items()
            self._appstruct = form.validate(form_data)

            dbsession = self._request.dbsession
            with dbsession.no_autoflush:
                d = delete(LayerWMTS.__table__)
                d = d.where(LayerWMTS.__table__.c.id == src.id)
                i = insert(LayerWMS.__table__)
                i = i.values({
                    'id': src.id,
                    'layer': src.layer,
                    'style': src.style,
                    'ogc_server_id': dbsession.query(OGCServer.id).order_by(OGCServer.id).first()[0],
                    'time_mode': 'disabled',
                    'time_widget': 'slider'
                })
                u = update(TreeItem.__table__)
                u = u.where(TreeItem.__table__.c.id == src.id)
                u = u.values({'type': 'l_wms'})
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
                    table='layers_wms',
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
