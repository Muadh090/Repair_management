# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class RepairBranchDayCloseWizard(models.TransientModel):
    _name = 'repair.branch.day.close.wizard'
    _description = 'Repair Branch Day Close Wizard'

    branch_id = fields.Many2one(
        comodel_name='res.branch',
        string='Branch',
        required=True,
    )
    date = fields.Date(
        string='Date',
        default=fields.Date.context_today,
        readonly=True,
    )
    closed_by = fields.Many2one(
        comodel_name='hr.employee',
        string='Closed By',
        required=True,
        default=lambda self: self.env.user.employee_id,
    )

    jobs_received_today = fields.Integer(string='Jobs Received Today')
    jobs_completed_today = fields.Integer(string='Jobs Completed Today')
    jobs_pending = fields.Integer(string='Jobs Pending')
    jobs_collected_today = fields.Integer(string='Jobs Collected Today')

    cash_received_today = fields.Float(string='Cash Received Today')
    pos_received_today = fields.Float(string='POS Received Today')
    transfer_received_today = fields.Float(string='Transfer Received Today')
    total_received_today = fields.Float(
        string='Total Received Today',
        compute='_compute_total_received_today',
        store=True,
    )
    total_expenses_today = fields.Float(string='Total Expenses Today')
    opening_petty_cash = fields.Float(string='Opening Petty Cash')

    actual_cash_in_drawer = fields.Float(
        string='Actual Cash In Drawer',
        required=True,
    )
    cash_difference = fields.Float(
        string='Cash Difference',
        compute='_compute_cash_difference',
        store=True,
    )
    difference_reason = fields.Text(string='Difference Reason')

    low_stock_count = fields.Integer(string='Low Stock Count')
    out_of_stock_count = fields.Integer(string='Out of Stock Count')
    show_stock_warning = fields.Boolean(
        string='Show Stock Warning',
        compute='_compute_show_stock_warning',
        store=True,
    )

    operations_notes = fields.Text(string='Operations Notes')
    issues_to_report = fields.Text(string='Issues to Report')
    print_report = fields.Boolean(string='Print Daily Report', default=True)

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)

        user = self.env.user
        default_branch = user.branch_id
        if not default_branch and user.employee_id and hasattr(user.employee_id, 'branch_id'):
            default_branch = user.employee_id.branch_id

        if 'branch_id' in fields_list and default_branch:
            vals['branch_id'] = default_branch.id
        if 'closed_by' in fields_list and user.employee_id:
            vals['closed_by'] = user.employee_id.id

        date_value = vals.get('date') or fields.Date.context_today(self)
        branch_id = vals.get('branch_id')
        if branch_id:
            summary_vals = self._compute_all_summaries(branch_id, date_value)
            vals.update(summary_vals)

        return vals

    @api.onchange('branch_id')
    def _onchange_branch_id(self):
        if self.branch_id and self.date:
            vals = self._compute_all_summaries(self.branch_id.id, self.date)
            for key, value in vals.items():
                setattr(self, key, value)

    @api.depends('cash_received_today', 'pos_received_today', 'transfer_received_today')
    def _compute_total_received_today(self):
        for rec in self:
            rec.total_received_today = rec.cash_received_today + rec.pos_received_today + rec.transfer_received_today

    @api.depends('opening_petty_cash', 'cash_received_today', 'total_expenses_today', 'actual_cash_in_drawer')
    def _compute_cash_difference(self):
        for rec in self:
            expected = rec.opening_petty_cash + rec.cash_received_today - rec.total_expenses_today
            rec.cash_difference = rec.actual_cash_in_drawer - expected

    @api.depends('low_stock_count', 'out_of_stock_count')
    def _compute_show_stock_warning(self):
        for rec in self:
            rec.show_stock_warning = bool(rec.low_stock_count or rec.out_of_stock_count)

    def _compute_all_summaries(self, branch_id, date_value):
        RepairJob = self.env['repair.job']
        RepairPayment = self.env['repair.payment']
        PettyCash = self.env['repair.petty.cash']
        StockAlert = self.env['repair.stock.alert']

        start_dt = fields.Datetime.to_datetime('%s 00:00:00' % date_value)
        end_dt = fields.Datetime.to_datetime('%s 23:59:59' % date_value)

        vals = {
            'jobs_received_today': 0,
            'jobs_completed_today': 0,
            'jobs_pending': 0,
            'jobs_collected_today': 0,
            'cash_received_today': 0.0,
            'pos_received_today': 0.0,
            'transfer_received_today': 0.0,
            'total_expenses_today': 0.0,
            'opening_petty_cash': 0.0,
            'low_stock_count': 0,
            'out_of_stock_count': 0,
        }

        if not branch_id:
            return vals

        vals['jobs_received_today'] = RepairJob.search_count([
            ('branch_id', '=', branch_id),
            ('date_received', '>=', start_dt),
            ('date_received', '<=', end_dt),
        ])
        vals['jobs_completed_today'] = RepairJob.search_count([
            ('branch_id', '=', branch_id),
            ('date_completed', '>=', start_dt),
            ('date_completed', '<=', end_dt),
        ])
        vals['jobs_pending'] = RepairJob.search_count([
            ('branch_id', '=', branch_id),
            ('state', 'in', ('received', 'diagnosing', 'repairing', 'waiting_parts')),
        ])
        vals['jobs_collected_today'] = RepairJob.search_count([
            ('branch_id', '=', branch_id),
            ('date_collected', '>=', start_dt),
            ('date_collected', '<=', end_dt),
        ])

        payments = RepairPayment.search([
            ('branch_id', '=', branch_id),
            ('state', '=', 'confirmed'),
            ('payment_date', '=', date_value),
        ])
        vals['cash_received_today'] = sum(payments.filtered(lambda p: p.payment_method == 'cash').mapped('amount'))
        vals['pos_received_today'] = sum(payments.filtered(lambda p: p.payment_method in ('card', 'pos')).mapped('amount'))
        vals['transfer_received_today'] = sum(
            payments.filtered(lambda p: p.payment_method in ('bank_transfer', 'transfer')).mapped('amount')
        )

        expense_lines = PettyCash.search_read([
            ('branch_id', '=', branch_id),
            ('state', '=', 'posted'),
            ('transaction_type', '=', 'expense'),
            ('date', '>=', start_dt),
            ('date', '<=', end_dt),
        ], ['amount'])
        vals['total_expenses_today'] = sum(x.get('amount', 0.0) for x in expense_lines)

        last_before_day = PettyCash.search([
            ('branch_id', '=', branch_id),
            ('state', '=', 'posted'),
            ('date', '<', start_dt),
        ], order='date desc, id desc', limit=1)
        vals['opening_petty_cash'] = last_before_day.balance_after if last_before_day else 0.0

        vals['low_stock_count'] = StockAlert.search_count([
            ('branch_id', '=', branch_id),
            ('state', 'in', ('active', 'acknowledged')),
            ('alert_type', 'in', ('low_stock', 'critical')),
        ])
        vals['out_of_stock_count'] = StockAlert.search_count([
            ('branch_id', '=', branch_id),
            ('state', 'in', ('active', 'acknowledged')),
            ('alert_type', '=', 'out_of_stock'),
        ])

        return vals

    def _prepare_day_close_vals(self):
        self.ensure_one()
        return {
            'branch_id': self.branch_id.id,
            'date': self.date,
            'closed_by': self.closed_by.id,
            'approved_by': self.closed_by.id,
            'state': 'approved',
            'total_jobs_received': self.jobs_received_today,
            'total_jobs_completed': self.jobs_completed_today,
            'total_jobs_pending': self.jobs_pending,
            'total_jobs_collected': self.jobs_collected_today,
            'total_cash_collected': self.cash_received_today,
            'total_pos_collected': self.pos_received_today,
            'total_transfer_collected': self.transfer_received_today,
            'total_expenses': self.total_expenses_today,
            'opening_cash': self.opening_petty_cash,
            'actual_closing_cash': self.actual_cash_in_drawer,
            'difference_reason': self.difference_reason,
            'low_stock_items': self.low_stock_count + self.out_of_stock_count,
            'operations_notes': self.operations_notes,
            'issues_reported': self.issues_to_report,
        }

    def _post_petty_cash_closing_entry(self):
        self.ensure_one()
        if not self.cash_difference:
            return False

        amount = abs(self.cash_difference)
        tx_type = 'adjustment'
        notes = _('Day close variance adjustment: %s', self.difference_reason or 'No reason')

        tx = self.env['repair.petty.cash'].create({
            'branch_id': self.branch_id.id,
            'transaction_type': tx_type,
            'amount': amount,
            'done_by': self.closed_by.id,
            'approved_by': self.closed_by.id,
            'reference': _('Day Close %s', self.date),
            'notes': notes,
        })
        tx.action_post()
        return tx

    def _finalize_close(self, allow_variance=False):
        self.ensure_one()

        if not self.branch_id:
            raise UserError(_('Branch is required.'))
        if not self.closed_by:
            raise UserError(_('Closed by is required.'))
        if self.cash_difference and not allow_variance:
            raise UserError(_('Cash difference detected. Use "Close with Variance".'))
        if self.cash_difference and not self.difference_reason:
            raise UserError(_('Difference reason is required when there is a cash variance.'))

        vals = self._prepare_day_close_vals()
        close_record = self.env['repair.branch.day.close'].create(vals)

        self._post_petty_cash_closing_entry()

        # Branch day close state is represented by last_day_close_date.
        self.branch_id.write({'last_day_close_date': self.date})

        report = self.env.ref('repair_branch.action_report_branch_daily', raise_if_not_found=False)
        if self.print_report and report:
            return report.report_action(close_record)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('Branch day close completed successfully.'),
                'type': 'success',
                'sticky': False,
            },
        }

    def action_close_day(self):
        return self._finalize_close(allow_variance=False)

    def action_close_day_with_variance(self):
        return self._finalize_close(allow_variance=True)
