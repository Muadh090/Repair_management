# -*- coding: utf-8 -*-

from odoo import api, fields, models
from dateutil.relativedelta import relativedelta


class ProductTemplateRepair(models.Model):
    _inherit = 'product.template'

    is_repair_part = fields.Boolean(
        string='Is Repair Part',
        default=False,
    )
    part_category = fields.Selection(
        selection=[
            ('screen', 'Screen'),
            ('battery', 'Battery'),
            ('charging_port', 'Charging Port'),
            ('speaker', 'Speaker'),
            ('camera', 'Camera'),
            ('motherboard', 'Motherboard'),
            ('casing', 'Casing'),
            ('cable', 'Cable'),
            ('tool', 'Tool'),
            ('consumable', 'Consumable'),
            ('other', 'Other'),
        ],
        string='Part Category',
    )
    compatible_devices = fields.Text(
        string='Compatible Devices',
        help='List of devices this part is compatible with.',
    )
    part_code = fields.Char(
        string='Part Code',
        help='Internal part reference code.',
    )
    minimum_stock_qty = fields.Float(
        string='Minimum Stock Qty',
        default=0.0,
    )
    reorder_qty = fields.Float(
        string='Reorder Quantity',
        default=0.0,
    )
    average_repair_usage = fields.Float(
        string='Avg Monthly Usage',
        compute='_compute_average_repair_usage',
        store=True,
    )
    is_critical_part = fields.Boolean(
        string='Critical Part',
        default=False,
        help='Critical parts trigger immediate reorder alerts.',
    )
    supplier_ids_repair = fields.Many2many(
        comodel_name='res.partner',
        relation='product_template_repair_supplier_rel',
        column1='product_tmpl_id',
        column2='partner_id',
        string='Preferred Suppliers',
        domain="[('supplier_rank', '>', 0)]",
    )
    last_purchase_price = fields.Float(
        string='Last Purchase Price',
        compute='_compute_last_purchase',
    )
    last_purchase_date = fields.Date(
        string='Last Purchase Date',
        compute='_compute_last_purchase',
    )
    total_used_in_repairs = fields.Integer(
        string='Total Used in Repairs',
        compute='_compute_total_used_in_repairs',
    )
    days_of_stock = fields.Float(
        string='Days of Stock',
        compute='_compute_days_of_stock',
    )

    # -----------------------------------------------------------------
    # COMPUTE METHODS
    # -----------------------------------------------------------------
    @api.depends('product_variant_ids')
    def _compute_average_repair_usage(self):
        """Average parts used per month over the last 6 months."""
        six_months_ago = fields.Date.today() - relativedelta(months=6)
        RepairPartsLine = self.env['repair.parts.line']
        for tmpl in self:
            product_ids = tmpl.product_variant_ids.ids
            if not product_ids:
                tmpl.average_repair_usage = 0.0
                continue
            lines = RepairPartsLine.search([
                ('product_id', 'in', product_ids),
                ('job_id.date_received', '>=', six_months_ago),
            ])
            total_qty = sum(lines.mapped('quantity'))
            tmpl.average_repair_usage = total_qty / 6.0

    def _compute_last_purchase(self):
        """Last purchase price and date from confirmed purchase orders."""
        PurchaseOrderLine = self.env['purchase.order.line']
        for tmpl in self:
            product_ids = tmpl.product_variant_ids.ids
            if not product_ids:
                tmpl.last_purchase_price = 0.0
                tmpl.last_purchase_date = False
                continue
            last_line = PurchaseOrderLine.search([
                ('product_id', 'in', product_ids),
                ('order_id.state', 'in', ('purchase', 'done')),
            ], order='date_order desc', limit=1)
            if last_line:
                tmpl.last_purchase_price = last_line.price_unit
                tmpl.last_purchase_date = last_line.order_id.date_order.date()
            else:
                tmpl.last_purchase_price = 0.0
                tmpl.last_purchase_date = False

    def _compute_total_used_in_repairs(self):
        """Total times this part has been used across all repair jobs."""
        RepairPartsLine = self.env['repair.parts.line']
        for tmpl in self:
            product_ids = tmpl.product_variant_ids.ids
            if not product_ids:
                tmpl.total_used_in_repairs = 0
                continue
            lines = RepairPartsLine.search([
                ('product_id', 'in', product_ids),
            ])
            tmpl.total_used_in_repairs = int(sum(lines.mapped('quantity')))

    @api.depends('product_variant_ids')
    def _compute_days_of_stock(self):
        """Current stock divided by average daily usage."""
        for tmpl in self:
            qty_on_hand = sum(
                tmpl.product_variant_ids.mapped('qty_available')
            )
            if tmpl.average_repair_usage > 0:
                daily_usage = tmpl.average_repair_usage / 30.0
                tmpl.days_of_stock = qty_on_hand / daily_usage
            else:
                tmpl.days_of_stock = 0.0
