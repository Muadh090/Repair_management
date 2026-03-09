# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class RepairPaymentWizard(models.TransientModel):
    _name = 'repair.payment.wizard'
    _description = 'Repair Payment Wizard'

    # -----------------------------------------------------------------
    # JOB SUMMARY (readonly)
    # -----------------------------------------------------------------
    job_id = fields.Many2one(
        comodel_name='repair.job',
        string='Repair Job',
        readonly=True,
    )
    customer_id = fields.Many2one(
        string='Customer',
        related='job_id.customer_id',
        readonly=True,
    )
    grand_total = fields.Float(
        string='Grand Total',
        related='job_id.grand_total',
        readonly=True,
    )
    total_paid = fields.Float(
        string='Total Paid',
        related='job_id.total_paid',
        readonly=True,
    )
    total_deposit = fields.Float(
        string='Total Deposits',
        related='job_id.total_deposit',
        readonly=True,
    )
    balance_due = fields.Float(
        string='Balance Due',
        related='job_id.balance_due',
        readonly=True,
    )

    # -----------------------------------------------------------------
    # PAYMENT ENTRY
    # -----------------------------------------------------------------
    amount = fields.Float(
        string='Payment Amount',
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
    payment_reference = fields.Char(string='Payment Reference')
    date = fields.Date(
        string='Payment Date',
        default=fields.Date.context_today,
    )
    journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Journal',
        required=True,
        domain="[('type', 'in', ('cash', 'bank'))]",
    )
    received_by = fields.Many2one(
        comodel_name='hr.employee',
        string='Received By',
    )
    notes = fields.Text(string='Notes')

    # -----------------------------------------------------------------
    # DEPOSIT
    # -----------------------------------------------------------------
    apply_deposit = fields.Boolean(
        string='Apply Existing Deposit',
        default=True,
    )
    deposit_to_apply = fields.Float(
        string='Deposit Available',
        compute='_compute_deposit_to_apply',
    )

    # -----------------------------------------------------------------
    # CHANGE & RECEIPT
    # -----------------------------------------------------------------
    change_amount = fields.Float(
        string='Change Due',
        compute='_compute_change_amount',
    )
    print_receipt = fields.Boolean(
        string='Print Receipt',
        default=True,
    )

    # -----------------------------------------------------------------
    # COMPUTE
    # -----------------------------------------------------------------
    @api.depends('job_id.total_deposit', 'apply_deposit')
    def _compute_deposit_to_apply(self):
        for wiz in self:
            if wiz.apply_deposit and wiz.job_id:
                wiz.deposit_to_apply = wiz.job_id.total_deposit
            else:
                wiz.deposit_to_apply = 0.0

    @api.depends('amount', 'balance_due', 'deposit_to_apply')
    def _compute_change_amount(self):
        for wiz in self:
            effective_payment = wiz.amount + wiz.deposit_to_apply
            if effective_payment > wiz.balance_due and wiz.balance_due > 0:
                wiz.change_amount = effective_payment - wiz.balance_due
            else:
                wiz.change_amount = 0.0

    # -----------------------------------------------------------------
    # ACTIONS
    # -----------------------------------------------------------------
    def action_confirm_payment(self):
        """Confirm the payment: create record, post accounting, update job."""
        self.ensure_one()

        if self.amount <= 0:
            raise UserError(_('Payment amount must be greater than zero.'))

        job = self.job_id
        if not job:
            raise UserError(_('No repair job linked to this payment.'))

        # 1. Create repair.payment record
        payment_vals = {
            'job_id': job.id,
            'amount': self.amount,
            'payment_method': self.payment_method,
            'payment_reference': self.payment_reference,
            'payment_date': self.date,
            'journal_id': self.journal_id.id,
            'received_by': self.received_by.id if self.received_by else False,
            'notes': self.notes,
            'invoice_id': job.invoice_id.id if job.invoice_id else False,
        }

        # 2. Apply deposit if requested
        if self.apply_deposit and self.deposit_to_apply > 0:
            payment_vals['is_deposit_applied'] = True
            payment_vals['deposit_applied_amount'] = self.deposit_to_apply

        repair_payment = self.env['repair.payment'].create(payment_vals)

        # 3. Post to accounting via confirm action
        repair_payment.action_confirm()

        # 4. If balance becomes zero and print_receipt is on, print receipt
        if self.print_receipt and job.balance_due <= 0:
            return self.action_print_receipt()

        # 5. Close wizard
        return {'type': 'ir.actions.act_window_close'}

    def action_print_receipt(self):
        """Generate and return the receipt PDF."""
        self.ensure_one()
        return self.env.ref(
            'repair_invoicing.action_report_repair_receipt'
        ).report_action(self.job_id)
