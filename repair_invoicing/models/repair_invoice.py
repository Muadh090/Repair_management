# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class RepairJobInvoicing(models.Model):
    _inherit = 'repair.job'

    # =====================================================================
    # INVOICE FIELDS
    # =====================================================================
    invoice_id = fields.Many2one(
        comodel_name='account.move',
        string='Invoice',
        readonly=True,
        copy=False,
    )
    invoice_state = fields.Selection(
        string='Invoice Status',
        related='invoice_id.payment_state',
        readonly=True,
    )
    invoice_date = fields.Date(
        string='Invoice Date',
        related='invoice_id.invoice_date',
        readonly=True,
    )
    invoice_amount_total = fields.Monetary(
        string='Invoice Total',
        related='invoice_id.amount_total',
        readonly=True,
    )
    invoice_amount_residual = fields.Monetary(
        string='Invoice Amount Due',
        related='invoice_id.amount_residual',
        readonly=True,
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id,
    )
    proforma_id = fields.Many2one(
        comodel_name='account.move',
        string='Proforma Invoice',
        readonly=True,
        copy=False,
    )
    credit_note_id = fields.Many2one(
        comodel_name='account.move',
        string='Credit Note',
        readonly=True,
        copy=False,
    )

    # =====================================================================
    # DEPOSIT FIELDS
    # =====================================================================
    deposit_ids = fields.One2many(
        comodel_name='repair.deposit',
        inverse_name='job_id',
        string='Deposits',
    )
    total_deposit = fields.Float(
        string='Total Deposits',
        compute='_compute_total_deposit',
        store=True,
    )
    requires_deposit = fields.Boolean(
        string='Requires Deposit',
        default=False,
    )
    deposit_amount_required = fields.Float(
        string='Deposit Required',
        default=0.0,
    )
    deposit_collected = fields.Boolean(
        string='Deposit Collected',
        compute='_compute_total_deposit',
        store=True,
    )

    # =====================================================================
    # PAYMENT FIELDS
    # =====================================================================
    payment_ids = fields.One2many(
        comodel_name='repair.payment',
        inverse_name='job_id',
        string='Payments',
    )
    total_paid = fields.Float(
        string='Total Paid',
        compute='_compute_total_paid',
        store=True,
    )
    payment_status = fields.Selection(
        selection=[
            ('unpaid', 'Unpaid'),
            ('partial', 'Partially Paid'),
            ('paid', 'Paid'),
        ],
        string='Payment Status',
        compute='_compute_payment_status',
        store=True,
    )
    last_payment_date = fields.Date(
        string='Last Payment Date',
        compute='_compute_total_paid',
        store=True,
    )

    # =====================================================================
    # FINANCIAL SUMMARY
    # =====================================================================
    subtotal = fields.Float(
        string='Subtotal',
        compute='_compute_subtotal',
        store=True,
    )
    discount_percent = fields.Float(
        string='Discount (%)',
        default=0.0,
    )
    discount_amount = fields.Float(
        string='Discount',
        compute='_compute_discount_amount',
        store=True,
        readonly=False,
    )
    tax_amount = fields.Float(
        string='Tax Amount',
        compute='_compute_grand_total',
        store=True,
    )
    grand_total = fields.Float(
        string='Grand Total',
        compute='_compute_grand_total',
        store=True,
    )
    balance_due = fields.Float(
        string='Balance Due',
        compute='_compute_balance_due',
        store=True,
    )

    # -----------------------------------------------------------------
    # COMPUTE METHODS
    # -----------------------------------------------------------------
    @api.depends('deposit_ids.amount', 'deposit_ids.state')
    def _compute_total_deposit(self):
        for job in self:
            confirmed = job.deposit_ids.filtered(
                lambda d: d.state == 'confirmed'
            )
            job.total_deposit = sum(confirmed.mapped('amount'))
            job.deposit_collected = (
                job.total_deposit >= job.deposit_amount_required
                if job.requires_deposit else True
            )

    @api.depends('payment_ids.amount', 'payment_ids.state', 'payment_ids.payment_date')
    def _compute_total_paid(self):
        for job in self:
            confirmed = job.payment_ids.filtered(
                lambda p: p.state == 'confirmed'
            )
            job.total_paid = sum(confirmed.mapped('amount'))
            if confirmed:
                job.last_payment_date = max(confirmed.mapped('payment_date'))
            else:
                job.last_payment_date = False

    @api.depends('total_paid', 'grand_total')
    def _compute_payment_status(self):
        for job in self:
            if job.total_paid <= 0:
                job.payment_status = 'unpaid'
            elif job.total_paid < job.grand_total:
                job.payment_status = 'partial'
            else:
                job.payment_status = 'paid'

    @api.depends('diagnosis_fee', 'labour_cost', 'parts_cost')
    def _compute_subtotal(self):
        for job in self:
            job.subtotal = job.diagnosis_fee + job.labour_cost + job.parts_cost

    @api.depends('subtotal', 'discount_percent')
    def _compute_discount_amount(self):
        for job in self:
            job.discount_amount = job.subtotal * (job.discount_percent / 100.0)

    @api.depends('subtotal', 'discount_amount')
    def _compute_grand_total(self):
        for job in self:
            taxable = job.subtotal - job.discount_amount
            # Use the partner's fiscal position / default taxes if configured
            taxes = self.env['account.tax']
            if job.customer_id and job.customer_id.property_account_position_id:
                fiscal = job.customer_id.property_account_position_id
                sale_taxes = self.env['account.tax'].search([
                    ('type_tax_use', '=', 'sale'),
                    ('company_id', '=', job.company_id.id or self.env.company.id),
                ], limit=1)
                if sale_taxes:
                    taxes = fiscal.map_tax(sale_taxes)
            if taxes:
                tax_res = taxes.compute_all(taxable, currency=job.currency_id)
                job.tax_amount = tax_res['total_included'] - tax_res['total_excluded']
                job.grand_total = tax_res['total_included']
            else:
                job.tax_amount = 0.0
                job.grand_total = taxable

    @api.depends('grand_total', 'total_paid', 'total_deposit')
    def _compute_balance_due(self):
        for job in self:
            job.balance_due = job.grand_total - job.total_paid - job.total_deposit

    # -----------------------------------------------------------------
    # INVOICE ACTIONS
    # -----------------------------------------------------------------
    def action_create_invoice(self):
        """Create a customer invoice from the repair job."""
        self.ensure_one()
        if self.invoice_id:
            raise UserError(_('An invoice already exists for this job.'))

        invoice_lines = []

        # Diagnosis fee line
        if self.diagnosis_fee:
            invoice_lines.append((0, 0, {
                'name': _('Diagnosis Fee – %s', self.name),
                'quantity': 1,
                'price_unit': self.diagnosis_fee,
            }))

        # Labour cost line
        if self.labour_cost:
            invoice_lines.append((0, 0, {
                'name': _('Labour Cost – %s', self.name),
                'quantity': 1,
                'price_unit': self.labour_cost,
            }))

        # Parts lines — one invoice line per part
        for line in self.parts_line_ids:
            invoice_lines.append((0, 0, {
                'name': line.product_id.display_name or _('Repair Part'),
                'product_id': line.product_id.id,
                'quantity': line.quantity,
                'price_unit': line.unit_price,
            }))

        # Discount as negative line
        if self.discount_amount > 0:
            invoice_lines.append((0, 0, {
                'name': _('Discount – %s', self.name),
                'quantity': 1,
                'price_unit': -self.discount_amount,
            }))

        if not invoice_lines:
            raise UserError(_('Nothing to invoice. Add fees or parts first.'))

        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.customer_id.id,
            'invoice_origin': self.name,
            'invoice_line_ids': invoice_lines,
        })
        self.invoice_id = invoice.id

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': invoice.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_create_proforma(self):
        """Create a proforma (estimate) invoice before repair starts."""
        self.ensure_one()
        if self.proforma_id:
            raise UserError(_('A proforma invoice already exists for this job.'))

        invoice_lines = []

        if self.diagnosis_fee:
            invoice_lines.append((0, 0, {
                'name': _('Diagnosis Fee (Estimate) – %s', self.name),
                'quantity': 1,
                'price_unit': self.diagnosis_fee,
            }))

        if self.labour_cost:
            invoice_lines.append((0, 0, {
                'name': _('Labour Cost (Estimate) – %s', self.name),
                'quantity': 1,
                'price_unit': self.labour_cost,
            }))

        for line in self.parts_line_ids:
            invoice_lines.append((0, 0, {
                'name': _('%s (Estimate)', line.product_id.display_name or 'Part'),
                'product_id': line.product_id.id,
                'quantity': line.quantity,
                'price_unit': line.unit_price,
            }))

        if self.discount_amount > 0:
            invoice_lines.append((0, 0, {
                'name': _('Discount (Estimate) – %s', self.name),
                'quantity': 1,
                'price_unit': -self.discount_amount,
            }))

        if not invoice_lines:
            raise UserError(_('Nothing to estimate. Add fees or parts first.'))

        proforma = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.customer_id.id,
            'invoice_origin': _('PROFORMA – %s', self.name),
            'narration': _('This is a proforma invoice / estimate for repair job %s.', self.name),
            'invoice_line_ids': invoice_lines,
        })
        self.proforma_id = proforma.id

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': proforma.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_confirm_proforma(self):
        """Convert proforma invoice into a real invoice."""
        self.ensure_one()
        if not self.proforma_id:
            raise UserError(_('No proforma invoice to confirm.'))
        if self.invoice_id:
            raise UserError(_('A final invoice already exists for this job.'))

        proforma = self.proforma_id

        # Cancel the proforma
        if proforma.state == 'draft':
            proforma.button_cancel()

        # Create the real invoice using the standard method
        return self.action_create_invoice()

    def action_create_credit_note(self):
        """Create a credit note / refund for the repair job."""
        self.ensure_one()
        if not self.invoice_id:
            raise UserError(_('No invoice exists to create a credit note from.'))
        if self.credit_note_id:
            raise UserError(_('A credit note already exists for this job.'))

        credit_lines = []
        for inv_line in self.invoice_id.invoice_line_ids.filtered(
            lambda l: l.display_type == 'product'
        ):
            credit_lines.append((0, 0, {
                'name': _('Refund: %s', inv_line.name),
                'product_id': inv_line.product_id.id if inv_line.product_id else False,
                'quantity': inv_line.quantity,
                'price_unit': inv_line.price_unit,
            }))

        if not credit_lines:
            raise UserError(_('The invoice has no lines to refund.'))

        credit_note = self.env['account.move'].create({
            'move_type': 'out_refund',
            'partner_id': self.customer_id.id,
            'invoice_origin': self.name,
            'reversed_entry_id': self.invoice_id.id,
            'invoice_line_ids': credit_lines,
        })
        self.credit_note_id = credit_note.id

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': credit_note.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # -----------------------------------------------------------------
    # PAYMENT / SEND / PRINT ACTIONS
    # -----------------------------------------------------------------
    def action_register_payment(self):
        """Open the payment registration wizard."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Register Payment'),
            'res_model': 'repair.payment.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_job_id': self.id,
                'default_amount': self.balance_due,
                'default_customer_id': self.customer_id.id,
            },
        }

    def action_send_invoice(self):
        """Send the invoice to the customer by email."""
        self.ensure_one()
        if not self.invoice_id:
            raise UserError(_('No invoice to send. Create an invoice first.'))

        template = self.env.ref(
            'account.email_template_edi_invoice', raise_if_not_found=False
        )
        compose_ctx = {
            'default_model': 'account.move',
            'default_res_ids': [self.invoice_id.id],
            'default_template_id': template.id if template else False,
            'default_composition_mode': 'comment',
            'mark_invoice_as_sent': True,
            'force_email': True,
        }
        return {
            'type': 'ir.actions.act_window',
            'name': _('Send Invoice'),
            'res_model': 'mail.compose.message',
            'view_mode': 'form',
            'target': 'new',
            'context': compose_ctx,
        }

    def action_print_invoice(self):
        """Print / download the invoice PDF."""
        self.ensure_one()
        if not self.invoice_id:
            raise UserError(_('No invoice to print. Create an invoice first.'))
        return self.env.ref(
            'account.account_invoices'
        ).report_action(self.invoice_id)

    def action_print_receipt(self):
        """Print / download the payment receipt PDF."""
        self.ensure_one()
        return self.env.ref(
            'repair_invoicing.action_report_repair_receipt'
        ).report_action(self)
