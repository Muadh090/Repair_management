# -*- coding: utf-8 -*-

from odoo import api, fields, models


class RepairPurchaseRequestLine(models.Model):
    _name = 'repair.purchase.request.line'
    _description = 'Repair Purchase Request Line'

    request_id = fields.Many2one(
        comodel_name='repair.purchase.request',
        string='Purchase Request',
        ondelete='cascade',
    )
    product_id = fields.Many2one(
        comodel_name='product.product',
        string='Product',
        required=True,
    )
    description = fields.Char(
        string='Description',
    )
    quantity_requested = fields.Float(
        string='Quantity Requested',
        required=True,
        digits='Product Unit of Measure',
    )
    quantity_approved = fields.Float(
        string='Quantity Approved',
        digits='Product Unit of Measure',
    )
    unit_price_estimated = fields.Float(
        string='Estimated Unit Price',
        digits='Product Price',
    )
    subtotal = fields.Float(
        string='Subtotal',
        compute='_compute_subtotal',
        store=True,
        digits='Product Price',
    )
    current_stock = fields.Float(
        string='Current Stock',
        compute='_compute_current_stock',
        digits='Product Unit of Measure',
    )
    minimum_stock = fields.Float(
        string='Minimum Stock',
        related='product_id.product_tmpl_id.minimum_stock_qty',
    )
    preferred_supplier_id = fields.Many2one(
        comodel_name='res.partner',
        string='Preferred Supplier',
        domain="[('supplier_rank', '>', 0)]",
    )
    notes = fields.Char(
        string='Notes',
    )

    @api.depends('quantity_requested', 'unit_price_estimated')
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.quantity_requested * line.unit_price_estimated

    @api.depends('product_id', 'request_id.warehouse_id')
    def _compute_current_stock(self):
        for line in self:
            if line.product_id and line.request_id.warehouse_id:
                location = line.request_id.warehouse_id.lot_stock_id
                quants = self.env['stock.quant'].search([
                    ('product_id', '=', line.product_id.id),
                    ('location_id', 'child_of', location.id),
                ])
                line.current_stock = sum(quants.mapped('quantity'))
            elif line.product_id:
                line.current_stock = line.product_id.qty_available
            else:
                line.current_stock = 0.0

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.description = self.product_id.display_name
            # Set estimated price from last purchase or standard price
            seller = self.product_id.seller_ids[:1]
            if seller:
                self.unit_price_estimated = seller.price
                self.preferred_supplier_id = seller.partner_id.id
            else:
                self.unit_price_estimated = self.product_id.standard_price
            # Current stock is handled by compute method
