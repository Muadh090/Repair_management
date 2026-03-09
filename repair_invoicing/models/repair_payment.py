# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class RepairPayment(models.Model):
    _name = 'repair.payment'
    _description = 'Repair Payment'
    _order = 'payment_date desc, id desc'

    name = fields.Char(
        string='Reference',
        readonly=True,
        copy=False,
        default='New',
    )
    job_id = fields.Many2one(
        comodel_name='repair.job',
        string='Repair Job',
        required=True,
        ondelete='cascade',
    )
    customer_id = fields.Many2one(
        string='Customer',
        related='job_id.customer_id',
        readonly=True,
        store=True,
    )
    branch_id = fields.Many2one(
        string='Branch',
        related='job_id.branch_id',
        readonly=True,
        store=True,
    )
    invoice_id = fields.Many2one(
        comodel_name='account.move',
        string='Invoice',
    )
    amount = fields.Float(
        string='Amount',
        required=True,
    )
    payment_method = fields.Selection(
        selection=[
            ('cash', 'Cash'),
            ('bank_transfer', 'Bank Transfer'),
            ('pos', 'POS'),
            ('cheque', 'Cheque'),
            ('other', 'Other'),
        ],
        string='Payment Method',
        required=True,
        default='cash',
    )
    payment_reference = fields.Char(
        string='Payment Reference',
        help='Bank reference or POS receipt number.',
    )
    payment_date = fields.Date(
        string='Date',
        default=fields.Date.context_today,
        required=True,
    )
    received_by = fields.Many2one(
        comodel_name='hr.employee',
        string='Received By',
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('confirmed', 'Confirmed'),
            ('reversed', 'Reversed'),
        ],
        string='Status',
        default='draft',
        required=True,
    )
    is_deposit_applied = fields.Boolean(
        string='Deposit Applied',
        default=False,
    )
    deposit_applied_amount = fields.Float(
        string='Deposit Applied Amount',
        default=0.0,
    )
    notes = fields.Text(string='Notes')
    journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Journal',
    )
    move_id = fields.Many2one(
        comodel_name='account.move',
        string='Journal Entry',
        readonly=True,
        copy=False,
    )

    # -----------------------------------------------------------------
    # CRUD
    # -----------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'repair.payment'
                ) or 'New'
        return super().create(vals_list)

    # -----------------------------------------------------------------
    # DISPLAY NAME
    # -----------------------------------------------------------------
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = '%s (%.2f)' % (rec.name or 'New', rec.amount)

    # -----------------------------------------------------------------
    # ACTIONS
    # -----------------------------------------------------------------
    def action_confirm(self):
        """Confirm payment, post to accounting, apply pending deposit."""
        for payment in self:
            if payment.state != 'draft':
                raise UserError(_('Only draft payments can be confirmed.'))

            if not payment.journal_id:
                payment.journal_id = self.env['account.journal'].search(
                    [('type', '=', 'cash'), ('company_id', '=', self.env.company.id)],
                    limit=1,
                )
            if not payment.journal_id:
                raise UserError(
                    _('No journal found. Please set a journal on the payment.')
                )

            receivable_account = payment.customer_id.property_account_receivable_id
            if not receivable_account:
                raise UserError(
                    _('No receivable account configured for customer %s.',
                      payment.customer_id.display_name)
                )

            # Check for un-applied deposits and deduct from balance
            deposit_applied = 0.0
            if payment.job_id.deposit_ids:
                confirmed_deposits = payment.job_id.deposit_ids.filtered(
                    lambda d: d.state == 'confirmed'
                )
                deposit_applied = sum(confirmed_deposits.mapped('amount'))

            actual_cash = payment.amount - deposit_applied
            if actual_cash < 0:
                actual_cash = 0.0

            move_lines = [
                (0, 0, {
                    'name': _('Payment %s', payment.name),
                    'partner_id': payment.customer_id.id,
                    'account_id': payment.journal_id.default_account_id.id,
                    'debit': actual_cash,
                    'credit': 0.0,
                }),
                (0, 0, {
                    'name': _('Payment %s', payment.name),
                    'partner_id': payment.customer_id.id,
                    'account_id': receivable_account.id,
                    'debit': 0.0,
                    'credit': payment.amount,
                }),
            ]

            # If deposit is applied, add a line for the deposit offset
            if deposit_applied > 0:
                move_lines.append((0, 0, {
                    'name': _('Deposit applied %s', payment.name),
                    'partner_id': payment.customer_id.id,
                    'account_id': receivable_account.id,
                    'debit': deposit_applied,
                    'credit': 0.0,
                }))

            move = self.env['account.move'].create({
                'move_type': 'entry',
                'journal_id': payment.journal_id.id,
                'date': payment.payment_date,
                'ref': _('Payment %s – %s', payment.name, payment.job_id.name),
                'line_ids': move_lines,
            })
            move.action_post()

            payment.write({
                'state': 'confirmed',
                'move_id': move.id,
                'is_deposit_applied': deposit_applied > 0,
                'deposit_applied_amount': deposit_applied,
            })

    def action_reverse(self):
        """Reverse a confirmed payment entry."""
        for payment in self:
            if payment.state != 'confirmed':
                raise UserError(_('Only confirmed payments can be reversed.'))

            if payment.move_id:
                reversal_wizard = self.env['account.move.reversal'].with_context(
                    active_model='account.move',
                    active_ids=payment.move_id.ids,
                ).create({
                    'journal_id': payment.move_id.journal_id.id,
                    'reason': _('Reverse payment %s', payment.name),
                    'date': fields.Date.context_today(self),
                })
                reversal_wizard.refund_moves()

            payment.state = 'reversed'
