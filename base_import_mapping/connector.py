# coding: utf-8
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2015-TODAY Akretion (<http://www.akretion.com>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

import sys

from openerp import models, fields, api
from openerp.addons.connector import backend
from openerp.addons.connector.connector import install_in_connector
from openerp.addons.connector.exception import NoConnectorUnitError
from openerp.addons.connector.connector import ConnectorEnvironment
from openerp.addons.connector.session import ConnectorSession
from openerp.addons.connector.unit.mapper import ImportMapper
from openerp.addons.base_import.models import FIELDS_RECURSION_LIMIT


class ir_fields_converter(models.Model):
    _inherit = 'ir.fields.converter'

    @api.model
    def for_model(self, model, fromtype=str):

        fn = super(ir_fields_converter, self).for_model(model, fromtype)

        def fn_with_mapping(record, log):

            record_to_convert = {}
            record_to_map = {}

            for field, value in record.iteritems():
                if field in (None, 'id', '.id'):
                    continue

                if field in model._fields.keys():
                    record_to_convert[field] = value
                else:
                    record_to_map[field] = value

            converted = fn(record_to_convert, log)
            converted.update(record_to_map)
            return converted

        return fn_with_mapping


class IrModelData(models.Model):
    _inherit = 'ir.model.data'

    @api.model
    def _map_fields(self, model, vals):

        mapper = BackendBaseImport.get_mapper(self.env, model)
        if mapper:
            vals.update(mapper.map_record(vals).values())
            for map_field, label in mapper._map_fields:
                if map_field in vals:
                    del vals[map_field]

        res = vals
        model_obj = self.env[model]
        for field_name, value in vals.items():
            if field_name in model_obj._fields:
                field = model_obj._fields[field_name]
                if field.type in ('one2many', 'many2many'):

                    if not isinstance(value, list):
                        continue

                    many_res = []
                    for many_val in value:
                        many_val = list(many_val)
                        if len(many_val) == 3 and \
                                isinstance(many_val[2], dict):
                            many_val[2] = self._map_fields(
                                field.comodel_name, many_val[2])
                        many_res.append(tuple(many_val))
                    res[field_name] = many_res

        return res

    @api.model
    def _update(self, model, module, values, xml_id=False, store=True,
                noupdate=False, mode='init', res_id=False, context=None):
        context = context or {}
        values = self._map_fields(model, values)
        return super(IrModelData, self)._update(model, module, values,
                                                xml_id=xml_id, store=store,
                                                noupdate=noupdate, mode=mode,
                                                res_id=res_id, context=context
                                                )


class ir_import(models.Model):
    _inherit = 'base_import.import'

    @api.model
    def get_fields(self, model, depth=FIELDS_RECURSION_LIMIT):

        res = super(ir_import, self).get_fields(model, depth=depth)

        mapper = BackendBaseImport.get_mapper(self.env, model)
        if mapper:
            for field, label in mapper._map_fields:
                res.append({
                    'id': None,
                    'name': field,
                    'string': label,
                    'required': False,
                    'fields': [],
                })

        return res


class ImportMapperBase(ImportMapper):
    _map_fields = []


base_import = backend.Backend('base_import_mapping')
"""  Backend Base Import """

base_import_base = backend.Backend(parent=base_import,
                                   version='1.0')
""" Backend Base Import version 1.0 """


class BackendBaseImport(models.Model):
    _name = 'backend.base.import'
    _description = 'Base Import Backend'
    _inherit = 'connector.backend'

    _backend_type = 'base_import_mapping'

    @classmethod
    def get_mapper(cls, env, model):
        mapper = None
        backend_records = env[cls._name].search([])
        if backend_records:
            session = ConnectorSession(env.cr, env.uid)
            connector_env = ConnectorEnvironment(backend_records[0],
                                                 session, model)
            try:
                mapper = connector_env.get_connector_unit(ImportMapperBase)
            except NoConnectorUnitError:
                pass
        return mapper

    @api.model
    def select_versions(self):
        """ Available versions in the backend.
        """
        return [('1.0', '1.0')]

    @api.model
    def _select_versions(self):
        """ Available versions in the backend.
        If you want to add a version, do not override this
        method, but ``select_version``.
        """
        return self.select_versions()

    version = fields.Selection(
        _select_versions,
        string='Version',
        required=True
    )
    company_id = fields.Many2one('res.company', string='Company')

_add_fake_fields_original = models.BaseModel._add_fake_fields


@api.model
def _add_fake_fields(self, fields):
    if 'openerp.addons.base_import_mapping' in sys.modules:
        fields = _add_fake_fields_original(self, fields)
        mapper = BackendBaseImport.get_mapper(self.env, self._name)
        if mapper and mapper._map_fields:
            from openerp.fields import Char
            for field, label in mapper._map_fields:
                fields[field] = Char(field)
    return fields


install_in_connector()

models.BaseModel._add_fake_fields = _add_fake_fields
