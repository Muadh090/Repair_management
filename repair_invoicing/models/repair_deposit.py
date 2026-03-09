# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class RepairDeposit(models.Model):
    _name = 'repair.deposit'
    _description = 'Repair Deposit'
    _order = 'date desc, id desc'

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
    date = fields.Date(
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
            ('refunded', 'Refunded'),
        ],
        string='Status',
        default='draft',
        required=True,
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
                    'repair.deposit'
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
        """Confirm the deposit and create an accounting entry."""
        for deposit in self:
            if deposit.state != 'draft':
                raise UserError(_('Only draft deposits can be confirmed.'))

            if not deposit.journal_id:
                deposit.journal_id = self.env['account.journal'].search(
                    [('type', '=', 'cash'), ('company_id', '=', self.env.company.id)],
                    limit=1,
                )
            if not deposit.journal_id:
                raise UserError(
                    _('No journal found. Please set a journal on the deposit.')
                )

            receivable_account = deposit.customer_id.property_account_receivable_id
            if not receivable_account:
                raise UserError(
                    _('No receivable account configured for customer %s.',
                      deposit.customer_id.display_name)
                )

            move = self.env['account.move'].create({
                'move_type': 'entry',
                'journal_id': deposit.journal_id.id,
                'date': deposit.date,
                'ref': _('Deposit %s – %s', deposit.name, deposit.job_id.name),
                'line_ids': [
                    (0, 0, {
                        'name': _('Deposit %s', deposit.name),
                        'partner_id': deposit.customer_id.id,
                        'account_id': deposit.journal_id.default_account_id.id,
                        'debit': deposit.amount,
                        'credit': 0.0,
                    }),
                    (0, 0, {
                        'name': _('Deposit %s', deposit.name),
                        'partner_id': deposit.customer_id.id,
                        'account_id': receivable_account.id,
                        'debit': 0.0,
                        'credit': deposit.amount,
                    }),
                ],
            })
            move.action_post()

            deposit.write({
                'state': 'confirmed',
                'move_id': move.id,
            })

    def action_refund(self):
        """Mark deposit as refunded and reverse the accounting entry."""
        for deposit in self:
            if deposit.state != 'confirmed':
                raise UserError(_('Only confirmed deposits can be refunded.'))

            if deposit.move_id:
                reversal_wizard = self.env['account.move.reversal'].with_context(
                    active_model='account.move',
                    active_ids=deposit.move_id.ids,
                ).create({
                    'journal_id': deposit.move_id.journal_id.id,
                    'reason': _('Refund deposit %s', deposit.name),
                    'date': fields.Date.context_today(self),
                })
                reversal_wizard.refund_moves()

            deposit.state = 'refunded'
