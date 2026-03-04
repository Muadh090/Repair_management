# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class RepairPartsLine(models.Model):
    _name = 'repair.parts.line'
    _description = 'Repair Parts Line'

    job_id = fields.Many2one(
        comodel_name='repair.job',
        string='Repair Job',
        required=True,
        ondelete='cascade',
    )
    product_id = fields.Many2one(
        comodel_name='product.product',
        string='Product',
        required=True,
    )
    description = fields.Char(
        string='Description',
        related='product_id.name',
        readonly=True,
    )
    quantity = fields.Float(
        string='Quantity',
        default=1.0,
        required=True,
    )
    unit_price = fields.Float(string='Unit Price')
    subtotal = fields.Float(
        string='Subtotal',
        compute='_compute_subtotal',
        store=True,
    )
    stock_move_id = fields.Many2one(
        comodel_name='stock.move',
        string='Stock Move',
        copy=False,
    )
    is_deducted = fields.Boolean(
        string='Stock Deducted',
        default=False,
        copy=False,
    )
    warehouse_id = fields.Many2one(
        comodel_name='stock.warehouse',
        string='Warehouse',
    )

    # -----------------------------------------------------------------
    # COMPUTE
    # -----------------------------------------------------------------
    @api.depends('quantity', 'unit_price')
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.quantity * line.unit_price

    # -----------------------------------------------------------------
    # ONCHANGE
    # -----------------------------------------------------------------
    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.unit_price = self.product_id.standard_price

    # -----------------------------------------------------------------
    # ACTIONS
    # -----------------------------------------------------------------
    def action_deduct_stock(self):
        """Create a stock move to deduct this part from the branch warehouse."""
        for line in self:
            if line.is_deducted:
                continue
            if not line.warehouse_id:
                raise UserError(
                    _('Please set a warehouse on part "%s" before deducting stock.',
                      line.product_id.display_name)
                )
            if not line.product_id:
                raise UserError(_('No product set on the parts line.'))

            source_location = line.warehouse_id.lot_stock_id
            dest_location = self.env.ref('stock.stock_location_customers')

            move_vals = {
                'name': _('%s – %s', line.job_id.name, line.product_id.display_name),
                'product_id': line.product_id.id,
                'product_uom_qty': line.quantity,
                'product_uom': line.product_id.uom_id.id,
                'location_id': source_location.id,
                'location_dest_id': dest_location.id,
                'origin': line.job_id.name,
            }

            move = self.env['stock.move'].create(move_vals)
            move._action_confirm()
            move._action_assign()
            move.quantity = line.quantity
            move.picked = True
            move._action_done()

            line.write({
                'stock_move_id': move.id,
                'is_deducted': True,
            })
