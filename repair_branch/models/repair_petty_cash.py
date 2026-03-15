# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class RepairPettyCash(models.Model):
    _name = 'repair.petty.cash'
    _description = 'Repair Petty Cash Transaction'
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
    transaction_type = fields.Selection(
        selection=[
            ('top_up', 'Cash Top Up'),
            ('expense', 'Expense Payment'),
            ('collection', 'Cash Collection'),
            ('transfer_out', 'Transfer to Bank'),
            ('adjustment', 'Adjustment'),
        ],
        string='Transaction Type',
        required=True,
        tracking=True,
    )
    amount = fields.Float(
        string='Amount',
        required=True,
    )
    balance_before = fields.Float(
        string='Balance Before',
        compute='_compute_balances',
        store=True,
    )
    balance_after = fields.Float(
        string='Balance After',
        compute='_compute_balances',
        store=True,
    )
    date = fields.Datetime(
        string='Date',
        default=fields.Datetime.now,
        tracking=True,
    )
    done_by = fields.Many2one(
        comodel_name='hr.employee',
        string='Done By',
        default=lambda self: self.env.user.employee_id,
    )
    approved_by = fields.Many2one(
        comodel_name='hr.employee',
        string='Approved By',
    )
    reference = fields.Char(
        string='Reference',
    )
    notes = fields.Text(
        string='Notes',
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('posted', 'Posted'),
            ('reversed', 'Reversed'),
        ],
        string='Status',
        default='draft',
        tracking=True,
    )
    journal_entry_id = fields.Many2one(
        comodel_name='account.move',
        string='Journal Entry',
        readonly=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        records = self.browse()
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('repair.petty.cash') or 'New'

            branch_id = vals.get('branch_id')
            amount = vals.get('amount', 0.0)
            tx_type = vals.get('transaction_type')
            before = 0.0

            if branch_id:
                last_posted = self.search([
                    ('branch_id', '=', branch_id),
                    ('state', '=', 'posted'),
                ], order='date desc, id desc', limit=1)
                before = last_posted.balance_after if last_posted else 0.0

            vals['balance_before'] = before
            vals['balance_after'] = before + self._signed_amount(tx_type, amount)

            records |= super(RepairPettyCash, self).create([vals])
        return records

    def _signed_amount(self, tx_type, amount):
        if tx_type in ('expense', 'transfer_out'):
            return -amount
        return amount

    @api.depends('branch_id', 'transaction_type', 'amount', 'state', 'date')
    def _compute_balances(self):
        for rec in self:
            before = 0.0
            if rec.branch_id:
                prev = self.search([
                    ('branch_id', '=', rec.branch_id.id),
                    ('state', '=', 'posted'),
                    ('id', '!=', rec.id),
                    '|',
                    ('date', '<', rec.date),
                    '&', ('date', '=', rec.date), ('id', '<', rec.id),
                ], order='date desc, id desc', limit=1)
                before = prev.balance_after if prev else 0.0
            rec.balance_before = before
            rec.balance_after = before + rec._signed_amount(rec.transaction_type, rec.amount)

    def _create_journal_entry(self):
        self.ensure_one()
        branch = self.branch_id
        journal = branch.journal_id or branch.bank_journal_id
        if not journal:
            return False
        if not journal.default_account_id:
            return False

        company = journal.company_id
        account = journal.default_account_id
        amount = abs(self.amount)

        # Fallback pair account: use company's transfer account if available.
        counterpart = company.account_journal_suspense_account_id or account

        if self.transaction_type in ('expense', 'transfer_out'):
            debit_account = counterpart
            credit_account = account
        else:
            debit_account = account
            credit_account = counterpart

        move = self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': journal.id,
            'date': fields.Date.context_today(self),
            'ref': self.name,
            'line_ids': [
                (0, 0, {
                    'name': self.name,
                    'account_id': debit_account.id,
                    'debit': amount,
                    'credit': 0.0,
                }),
                (0, 0, {
                    'name': self.name,
                    'account_id': credit_account.id,
                    'debit': 0.0,
                    'credit': amount,
                }),
            ],
        })
        move.action_post()
        return move

    def action_post(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_('Only draft transactions can be posted.'))
            if rec.amount <= 0:
                raise UserError(_('Amount must be greater than zero.'))

            if rec.transaction_type in ('expense', 'transfer_out') and rec.balance_after < 0:
                raise UserError(_('Insufficient petty cash balance for this transaction.'))

            rec.approved_by = rec.approved_by or self.env.user.employee_id
            move = rec._create_journal_entry()
            rec.write({
                'journal_entry_id': move.id if move else False,
                'state': 'posted',
            })

    def action_reverse(self):
        for rec in self:
            if rec.state != 'posted':
                raise UserError(_('Only posted transactions can be reversed.'))

            reverse_move = False
            if rec.journal_entry_id and rec.journal_entry_id.state == 'posted':
                reverse_move = rec.journal_entry_id._reverse_moves(default_values_list=[{
                    'ref': _('Reversal of %s', rec.name),
                }], cancel=True)

            # Create explicit reversal transaction to keep running balances traceable.
            reverse_type_map = {
                'top_up': 'adjustment',
                'collection': 'adjustment',
                'adjustment': 'adjustment',
                'expense': 'adjustment',
                'transfer_out': 'adjustment',
            }
            reversal = self.create({
                'branch_id': rec.branch_id.id,
                'transaction_type': reverse_type_map.get(rec.transaction_type, 'adjustment'),
                'amount': -rec._signed_amount(rec.transaction_type, rec.amount),
                'date': fields.Datetime.now(),
                'done_by': self.env.user.employee_id.id,
                'approved_by': self.env.user.employee_id.id,
                'reference': _('Reversal of %s', rec.name),
                'notes': _('Auto reversal entry'),
                'state': 'posted',
                'journal_entry_id': reverse_move.id if reverse_move else False,
            })

            rec.write({
                'state': 'reversed',
                'notes': (rec.notes or '') + '\n' + _('Reversed by %s via %s', self.env.user.name, reversal.name),
            })
