# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class RepairStockAdjustmentWizard(models.TransientModel):
    _name = 'repair.stock.adjustment.wizard'
    _description = 'Stock Adjustment Wizard'

    warehouse_id = fields.Many2one(
        comodel_name='stock.warehouse',
        string='Warehouse',
        required=True,
    )
    branch_id = fields.Many2one(
        comodel_name='res.branch',
        string='Branch',
    )
    adjustment_date = fields.Date(
        string='Adjustment Date',
        default=fields.Date.context_today,
    )
    reason = fields.Selection(
        selection=[
            ('count', 'Physical Stock Count'),
            ('damaged', 'Damaged Parts'),
            ('expired', 'Expired Parts'),
            ('found', 'Found Extra Stock'),
            ('other', 'Other'),
        ],
        string='Reason',
        required=True,
    )
    notes = fields.Text(
        string='Notes',
    )
    line_ids = fields.One2many(
        comodel_name='repair.stock.adjustment.line',
        inverse_name='wizard_id',
        string='Adjustment Lines',
    )
    adjusted_by = fields.Many2one(
        comodel_name='res.users',
        string='Adjusted By',
        default=lambda self: self.env.uid,
    )

    def action_apply_adjustment(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_('Please add at least one adjustment line.'))

        reason_labels = dict(self._fields['reason'].selection)
        reason_label = reason_labels.get(self.reason, self.reason)

        for line in self.line_ids:
            if line.difference_qty == 0:
                continue

            location = self.warehouse_id.lot_stock_id
            inventory_location = self.env.ref('stock.location_inventory')

            if line.difference_qty > 0:
                # Stock increase — move from inventory adjustment location into warehouse
                src_location = inventory_location
                dest_location = location
                movement_type = 'stock_adjustment'
            else:
                # Stock decrease — move from warehouse to inventory adjustment location
                src_location = location
                dest_location = inventory_location
                movement_type = 'damaged' if self.reason == 'damaged' else 'stock_adjustment'

            abs_qty = abs(line.difference_qty)

            # Create stock move
            stock_move = self.env['stock.move'].create({
                'name': _('Adjustment: %s - %s', reason_label, line.product_id.display_name),
                'product_id': line.product_id.id,
                'product_uom_qty': abs_qty,
                'product_uom': line.product_id.uom_id.id,
                'location_id': src_location.id,
                'location_dest_id': dest_location.id,
                'date': self.adjustment_date,
            })
            stock_move._action_confirm()
            stock_move._action_assign()
            stock_move.quantity = abs_qty
            stock_move._action_done()

            # Create repair stock movement record
            self.env['repair.stock.movement'].create({
                'movement_type': movement_type,
                'product_id': line.product_id.id,
                'quantity': abs_qty,
                'unit_of_measure': line.product_id.uom_id.id,
                'from_warehouse_id': self.warehouse_id.id if line.difference_qty < 0 else False,
                'to_warehouse_id': self.warehouse_id.id if line.difference_qty > 0 else False,
                'from_location_id': src_location.id,
                'to_location_id': dest_location.id,
                'stock_move_id': stock_move.id,
                'unit_cost': line.unit_cost,
                'date': self.adjustment_date,
                'done_by': self.env.uid,
                'state': 'done',
                'reference': _('Adjustment: %s', reason_label),
                'notes': self.notes,
            })

        return {'type': 'ir.actions.act_window_close'}


class RepairStockAdjustmentLine(models.TransientModel):
    _name = 'repair.stock.adjustment.line'
    _description = 'Stock Adjustment Line'

    wizard_id = fields.Many2one(
        comodel_name='repair.stock.adjustment.wizard',
        string='Adjustment Wizard',
    )
    product_id = fields.Many2one(
        comodel_name='product.product',
        string='Product',
        required=True,
    )
    current_qty = fields.Float(
        string='System Qty',
        compute='_compute_current_qty',
        digits='Product Unit of Measure',
    )
    counted_qty = fields.Float(
        string='Counted Qty',
        required=True,
        digits='Product Unit of Measure',
    )
    difference_qty = fields.Float(
        string='Difference',
        compute='_compute_difference',
        store=True,
        digits='Product Unit of Measure',
    )
    unit_cost = fields.Float(
        string='Unit Cost',
        digits='Product Price',
    )
    adjustment_value = fields.Float(
        string='Adjustment Value',
        compute='_compute_adjustment_value',
        store=True,
        digits='Product Price',
    )

    @api.depends('product_id', 'wizard_id.warehouse_id')
    def _compute_current_qty(self):
        for line in self:
            if line.product_id and line.wizard_id.warehouse_id:
                location = line.wizard_id.warehouse_id.lot_stock_id
                quants = self.env['stock.quant'].search([
                    ('product_id', '=', line.product_id.id),
                    ('location_id', 'child_of', location.id),
                ])
                line.current_qty = sum(quants.mapped('quantity'))
            else:
                line.current_qty = 0.0

    @api.depends('counted_qty', 'current_qty')
    def _compute_difference(self):
        for line in self:
            line.difference_qty = line.counted_qty - line.current_qty

    @api.depends('difference_qty', 'unit_cost')
    def _compute_adjustment_value(self):
        for line in self:
            line.adjustment_value = line.difference_qty * line.unit_cost

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.unit_cost = self.product_id.standard_price
