# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class RepairStockAlert(models.Model):
    _name = 'repair.stock.alert'
    _description = 'Repair Stock Alert'
    _inherit = ['mail.thread']
    _order = 'date_triggered desc, id desc'

    name = fields.Char(
        string='Alert Reference',
        readonly=True,
        copy=False,
        default='New',
    )
    product_id = fields.Many2one(
        comodel_name='product.product',
        string='Product',
        required=True,
    )
    warehouse_id = fields.Many2one(
        comodel_name='stock.warehouse',
        string='Warehouse',
    )
    branch_id = fields.Many2one(
        comodel_name='res.branch',
        string='Branch',
    )
    current_stock = fields.Float(
        string='Current Stock',
        compute='_compute_current_stock',
        store=True,
        digits='Product Unit of Measure',
    )
    minimum_stock = fields.Float(
        string='Minimum Stock',
        related='product_id.product_tmpl_id.minimum_stock_qty',
        store=True,
    )
    shortage_qty = fields.Float(
        string='Shortage Quantity',
        compute='_compute_shortage_qty',
        store=True,
        digits='Product Unit of Measure',
    )
    alert_type = fields.Selection(
        selection=[
            ('low_stock', 'Low Stock'),
            ('out_of_stock', 'Out of Stock'),
            ('critical', 'Critical'),
        ],
        string='Alert Type',
        tracking=True,
    )
    state = fields.Selection(
        selection=[
            ('active', 'Active'),
            ('acknowledged', 'Acknowledged'),
            ('resolved', 'Resolved'),
        ],
        string='Status',
        default='active',
        tracking=True,
    )
    date_triggered = fields.Datetime(
        string='Date Triggered',
        default=fields.Datetime.now,
    )
    acknowledged_by = fields.Many2one(
        comodel_name='res.users',
        string='Acknowledged By',
        readonly=True,
    )
    purchase_request_id = fields.Many2one(
        comodel_name='repair.purchase.request',
        string='Purchase Request',
        readonly=True,
    )
    notes = fields.Text(
        string='Notes',
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'repair.stock.alert'
                ) or 'New'
        return super().create(vals_list)

    @api.depends('product_id', 'warehouse_id')
    def _compute_current_stock(self):
        for record in self:
            if record.product_id and record.warehouse_id:
                location = record.warehouse_id.lot_stock_id
                quants = self.env['stock.quant'].search([
                    ('product_id', '=', record.product_id.id),
                    ('location_id', 'child_of', location.id),
                ])
                record.current_stock = sum(quants.mapped('quantity'))
            elif record.product_id:
                record.current_stock = record.product_id.qty_available
            else:
                record.current_stock = 0.0

    @api.depends('current_stock', 'minimum_stock')
    def _compute_shortage_qty(self):
        for record in self:
            diff = record.minimum_stock - record.current_stock
            record.shortage_qty = diff if diff > 0 else 0.0

    def action_acknowledge(self):
        for record in self:
            if record.state != 'active':
                raise UserError(_('Only active alerts can be acknowledged.'))
            record.write({
                'state': 'acknowledged',
                'acknowledged_by': self.env.uid,
            })

    def action_create_purchase_request(self):
        self.ensure_one()
        if self.purchase_request_id:
            raise UserError(_('A purchase request already exists for this alert.'))
        purchase_request = self.env['repair.purchase.request'].create({
            'product_id': self.product_id.id,
            'quantity': self.shortage_qty or self.product_id.product_tmpl_id.reorder_qty or 1.0,
            'warehouse_id': self.warehouse_id.id if self.warehouse_id else False,
            'branch_id': self.branch_id.id if self.branch_id else False,
            'notes': _('Auto-created from stock alert %s', self.name),
        })
        self.purchase_request_id = purchase_request.id
        if self.state == 'active':
            self.state = 'acknowledged'
            self.acknowledged_by = self.env.uid
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'repair.purchase.request',
            'res_id': purchase_request.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_resolve(self):
        for record in self:
            record.state = 'resolved'
