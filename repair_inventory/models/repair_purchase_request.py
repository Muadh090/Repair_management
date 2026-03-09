# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class RepairPurchaseRequest(models.Model):
    _name = 'repair.purchase.request'
    _description = 'Repair Purchase Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'request_date desc, id desc'

    name = fields.Char(
        string='Reference',
        readonly=True,
        copy=False,
        default='New',
    )
    branch_id = fields.Many2one(
        comodel_name='res.branch',
        string='Branch',
        required=True,
    )
    warehouse_id = fields.Many2one(
        comodel_name='stock.warehouse',
        string='Warehouse',
    )
    requested_by = fields.Many2one(
        comodel_name='hr.employee',
        string='Requested By',
        required=True,
    )
    approved_by = fields.Many2one(
        comodel_name='hr.employee',
        string='Approved By',
        readonly=True,
    )
    request_date = fields.Date(
        string='Request Date',
        default=fields.Date.context_today,
    )
    required_date = fields.Date(
        string='Required Date',
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('submitted', 'Submitted'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
            ('ordered', 'Ordered'),
            ('received', 'Received'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status',
        default='draft',
        tracking=True,
    )
    priority = fields.Selection(
        selection=[
            ('normal', 'Normal'),
            ('urgent', 'Urgent'),
            ('emergency', 'Emergency'),
        ],
        string='Priority',
        default='normal',
        tracking=True,
    )
    repair_id = fields.Many2one(
        comodel_name='repair.job',
        string='Repair Job',
    )
    stock_alert_id = fields.Many2one(
        comodel_name='repair.stock.alert',
        string='Stock Alert',
    )
    line_ids = fields.One2many(
        comodel_name='repair.purchase.request.line',
        inverse_name='request_id',
        string='Request Lines',
    )
    total_estimated_cost = fields.Float(
        string='Total Estimated Cost',
        compute='_compute_total_estimated_cost',
        store=True,
        digits='Product Price',
    )
    purchase_order_id = fields.Many2one(
        comodel_name='purchase.order',
        string='Purchase Order',
        readonly=True,
    )
    rejection_reason = fields.Text(
        string='Rejection Reason',
    )
    notes = fields.Text(
        string='Notes',
    )

    @api.depends('line_ids.subtotal')
    def _compute_total_estimated_cost(self):
        for record in self:
            record.total_estimated_cost = sum(record.line_ids.mapped('subtotal'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'repair.purchase.request'
                ) or 'New'
        return super().create(vals_list)

    def action_submit(self):
        for record in self:
            if record.state != 'draft':
                raise UserError(_('Only draft requests can be submitted.'))
            if not record.line_ids:
                raise UserError(_('Cannot submit a request with no lines.'))
            record.state = 'submitted'

    def action_approve(self):
        for record in self:
            if record.state != 'submitted':
                raise UserError(_('Only submitted requests can be approved.'))
            employee = self.env['hr.employee'].search(
                [('user_id', '=', self.env.uid)], limit=1
            )
            record.write({
                'state': 'approved',
                'approved_by': employee.id if employee else False,
            })
            # Approve quantities: default to requested if not set
            for line in record.line_ids:
                if not line.quantity_approved:
                    line.quantity_approved = line.quantity_requested
            # Notify branch manager
            if record.branch_id and hasattr(record.branch_id, 'manager_id') and record.branch_id.manager_id:
                manager_user = record.branch_id.manager_id
                if hasattr(manager_user, 'partner_id'):
                    record.message_post(
                        body=_('Purchase request %s has been approved.', record.name),
                        partner_ids=[manager_user.partner_id.id],
                        message_type='notification',
                        subtype_xmlid='mail.mt_note',
                    )

    def action_reject(self):
        for record in self:
            if record.state != 'submitted':
                raise UserError(_('Only submitted requests can be rejected.'))
            if not record.rejection_reason:
                raise UserError(_('Please provide a rejection reason.'))
            record.state = 'rejected'

    def action_create_purchase_order(self):
        self.ensure_one()
        if self.state != 'approved':
            raise UserError(_('Only approved requests can generate purchase orders.'))
        if self.purchase_order_id:
            raise UserError(_('A purchase order already exists for this request.'))

        # Group lines by supplier
        supplier_lines = {}
        for line in self.line_ids:
            if line.quantity_approved <= 0:
                continue
            supplier = line.preferred_supplier_id
            if not supplier:
                # Fallback to first supplier on product
                seller = line.product_id.seller_ids[:1]
                supplier = seller.partner_id if seller else False
            if not supplier:
                raise UserError(_(
                    'No supplier found for product "%s". '
                    'Please set a preferred supplier on the request line.',
                    line.product_id.display_name,
                ))
            if supplier.id not in supplier_lines:
                supplier_lines[supplier.id] = {
                    'supplier': supplier,
                    'lines': [],
                }
            supplier_lines[supplier.id]['lines'].append(line)

        if not supplier_lines:
            raise UserError(_('No approved lines with quantity to order.'))

        # Create PO for the first (or only) supplier group
        # If multiple suppliers, create one PO for the primary supplier
        first_group = list(supplier_lines.values())[0]
        supplier = first_group['supplier']

        po_vals = {
            'partner_id': supplier.id,
            'date_order': fields.Datetime.now(),
            'origin': self.name,
        }
        if self.warehouse_id and self.warehouse_id.lot_stock_id:
            po_vals['picking_type_id'] = self.env['stock.picking.type'].search([
                ('warehouse_id', '=', self.warehouse_id.id),
                ('code', '=', 'incoming'),
            ], limit=1).id

        purchase_order = self.env['purchase.order'].create(po_vals)

        for group in supplier_lines.values():
            for line in group['lines']:
                self.env['purchase.order.line'].create({
                    'order_id': purchase_order.id,
                    'product_id': line.product_id.id,
                    'name': line.description or line.product_id.display_name,
                    'product_qty': line.quantity_approved,
                    'price_unit': line.unit_price_estimated,
                    'product_uom': line.product_id.uom_po_id.id or line.product_id.uom_id.id,
                    'date_planned': self.required_date or fields.Date.context_today(self),
                })

        self.write({
            'purchase_order_id': purchase_order.id,
            'state': 'ordered',
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.order',
            'res_id': purchase_order.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_cancel(self):
        for record in self:
            if record.state in ('received',):
                raise UserError(_('Received requests cannot be cancelled.'))
            record.state = 'cancelled'
