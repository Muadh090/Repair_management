# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from datetime import timedelta


class RepairJob(models.Model):
    _name = 'repair.job'
    _description = 'Repair Job'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name desc'

    # =====================================================================
    # IDENTIFICATION
    # =====================================================================
    name = fields.Char(
        string='Reference',
        readonly=True,
        copy=False,
        default='New',
    )
    state = fields.Selection(
        selection=[
            ('received', 'Received'),
            ('diagnosing', 'Diagnosing'),
            ('repairing', 'Repairing'),
            ('waiting_parts', 'Waiting for Parts'),
            ('ready', 'Ready'),
            ('collected', 'Collected'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status',
        default='received',
        tracking=True,
        required=True,
    )
    priority = fields.Selection(
        selection=[
            ('normal', 'Normal'),
            ('urgent', 'Urgent'),
            ('emergency', 'Emergency'),
        ],
        string='Priority',
        default='normal',
    )
    active = fields.Boolean(default=True)

    # =====================================================================
    # CUSTOMER INFO
    # =====================================================================
    customer_id = fields.Many2one(
        comodel_name='res.partner',
        string='Customer',
        required=True,
        tracking=True,
    )
    customer_phone = fields.Char(
        string='Phone',
        related='customer_id.phone',
        readonly=True,
    )
    customer_email = fields.Char(
        string='Email',
        related='customer_id.email',
        readonly=True,
    )

    # =====================================================================
    # DEVICE INFO
    # =====================================================================
    device_type = fields.Selection(
        selection=[
            ('phone', 'Phone'),
            ('laptop', 'Laptop'),
            ('tablet', 'Tablet'),
            ('tv', 'TV'),
            ('generator', 'Generator'),
            ('printer', 'Printer'),
            ('console', 'Console'),
            ('other', 'Other'),
        ],
        string='Device Type',
        required=True,
    )
    device_brand = fields.Char(string='Brand', required=True)
    device_model = fields.Char(string='Model')
    device_serial = fields.Char(string='Serial Number')
    device_color = fields.Char(string='Color')
    device_condition = fields.Text(string='Condition on Arrival')

    # =====================================================================
    # ASSIGNMENT
    # =====================================================================
    branch_id = fields.Many2one(
        comodel_name='res.branch',
        string='Branch',
    )
    technician_id = fields.Many2one(
        comodel_name='hr.employee',
        string='Lead Technician',
        tracking=True,
    )
    technician_ids = fields.Many2many(
        comodel_name='hr.employee',
        relation='repair_job_technician_rel',
        column1='job_id',
        column2='employee_id',
        string='Technicians',
    )

    # =====================================================================
    # DIAGNOSIS & REPAIR
    # =====================================================================
    fault_description = fields.Text(
        string='Fault Description',
        required=True,
        help='Customer complaint or reported fault.',
    )
    diagnosis_notes = fields.Text(
        string='Diagnosis Notes',
        help='Internal diagnosis notes by technician.',
    )
    technician_notes = fields.Text(string='Technician Notes')
    repair_action_taken = fields.Text(string='Repair Action Taken')

    # =====================================================================
    # DATES
    # =====================================================================
    date_received = fields.Datetime(
        string='Date Received',
        default=fields.Datetime.now,
    )
    date_estimated_completion = fields.Date(
        string='Estimated Completion',
    )
    date_completed = fields.Datetime(string='Date Completed')
    date_collected = fields.Datetime(string='Date Collected')

    # =====================================================================
    # COSTS
    # =====================================================================
    diagnosis_fee = fields.Float(string='Diagnosis Fee', default=0.0)
    labour_cost = fields.Float(string='Labour Cost', default=0.0)
    parts_cost = fields.Float(
        string='Parts Cost',
        compute='_compute_parts_cost',
        store=True,
    )
    discount_amount = fields.Float(string='Discount', default=0.0)
    total_cost = fields.Float(
        string='Total Cost',
        compute='_compute_total',
        store=True,
    )
    amount_paid = fields.Float(string='Amount Paid', default=0.0)
    balance_due = fields.Float(
        string='Balance Due',
        compute='_compute_balance_due',
        store=True,
    )

    # =====================================================================
    # WARRANTY
    # =====================================================================
    warranty_period = fields.Integer(
        string='Warranty Period (Days)',
        default=0,
    )
    warranty_expiry = fields.Date(
        string='Warranty Expiry',
        compute='_compute_warranty_expiry',
        store=True,
    )
    is_warranty_job = fields.Boolean(
        string='Warranty Job',
        default=False,
    )
    original_job_id = fields.Many2one(
        comodel_name='repair.job',
        string='Original Job',
        help='Reference to the original repair job if this is a warranty return.',
    )

    # =====================================================================
    # RELATIONS
    # =====================================================================
    parts_line_ids = fields.One2many(
        comodel_name='repair.parts.line',
        inverse_name='job_id',
        string='Parts Lines',
    )
    invoice_id = fields.Many2one(
        comodel_name='account.move',
        string='Invoice',
        copy=False,
    )
    invoice_state = fields.Selection(
        string='Invoice Status',
        related='invoice_id.payment_state',
        readonly=True,
    )

    # =====================================================================
    # TRACKING
    # =====================================================================
    is_comeback = fields.Boolean(
        string='Is Comeback',
        help='Returned for the same fault.',
        default=False,
    )
    comeback_count = fields.Integer(
        string='Comeback Count',
        compute='_compute_comeback_count',
    )
    image_ids = fields.One2many(
        comodel_name='ir.attachment',
        inverse_name='res_id',
        string='Device Photos',
        domain=[('res_model', '=', 'repair.job')],
    )

    # -----------------------------------------------------------------
    # CRUD
    # -----------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'repair.job'
                ) or 'New'
        return super().create(vals_list)

    # -----------------------------------------------------------------
    # COMPUTE METHODS
    # -----------------------------------------------------------------
    @api.depends('parts_line_ids.subtotal')
    def _compute_parts_cost(self):
        for job in self:
            job.parts_cost = sum(job.parts_line_ids.mapped('subtotal'))

    @api.depends('diagnosis_fee', 'labour_cost', 'parts_cost', 'discount_amount')
    def _compute_total(self):
        for job in self:
            job.total_cost = (
                job.diagnosis_fee
                + job.labour_cost
                + job.parts_cost
                - job.discount_amount
            )

    @api.depends('total_cost', 'amount_paid')
    def _compute_balance_due(self):
        for job in self:
            job.balance_due = job.total_cost - job.amount_paid

    @api.depends('date_completed', 'warranty_period')
    def _compute_warranty_expiry(self):
        for job in self:
            if job.date_completed and job.warranty_period > 0:
                job.warranty_expiry = (
                    job.date_completed.date() + timedelta(days=job.warranty_period)
                )
            else:
                job.warranty_expiry = False

    def _compute_comeback_count(self):
        for job in self:
            job.comeback_count = self.search_count([
                ('original_job_id', '=', job.id),
                ('is_comeback', '=', True),
            ])

    # -----------------------------------------------------------------
    # ACTION METHODS
    # -----------------------------------------------------------------
    def action_start_diagnosis(self):
        for job in self:
            if job.state != 'received':
                raise UserError(
                    _('Only jobs in "Received" state can move to diagnosing.')
                )
            job.state = 'diagnosing'

    def action_start_repair(self):
        for job in self:
            if job.state not in ('diagnosing', 'waiting_parts'):
                raise UserError(
                    _('Only jobs in "Diagnosing" or "Waiting for Parts" '
                      'state can move to repairing.')
                )
            job.state = 'repairing'

    def action_wait_parts(self):
        for job in self:
            if job.state not in ('diagnosing', 'repairing'):
                raise UserError(
                    _('Only jobs in "Diagnosing" or "Repairing" '
                      'state can move to waiting for parts.')
                )
            job.state = 'waiting_parts'

    def action_ready(self):
        for job in self:
            if job.state != 'repairing':
                raise UserError(
                    _('Only jobs in "Repairing" state can be marked as ready.')
                )
            job.write({
                'state': 'ready',
                'date_completed': fields.Datetime.now(),
            })

    def action_collect(self):
        for job in self:
            if job.state != 'ready':
                raise UserError(
                    _('Only jobs in "Ready" state can be collected.')
                )
            job.write({
                'state': 'collected',
                'date_collected': fields.Datetime.now(),
            })

    def action_cancel(self):
        for job in self:
            if job.state == 'collected':
                raise UserError(
                    _('A collected job cannot be cancelled.')
                )
            job.state = 'cancelled'

    def action_create_invoice(self):
        self.ensure_one()
        if self.invoice_id:
            raise UserError(_('An invoice already exists for this job.'))

        invoice_lines = []

        # Diagnosis fee
        if self.diagnosis_fee:
            invoice_lines.append((0, 0, {
                'name': _('Diagnosis Fee – %s', self.name),
                'quantity': 1,
                'price_unit': self.diagnosis_fee,
            }))

        # Labour cost
        if self.labour_cost:
            invoice_lines.append((0, 0, {
                'name': _('Labour Cost – %s', self.name),
                'quantity': 1,
                'price_unit': self.labour_cost,
            }))

        # Parts lines
        for line in self.parts_line_ids:
            invoice_lines.append((0, 0, {
                'name': line.product_id.name or _('Repair Part'),
                'product_id': line.product_id.id,
                'quantity': line.quantity,
                'price_unit': line.unit_price,
            }))

        if not invoice_lines:
            raise UserError(_('Nothing to invoice. Add fees or parts first.'))

        move_vals = {
            'move_type': 'out_invoice',
            'partner_id': self.customer_id.id,
            'invoice_origin': self.name,
            'invoice_line_ids': invoice_lines,
        }

        invoice = self.env['account.move'].create(move_vals)
        self.invoice_id = invoice.id

        # Apply discount as a negative line if present
        if self.discount_amount:
            self.env['account.move.line'].create({
                'move_id': invoice.id,
                'name': _('Discount – %s', self.name),
                'quantity': 1,
                'price_unit': -self.discount_amount,
            })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': invoice.id,
            'view_mode': 'form',
            'target': 'current',
        }
