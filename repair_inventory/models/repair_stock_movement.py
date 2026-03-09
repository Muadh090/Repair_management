# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class RepairStockMovement(models.Model):
    _name = 'repair.stock.movement'
    _description = 'Repair Stock Movement'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(
        string='Reference',
        readonly=True,
        copy=False,
        default='New',
    )
    movement_type = fields.Selection(
        selection=[
            ('repair_consume', 'Parts Used in Repair'),
            ('repair_return', 'Parts Returned from Repair'),
            ('branch_transfer', 'Inter-Branch Transfer'),
            ('stock_adjustment', 'Stock Adjustment'),
            ('purchase_receipt', 'Purchase Receipt'),
            ('damaged', 'Damaged/Written Off'),
        ],
        string='Movement Type',
        required=True,
        tracking=True,
    )
    repair_id = fields.Many2one(
        comodel_name='repair.job',
        string='Repair Job',
    )
    product_id = fields.Many2one(
        comodel_name='product.product',
        string='Product',
        required=True,
    )
    product_category = fields.Many2one(
        related='product_id.categ_id',
        string='Product Category',
        store=True,
    )
    quantity = fields.Float(
        string='Quantity',
        required=True,
        digits='Product Unit of Measure',
    )
    unit_of_measure = fields.Many2one(
        comodel_name='uom.uom',
        string='Unit of Measure',
    )
    from_branch_id = fields.Many2one(
        comodel_name='res.branch',
        string='From Branch',
    )
    to_branch_id = fields.Many2one(
        comodel_name='res.branch',
        string='To Branch',
    )
    from_warehouse_id = fields.Many2one(
        comodel_name='stock.warehouse',
        string='From Warehouse',
    )
    to_warehouse_id = fields.Many2one(
        comodel_name='stock.warehouse',
        string='To Warehouse',
    )
    from_location_id = fields.Many2one(
        comodel_name='stock.location',
        string='From Location',
    )
    to_location_id = fields.Many2one(
        comodel_name='stock.location',
        string='To Location',
    )
    stock_move_id = fields.Many2one(
        comodel_name='stock.move',
        string='Stock Move',
        readonly=True,
    )
    stock_picking_id = fields.Many2one(
        comodel_name='stock.picking',
        string='Stock Picking',
        readonly=True,
    )
    unit_cost = fields.Float(
        string='Unit Cost',
        digits='Product Price',
    )
    total_cost = fields.Float(
        string='Total Cost',
        compute='_compute_total_cost',
        store=True,
        digits='Product Price',
    )
    date = fields.Datetime(
        string='Date',
        default=fields.Datetime.now,
        tracking=True,
    )
    done_by = fields.Many2one(
        comodel_name='res.users',
        string='Done By',
        default=lambda self: self.env.uid,
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('confirmed', 'Confirmed'),
            ('done', 'Done'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status',
        default='draft',
        tracking=True,
    )
    reference = fields.Char(
        string='External Reference',
    )
    notes = fields.Text(
        string='Notes',
    )

    @api.depends('quantity', 'unit_cost')
    def _compute_total_cost(self):
        for record in self:
            record.total_cost = record.quantity * record.unit_cost

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'repair.stock.movement'
                ) or 'New'
        return super().create(vals_list)

    def action_confirm(self):
        for record in self:
            if record.state != 'draft':
                raise UserError(_('Only draft movements can be confirmed.'))
            if record.quantity <= 0:
                raise UserError(_('Quantity must be greater than zero.'))
            if record.movement_type in ('repair_consume', 'branch_transfer', 'damaged'):
                if not record.from_location_id:
                    raise UserError(_('Source location is required for this movement type.'))
            if record.movement_type in ('repair_return', 'branch_transfer', 'purchase_receipt'):
                if not record.to_location_id:
                    raise UserError(_('Destination location is required for this movement type.'))
            record.state = 'confirmed'

    def action_done(self):
        for record in self:
            if record.state != 'confirmed':
                raise UserError(_('Only confirmed movements can be completed.'))
            record._process_stock_move()
            record.state = 'done'

    def _process_stock_move(self):
        self.ensure_one()
        move_vals = {
            'name': self.name,
            'product_id': self.product_id.id,
            'product_uom_qty': self.quantity,
            'product_uom': self.unit_of_measure.id or self.product_id.uom_id.id,
            'date': self.date,
        }

        if self.movement_type == 'repair_consume':
            move_vals['location_id'] = self.from_location_id.id
            move_vals['location_dest_id'] = self.env.ref('stock.location_production').id
        elif self.movement_type == 'repair_return':
            move_vals['location_id'] = self.env.ref('stock.location_production').id
            move_vals['location_dest_id'] = self.to_location_id.id
        elif self.movement_type == 'branch_transfer':
            move_vals['location_id'] = self.from_location_id.id
            move_vals['location_dest_id'] = self.to_location_id.id
        elif self.movement_type == 'stock_adjustment':
            if self.from_location_id and self.to_location_id:
                move_vals['location_id'] = self.from_location_id.id
                move_vals['location_dest_id'] = self.to_location_id.id
            elif self.to_location_id:
                move_vals['location_id'] = self.env.ref('stock.location_inventory').id
                move_vals['location_dest_id'] = self.to_location_id.id
            else:
                move_vals['location_id'] = self.from_location_id.id
                move_vals['location_dest_id'] = self.env.ref('stock.location_inventory').id
        elif self.movement_type == 'purchase_receipt':
            move_vals['location_id'] = self.env.ref('stock.stock_location_suppliers').id
            move_vals['location_dest_id'] = self.to_location_id.id
        elif self.movement_type == 'damaged':
            move_vals['location_id'] = self.from_location_id.id
            move_vals['location_dest_id'] = self.env.ref('stock.stock_location_scrapped').id

        stock_move = self.env['stock.move'].create(move_vals)
        stock_move._action_confirm()
        stock_move._action_assign()
        stock_move._action_done()
        self.stock_move_id = stock_move.id

    def action_cancel(self):
        for record in self:
            if record.state == 'done' and record.stock_move_id:
                reverse_move = self.env['stock.move'].create({
                    'name': _('Reversal of %s', record.name),
                    'product_id': record.product_id.id,
                    'product_uom_qty': record.quantity,
                    'product_uom': record.unit_of_measure.id or record.product_id.uom_id.id,
                    'location_id': record.stock_move_id.location_dest_id.id,
                    'location_dest_id': record.stock_move_id.location_id.id,
                    'date': fields.Datetime.now(),
                })
                reverse_move._action_confirm()
                reverse_move._action_assign()
                reverse_move._action_done()
            if record.state in ('draft', 'confirmed', 'done'):
                record.state = 'cancelled'
