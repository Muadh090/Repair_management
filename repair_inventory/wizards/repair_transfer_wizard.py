# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class RepairTransferWizard(models.TransientModel):
    _name = 'repair.transfer.wizard'
    _description = 'Inter-Branch Transfer Wizard'

    from_branch_id = fields.Many2one(
        comodel_name='res.branch',
        string='From Branch',
        required=True,
    )
    from_warehouse_id = fields.Many2one(
        comodel_name='stock.warehouse',
        string='From Warehouse',
        required=True,
        domain="[('branch_id', '=', from_branch_id)]",
    )
    to_branch_id = fields.Many2one(
        comodel_name='res.branch',
        string='To Branch',
        required=True,
    )
    to_warehouse_id = fields.Many2one(
        comodel_name='stock.warehouse',
        string='To Warehouse',
        required=True,
        domain="[('branch_id', '=', to_branch_id)]",
    )
    transfer_date = fields.Date(
        string='Transfer Date',
        default=fields.Date.context_today,
    )
    reference = fields.Char(
        string='Reference',
    )
    reason = fields.Text(
        string='Reason',
    )
    line_ids = fields.One2many(
        comodel_name='repair.transfer.wizard.line',
        inverse_name='wizard_id',
        string='Transfer Lines',
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('confirmed', 'Confirmed'),
        ],
        string='Status',
        default='draft',
    )
    total_lines = fields.Integer(
        string='Total Lines',
        compute='_compute_total_lines',
    )
    requested_by = fields.Many2one(
        comodel_name='res.users',
        string='Requested By',
        default=lambda self: self.env.uid,
    )

    @api.depends('line_ids')
    def _compute_total_lines(self):
        for record in self:
            record.total_lines = len(record.line_ids)

    @api.onchange('from_branch_id')
    def _onchange_from_branch_id(self):
        self.from_warehouse_id = False

    @api.onchange('to_branch_id')
    def _onchange_to_branch_id(self):
        self.to_warehouse_id = False

    def action_confirm_transfer(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_('Please add at least one product line.'))
        if self.from_warehouse_id == self.to_warehouse_id:
            raise UserError(_('Source and destination warehouse cannot be the same.'))

        # Validate quantities
        for line in self.line_ids:
            if line.quantity <= 0:
                raise UserError(_(
                    'Quantity must be greater than zero for product "%s".',
                    line.product_id.display_name,
                ))
            if line.quantity > line.available_qty:
                raise UserError(_(
                    'Insufficient stock for "%s". Available: %s, Requested: %s.',
                    line.product_id.display_name,
                    line.available_qty,
                    line.quantity,
                ))

        # Find internal transfer picking type
        picking_type = self.env['stock.picking.type'].search([
            ('warehouse_id', '=', self.from_warehouse_id.id),
            ('code', '=', 'internal'),
        ], limit=1)
        if not picking_type:
            raise UserError(_(
                'No internal transfer operation type found for warehouse "%s".',
                self.from_warehouse_id.display_name,
            ))

        # Create stock picking
        picking_vals = {
            'picking_type_id': picking_type.id,
            'location_id': self.from_warehouse_id.lot_stock_id.id,
            'location_dest_id': self.to_warehouse_id.lot_stock_id.id,
            'origin': self.reference or 'Branch Transfer',
            'scheduled_date': self.transfer_date,
        }
        picking = self.env['stock.picking'].create(picking_vals)

        # Create stock moves and repair.stock.movement records
        for line in self.line_ids:
            move_vals = {
                'name': line.product_id.display_name,
                'product_id': line.product_id.id,
                'product_uom_qty': line.quantity,
                'product_uom': line.product_id.uom_id.id,
                'picking_id': picking.id,
                'location_id': self.from_warehouse_id.lot_stock_id.id,
                'location_dest_id': self.to_warehouse_id.lot_stock_id.id,
            }
            stock_move = self.env['stock.move'].create(move_vals)

            # Create repair stock movement record
            self.env['repair.stock.movement'].create({
                'movement_type': 'branch_transfer',
                'product_id': line.product_id.id,
                'quantity': line.quantity,
                'unit_of_measure': line.product_id.uom_id.id,
                'from_branch_id': self.from_branch_id.id,
                'to_branch_id': self.to_branch_id.id,
                'from_warehouse_id': self.from_warehouse_id.id,
                'to_warehouse_id': self.to_warehouse_id.id,
                'from_location_id': self.from_warehouse_id.lot_stock_id.id,
                'to_location_id': self.to_warehouse_id.lot_stock_id.id,
                'stock_move_id': stock_move.id,
                'stock_picking_id': picking.id,
                'unit_cost': line.unit_cost,
                'date': self.transfer_date,
                'done_by': self.env.uid,
                'state': 'confirmed',
                'reference': self.reference,
                'notes': self.reason,
            })

        # Confirm and validate the picking
        picking.action_confirm()
        picking.action_assign()
        if picking.state == 'assigned':
            for move_line in picking.move_ids:
                move_line.quantity = move_line.product_uom_qty
            picking.button_validate()

        self.state = 'confirmed'
        return {'type': 'ir.actions.act_window_close'}


class RepairTransferWizardLine(models.TransientModel):
    _name = 'repair.transfer.wizard.line'
    _description = 'Transfer Wizard Line'

    wizard_id = fields.Many2one(
        comodel_name='repair.transfer.wizard',
        string='Transfer Wizard',
    )
    product_id = fields.Many2one(
        comodel_name='product.product',
        string='Product',
        required=True,
    )
    available_qty = fields.Float(
        string='Available Qty',
        compute='_compute_available_qty',
        digits='Product Unit of Measure',
    )
    quantity = fields.Float(
        string='Quantity to Transfer',
        required=True,
        digits='Product Unit of Measure',
    )
    unit_cost = fields.Float(
        string='Unit Cost',
        digits='Product Price',
    )
    notes = fields.Char(
        string='Notes',
    )

    @api.depends('product_id', 'wizard_id.from_warehouse_id')
    def _compute_available_qty(self):
        for line in self:
            if line.product_id and line.wizard_id.from_warehouse_id:
                location = line.wizard_id.from_warehouse_id.lot_stock_id
                quants = self.env['stock.quant'].search([
                    ('product_id', '=', line.product_id.id),
                    ('location_id', 'child_of', location.id),
                ])
                line.available_qty = sum(quants.mapped('quantity'))
            else:
                line.available_qty = 0.0

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.unit_cost = self.product_id.standard_price
