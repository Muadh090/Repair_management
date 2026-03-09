# -*- coding: utf-8 -*-

from odoo import fields, models


class StockWarehouseRepair(models.Model):
    _inherit = 'stock.warehouse'

    branch_id = fields.Many2one(
        comodel_name='res.branch',
        string='Branch',
    )
    manager_id = fields.Many2one(
        comodel_name='hr.employee',
        string='Warehouse Manager',
    )
    low_stock_email = fields.Char(
        string='Low Stock Alert Email',
        help='Email address to notify when stock is low.',
    )
    auto_reorder = fields.Boolean(
        string='Auto Reorder',
        default=False,
        help='Automatically create purchase requests when stock falls below minimum.',
    )
    reorder_approval_required = fields.Boolean(
        string='Reorder Approval Required',
        default=True,
        help='Purchase requests require manager approval before processing.',
    )


class StockLocationRepair(models.Model):
    _inherit = 'stock.location'

    is_repair_location = fields.Boolean(
        string='Repair Location',
        default=False,
        help='Location specifically designated for repair parts.',
    )
    branch_id = fields.Many2one(
        comodel_name='res.branch',
        string='Branch',
    )
