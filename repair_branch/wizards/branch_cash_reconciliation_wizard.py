# -*- coding: utf-8 -*-

from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class RepairBranchCashReconciliationWizard(models.TransientModel):
    _name = 'repair.branch.cash.reconciliation.wizard'
    _description = 'Repair Branch Cash Reconciliation Wizard'

    branch_id = fields.Many2one(
        comodel_name='res.branch',
        string='Branch',
        required=True,
    )
    date = fields.Date(
        string='Date',
        default=fields.Date.context_today,
        required=True,
    )
    reconciled_by = fields.Many2one(
        comodel_name='hr.employee',
        string='Reconciled By',
        default=lambda self: self.env.user.employee_id,
    )
    period = fields.Selection(
        selection=[
            ('daily', 'Daily'),
            ('weekly', 'Weekly'),
            ('monthly', 'Monthly'),
        ],
        string='Period',
        default='daily',
        required=True,
    )

    system_cash_total = fields.Float(string='System Cash Total')
    system_pos_total = fields.Float(string='System POS Total')
    system_transfer_total = fields.Float(string='System Transfer Total')
    system_grand_total = fields.Float(
        string='System Grand Total',
        compute='_compute_system_aggregates',
        store=True,
    )
    system_expenses_total = fields.Float(string='System Expenses Total')
    system_net_total = fields.Float(
        string='System Net Total',
        compute='_compute_system_aggregates',
        store=True,
    )

    physical_cash = fields.Float(string='Physical Cash')
    physical_pos = fields.Float(string='Physical POS')
    physical_transfer = fields.Float(string='Physical Transfer')
    physical_grand_total = fields.Float(
        string='Physical Grand Total',
        compute='_compute_variances',
        store=True,
    )

    cash_variance = fields.Float(
        string='Cash Variance',
        compute='_compute_variances',
        store=True,
    )
    pos_variance = fields.Float(
        string='POS Variance',
        compute='_compute_variances',
        store=True,
    )
    transfer_variance = fields.Float(
        string='Transfer Variance',
        compute='_compute_variances',
        store=True,
    )
    total_variance = fields.Float(
        string='Total Variance',
        compute='_compute_variances',
        store=True,
    )
    variance_reason = fields.Text(string='Variance Reason')

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)

        user = self.env.user
        default_branch = user.branch_id
        if not default_branch and user.employee_id and hasattr(user.employee_id, 'branch_id'):
            default_branch = user.employee_id.branch_id

        if 'branch_id' in fields_list and default_branch:
            vals['branch_id'] = default_branch.id
        if 'reconciled_by' in fields_list and user.employee_id:
            vals['reconciled_by'] = user.employee_id.id

        date_value = vals.get('date') or fields.Date.context_today(self)
        period = vals.get('period') or 'daily'
        branch_id = vals.get('branch_id')

        if branch_id:
            vals.update(self._compute_all_system_totals(branch_id, date_value, period))

        return vals

    @api.onchange('branch_id', 'date', 'period')
    def _onchange_recompute_system(self):
        if self.branch_id and self.date and self.period:
            vals = self._compute_all_system_totals(self.branch_id.id, self.date, self.period)
            for key, value in vals.items():
                setattr(self, key, value)

    def _get_period_range(self, date_value, period):
        date_obj = fields.Date.to_date(date_value)
        if period == 'daily':
            start_date = end_date = date_obj
        elif period == 'weekly':
            start_date = date_obj - timedelta(days=date_obj.weekday())
            end_date = start_date + timedelta(days=6)
        else:
            start_date = date_obj.replace(day=1)
            if start_date.month == 12:
                end_date = start_date.replace(month=12, day=31)
            else:
                next_month = start_date.replace(month=start_date.month + 1, day=1)
                end_date = next_month - timedelta(days=1)

        start_dt = fields.Datetime.to_datetime('%s 00:00:00' % start_date)
        end_dt = fields.Datetime.to_datetime('%s 23:59:59' % end_date)
        return start_date, end_date, start_dt, end_dt

    def _compute_all_system_totals(self, branch_id, date_value, period):
        RepairPayment = self.env['repair.payment']
        PettyCash = self.env['repair.petty.cash']

        vals = {
            'system_cash_total': 0.0,
            'system_pos_total': 0.0,
            'system_transfer_total': 0.0,
            'system_expenses_total': 0.0,
        }
        if not branch_id:
            return vals

        start_date, end_date, start_dt, end_dt = self._get_period_range(date_value, period)

        payments = RepairPayment.search([
            ('branch_id', '=', branch_id),
            ('state', '=', 'confirmed'),
            ('payment_date', '>=', start_date),
            ('payment_date', '<=', end_date),
        ])

        vals['system_cash_total'] = sum(payments.filtered(lambda p: p.payment_method == 'cash').mapped('amount'))
        vals['system_pos_total'] = sum(payments.filtered(lambda p: p.payment_method in ('card', 'pos')).mapped('amount'))
        vals['system_transfer_total'] = sum(
            payments.filtered(lambda p: p.payment_method in ('bank_transfer', 'transfer')).mapped('amount')
        )

        expenses = PettyCash.search_read([
            ('branch_id', '=', branch_id),
            ('state', '=', 'posted'),
            ('transaction_type', '=', 'expense'),
            ('date', '>=', start_dt),
            ('date', '<=', end_dt),
        ], ['amount'])
        vals['system_expenses_total'] = sum(e.get('amount', 0.0) for e in expenses)

        return vals

    @api.depends('system_cash_total', 'system_pos_total', 'system_transfer_total', 'system_expenses_total')
    def _compute_system_aggregates(self):
        for rec in self:
            rec.system_grand_total = rec.system_cash_total + rec.system_pos_total + rec.system_transfer_total
            rec.system_net_total = rec.system_grand_total - rec.system_expenses_total

    @api.depends(
        'physical_cash',
        'physical_pos',
        'physical_transfer',
        'system_cash_total',
        'system_pos_total',
        'system_transfer_total',
    )
    def _compute_variances(self):
        for rec in self:
            rec.physical_grand_total = rec.physical_cash + rec.physical_pos + rec.physical_transfer
            rec.cash_variance = rec.physical_cash - rec.system_cash_total
            rec.pos_variance = rec.physical_pos - rec.system_pos_total
            rec.transfer_variance = rec.physical_transfer - rec.system_transfer_total
            rec.total_variance = rec.cash_variance + rec.pos_variance + rec.transfer_variance

    def _post_variance_journal_entry(self):
        self.ensure_one()
        if not self.total_variance:
            return False

        journal = self.branch_id.journal_id or self.branch_id.bank_journal_id
        if not journal or not journal.default_account_id:
            return False

        account = journal.default_account_id
        counterpart = journal.company_id.account_journal_suspense_account_id or account
        amount = abs(self.total_variance)

        if self.total_variance > 0:
            debit_acc = account
            credit_acc = counterpart
        else:
            debit_acc = counterpart
            credit_acc = account

        move = self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': journal.id,
            'date': self.date,
            'ref': _('Branch Reconciliation %s', self.branch_id.name),
            'line_ids': [
                (0, 0, {
                    'name': _('Reconciliation Variance'),
                    'account_id': debit_acc.id,
                    'debit': amount,
                    'credit': 0.0,
                }),
                (0, 0, {
                    'name': _('Reconciliation Variance'),
                    'account_id': credit_acc.id,
                    'debit': 0.0,
                    'credit': amount,
                }),
            ],
        })
        move.action_post()
        return move

    def action_confirm_reconciliation(self):
        self.ensure_one()

        if self.total_variance and not self.variance_reason:
            raise UserError(_('Variance reason is required when total variance is not zero.'))

        move = self._post_variance_journal_entry()

        # Create reconciliation log record through branch chatter.
        self.branch_id.message_post(
            body=_(
                'Cash reconciliation completed for %s (%s). '
                'System Total: %.2f, Physical Total: %.2f, Variance: %.2f%s',
                self.date,
                self.period,
                self.system_grand_total,
                self.physical_grand_total,
                self.total_variance,
                move and (_(', Journal Entry: %s') % move.name) or ''
            )
        )

        # Update reconciliation date if the field is writable in runtime model.
        branch_field = self.branch_id._fields.get('last_reconciliation_date')
        if branch_field and not branch_field.compute:
            self.branch_id.write({'last_reconciliation_date': self.date})

        report = self.env.ref('repair_branch.action_report_branch_reconciliation', raise_if_not_found=False)
        if report:
            return report.report_action(self.branch_id)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Reconciliation Completed'),
                'message': _('Reconciliation has been confirmed successfully.'),
                'type': 'success',
                'sticky': False,
            },
        }
