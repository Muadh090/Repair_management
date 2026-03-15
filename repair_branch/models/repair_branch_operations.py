# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError


class RepairBranchDayClose(models.Model):
    _name = 'repair.branch.day.close'
    _description = 'Repair Branch Day Close'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

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
        tracking=True,
    )
    date = fields.Date(
        string='Date',
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    closed_by = fields.Many2one(
        comodel_name='hr.employee',
        string='Closed By',
        required=True,
        default=lambda self: self.env.user.employee_id,
    )
    approved_by = fields.Many2one(
        comodel_name='hr.employee',
        string='Approved By',
        readonly=True,
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('submitted', 'Submitted'),
            ('approved', 'Approved'),
        ],
        string='Status',
        default='draft',
        tracking=True,
    )

    total_jobs_received = fields.Integer(string='Total Jobs Received')
    total_jobs_completed = fields.Integer(string='Total Jobs Completed')
    total_jobs_pending = fields.Integer(string='Total Jobs Pending')
    total_jobs_collected = fields.Integer(string='Total Jobs Collected')
    total_jobs_cancelled = fields.Integer(string='Total Jobs Cancelled')

    total_invoiced = fields.Float(string='Total Invoiced')
    total_cash_collected = fields.Float(string='Total Cash Collected')
    total_pos_collected = fields.Float(string='Total POS Collected')
    total_transfer_collected = fields.Float(string='Total Transfer Collected')
    total_grand_collected = fields.Float(
        string='Total Grand Collected',
        compute='_compute_total_grand_collected',
        store=True,
    )
    total_outstanding = fields.Float(string='Total Outstanding')
    total_expenses = fields.Float(string='Total Expenses')
    net_revenue = fields.Float(
        string='Net Revenue',
        compute='_compute_net_revenue',
        store=True,
    )

    opening_cash = fields.Float(string='Opening Cash')
    cash_in = fields.Float(
        string='Cash In',
        compute='_compute_cash_in_out',
        store=True,
    )
    cash_out = fields.Float(
        string='Cash Out',
        compute='_compute_cash_in_out',
        store=True,
    )
    expected_closing_cash = fields.Float(
        string='Expected Closing Cash',
        compute='_compute_cash_difference',
        store=True,
    )
    actual_closing_cash = fields.Float(string='Actual Closing Cash')
    cash_difference = fields.Float(
        string='Cash Difference',
        compute='_compute_cash_difference',
        store=True,
    )
    difference_reason = fields.Text(string='Difference Reason')

    parts_used_count = fields.Integer(
        string='Parts Used Count',
        compute='_compute_stock_summary',
        store=True,
    )
    parts_value_used = fields.Float(
        string='Parts Value Used',
        compute='_compute_stock_summary',
        store=True,
    )
    low_stock_items = fields.Integer(
        string='Low Stock Items',
        compute='_compute_stock_summary',
        store=True,
    )

    operations_notes = fields.Text(string='Operations Notes')
    issues_reported = fields.Text(string='Issues Reported')
    next_day_reminders = fields.Text(string='Next Day Reminders')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('repair.branch.day.close') or 'New'
        return super().create(vals_list)

    @api.depends('total_cash_collected', 'total_pos_collected', 'total_transfer_collected')
    def _compute_total_grand_collected(self):
        for rec in self:
            rec.total_grand_collected = (
                rec.total_cash_collected + rec.total_pos_collected + rec.total_transfer_collected
            )

    @api.depends('total_grand_collected', 'total_expenses')
    def _compute_net_revenue(self):
        for rec in self:
            rec.net_revenue = rec.total_grand_collected - rec.total_expenses

    @api.depends('branch_id', 'date')
    def _compute_cash_in_out(self):
        PettyCash = self.env['repair.petty.cash']
        for rec in self:
            rec.cash_in = 0.0
            rec.cash_out = 0.0
            if not rec.branch_id or not rec.date:
                continue

            start_dt = fields.Datetime.to_datetime('%s 00:00:00' % rec.date)
            end_dt = fields.Datetime.to_datetime('%s 23:59:59' % rec.date)

            in_lines = PettyCash.search_read(
                [
                    ('branch_id', '=', rec.branch_id.id),
                    ('state', '=', 'posted'),
                    ('date', '>=', start_dt),
                    ('date', '<=', end_dt),
                    ('transaction_type', 'in', ('top_up', 'collection', 'adjustment')),
                ],
                ['amount'],
            )
            out_lines = PettyCash.search_read(
                [
                    ('branch_id', '=', rec.branch_id.id),
                    ('state', '=', 'posted'),
                    ('date', '>=', start_dt),
                    ('date', '<=', end_dt),
                    ('transaction_type', 'in', ('expense', 'transfer_out')),
                ],
                ['amount'],
            )

            rec.cash_in = sum(x.get('amount', 0.0) for x in in_lines)
            rec.cash_out = sum(x.get('amount', 0.0) for x in out_lines)

    @api.depends('opening_cash', 'cash_in', 'cash_out', 'actual_closing_cash')
    def _compute_cash_difference(self):
        for rec in self:
            rec.expected_closing_cash = rec.opening_cash + rec.cash_in - rec.cash_out
            rec.cash_difference = rec.actual_closing_cash - rec.expected_closing_cash

    @api.depends('branch_id', 'date')
    def _compute_stock_summary(self):
        StockMovement = self.env['repair.stock.movement']
        StockAlert = self.env['repair.stock.alert']

        for rec in self:
            rec.parts_used_count = 0
            rec.parts_value_used = 0.0
            rec.low_stock_items = 0

            if not rec.branch_id or not rec.date:
                continue

            start_dt = fields.Datetime.to_datetime('%s 00:00:00' % rec.date)
            end_dt = fields.Datetime.to_datetime('%s 23:59:59' % rec.date)

            used_moves = StockMovement.search([
                ('branch_id', '=', rec.branch_id.id),
                ('movement_type', '=', 'repair_consume'),
                ('state', 'in', ('confirmed', 'done')),
                ('date', '>=', start_dt),
                ('date', '<=', end_dt),
            ])

            rec.parts_used_count = len(used_moves)
            rec.parts_value_used = sum(used_moves.mapped('total_cost'))

            rec.low_stock_items = StockAlert.search_count([
                ('branch_id', '=', rec.branch_id.id),
                ('state', 'in', ('active', 'acknowledged')),
                ('alert_type', 'in', ('low_stock', 'critical', 'out_of_stock')),
            ])

    def _compute_all_summaries(self):
        RepairJob = self.env['repair.job']
        RepairInvoice = self.env['repair.job']
        RepairPayment = self.env['repair.payment']
        PettyCash = self.env['repair.petty.cash']

        for rec in self:
            if not rec.branch_id or not rec.date:
                continue

            start_dt = fields.Datetime.to_datetime('%s 00:00:00' % rec.date)
            end_dt = fields.Datetime.to_datetime('%s 23:59:59' % rec.date)

            jobs_domain = [
                ('branch_id', '=', rec.branch_id.id),
                ('date_received', '>=', start_dt),
                ('date_received', '<=', end_dt),
            ]

            rec.total_jobs_received = RepairJob.search_count(jobs_domain)
            rec.total_jobs_completed = RepairJob.search_count(jobs_domain + [('state', '=', 'ready')])
            rec.total_jobs_pending = RepairJob.search_count(jobs_domain + [('state', 'in', ('diagnosing', 'repairing', 'waiting_parts'))])
            rec.total_jobs_collected = RepairJob.search_count(jobs_domain + [('state', '=', 'collected')])
            rec.total_jobs_cancelled = RepairJob.search_count(jobs_domain + [('state', '=', 'cancelled')])

            invoice_jobs = RepairInvoice.search([
                ('branch_id', '=', rec.branch_id.id),
                ('date_received', '>=', start_dt),
                ('date_received', '<=', end_dt),
                ('invoice_id', '!=', False),
            ])
            rec.total_invoiced = sum(invoice_jobs.mapped('invoice_amount_total'))
            rec.total_outstanding = sum(invoice_jobs.mapped('balance_due'))

            payments = RepairPayment.search([
                ('branch_id', '=', rec.branch_id.id),
                ('state', '=', 'confirmed'),
                ('payment_date', '>=', rec.date),
                ('payment_date', '<=', rec.date),
            ])
            rec.total_cash_collected = sum(payments.filtered(lambda p: p.payment_method == 'cash').mapped('amount'))
            rec.total_pos_collected = sum(payments.filtered(lambda p: p.payment_method in ('card', 'pos')).mapped('amount'))
            rec.total_transfer_collected = sum(payments.filtered(lambda p: p.payment_method in ('bank_transfer', 'transfer')).mapped('amount'))

            expenses = PettyCash.search_read(
                [
                    ('branch_id', '=', rec.branch_id.id),
                    ('state', '=', 'posted'),
                    ('transaction_type', '=', 'expense'),
                    ('date', '>=', start_dt),
                    ('date', '<=', end_dt),
                ],
                ['amount'],
            )
            rec.total_expenses = sum(x.get('amount', 0.0) for x in expenses)

            rec._compute_cash_in_out()
            rec._compute_cash_difference()
            rec._compute_stock_summary()
            rec._compute_total_grand_collected()
            rec._compute_net_revenue()

    def action_submit(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_('Only draft records can be submitted.'))

            rec._compute_all_summaries()
            if rec.cash_difference and not rec.difference_reason:
                raise UserError(_('Difference reason is required when cash difference is not zero.'))
            rec.state = 'submitted'

    def action_approve(self):
        for rec in self:
            if rec.state != 'submitted':
                raise UserError(_('Only submitted records can be approved.'))

            approver = self.env.user.employee_id
            if not approver:
                raise UserError(_('Current user is not linked to an employee.'))

            rec.approved_by = approver.id
            rec.state = 'approved'

            # Lock the day for the branch via day-close date.
            rec.branch_id.write({'last_day_close_date': rec.date})

    def action_reopen(self):
        for rec in self:
            if not self.env.user.has_group('base.group_system'):
                raise AccessError(_('Only managers can reopen day close records.'))
            rec.state = 'draft'

    @api.model
    def _check_overdue_jobs(self):
        overdue_jobs = self.env['repair.job'].search([
            ('date_estimated_completion', '!=', False),
            ('date_estimated_completion', '<', fields.Datetime.now()),
            ('state', 'not in', ('ready', 'collected', 'cancelled')),
        ])
        for job in overdue_jobs:
            job.message_post(body=_('Job is overdue and requires branch follow-up.'))
        return len(overdue_jobs)
