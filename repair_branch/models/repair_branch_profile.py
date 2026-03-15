# -*- coding: utf-8 -*-

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _


class RepairBranchProfile(models.Model):
    _inherit = 'res.branch'

    code = fields.Char(
        string='Branch Code',
        required=True,
        tracking=True,
    )
    branch_type = fields.Selection(
        selection=[
            ('head_office', 'Head Office'),
            ('branch', 'Branch'),
            ('kiosk', 'Kiosk'),
        ],
        string='Branch Type',
        default='branch',
        tracking=True,
    )
    date_opened = fields.Date(
        string='Date Opened',
    )
    is_active_branch = fields.Boolean(
        string='Active Branch',
        default=True,
        tracking=True,
    )
    address = fields.Text(
        string='Address',
    )
    city = fields.Char(
        string='City',
    )
    state_id = fields.Many2one(
        comodel_name='res.country.state',
        string='State',
    )
    phone = fields.Char(
        string='Phone',
    )
    email = fields.Char(
        string='Email',
    )
    whatsapp = fields.Char(
        string='WhatsApp',
    )

    manager_id = fields.Many2one(
        comodel_name='hr.employee',
        string='Branch Manager',
    )
    assistant_manager_id = fields.Many2one(
        comodel_name='hr.employee',
        string='Assistant Manager',
    )
    accountant_id = fields.Many2one(
        comodel_name='hr.employee',
        string='Accountant',
    )
    staff_ids = fields.Many2many(
        comodel_name='hr.employee',
        relation='repair_branch_staff_rel',
        column1='branch_id',
        column2='employee_id',
        string='All Staff',
    )
    staff_count = fields.Integer(
        string='Staff Count',
        compute='_compute_staff_count',
    )

    warehouse_id = fields.Many2one(
        comodel_name='stock.warehouse',
        string='Warehouse',
    )
    journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Cash Journal',
        domain="[('type', 'in', ('cash', 'bank'))]",
    )
    bank_journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Bank Journal',
        domain="[('type', '=', 'bank')]",
    )
    opening_time = fields.Float(
        string='Opening Time',
        default=8.0,
    )
    closing_time = fields.Float(
        string='Closing Time',
        default=18.0,
    )
    working_days = fields.Many2many(
        comodel_name='resource.calendar.attendance',
        relation='repair_branch_working_days_rel',
        column1='branch_id',
        column2='attendance_id',
        string='Working Days',
    )
    is_day_closed = fields.Boolean(
        string='Day Closed',
        default=False,
        compute='_compute_is_day_closed',
    )
    last_day_close_date = fields.Date(
        string='Last Day Close Date',
    )

    monthly_target = fields.Float(
        string='Monthly Target',
    )
    daily_target = fields.Float(
        string='Daily Target',
        compute='_compute_performance_metrics',
    )
    current_month_revenue = fields.Float(
        string='Current Month Revenue',
        compute='_compute_performance_metrics',
    )
    current_month_jobs = fields.Integer(
        string='Current Month Jobs',
        compute='_compute_performance_metrics',
    )
    target_achievement = fields.Float(
        string='Target Achievement (%)',
        compute='_compute_performance_metrics',
    )
    total_lifetime_revenue = fields.Float(
        string='Total Lifetime Revenue',
        compute='_compute_performance_metrics',
    )
    average_daily_revenue = fields.Float(
        string='Average Daily Revenue',
        compute='_compute_performance_metrics',
    )

    total_jobs_today = fields.Integer(
        string='Jobs Today',
        compute='_compute_repair_stats',
    )
    pending_jobs_count = fields.Integer(
        string='Pending Jobs',
        compute='_compute_repair_stats',
    )
    ready_for_pickup_count = fields.Integer(
        string='Ready for Pickup',
        compute='_compute_repair_stats',
    )
    overdue_jobs_count = fields.Integer(
        string='Overdue Jobs',
        compute='_compute_repair_stats',
    )
    total_jobs_this_month = fields.Integer(
        string='Jobs This Month',
        compute='_compute_repair_stats',
    )
    comeback_rate = fields.Float(
        string='Comeback Rate (%)',
        compute='_compute_repair_stats',
    )

    todays_collection = fields.Float(
        string="Today's Collection",
        compute='_compute_financial_stats',
    )
    outstanding_balance = fields.Float(
        string='Outstanding Balance',
        compute='_compute_financial_stats',
    )
    petty_cash_balance = fields.Float(
        string='Petty Cash Balance',
        compute='_compute_financial_stats',
    )
    last_reconciliation_date = fields.Date(
        string='Last Reconciliation Date',
        compute='_compute_financial_stats',
    )

    low_stock_count = fields.Integer(
        string='Low Stock Items',
        compute='_compute_inventory_stats',
    )
    out_of_stock_count = fields.Integer(
        string='Out of Stock Items',
        compute='_compute_inventory_stats',
    )
    total_inventory_value = fields.Float(
        string='Total Inventory Value',
        compute='_compute_inventory_stats',
    )

    def _month_period(self):
        today = fields.Date.context_today(self)
        start = today.replace(day=1)
        end = start + relativedelta(months=1)
        return today, start, end

    @api.depends('staff_ids', 'manager_id', 'assistant_manager_id', 'accountant_id')
    def _compute_staff_count(self):
        for branch in self:
            ids = set(branch.staff_ids.ids)
            for emp in (branch.manager_id, branch.assistant_manager_id, branch.accountant_id):
                if emp:
                    ids.add(emp.id)
            branch.staff_count = len(ids)

    @api.depends('last_day_close_date')
    def _compute_is_day_closed(self):
        today = fields.Date.context_today(self)
        for branch in self:
            branch.is_day_closed = branch.last_day_close_date == today

    @api.depends('monthly_target', 'date_opened')
    def _compute_performance_metrics(self):
        RepairJob = self.env['repair.job']
        RepairPayment = self.env['repair.payment']
        today, month_start, next_month = self._month_period()

        for branch in self:
            month_revenue = RepairPayment.search_read(
                [
                    ('branch_id', '=', branch.id),
                    ('state', '=', 'confirmed'),
                    ('payment_date', '>=', month_start),
                    ('payment_date', '<', next_month),
                ],
                ['amount'],
            )
            branch.current_month_revenue = sum(line.get('amount', 0.0) for line in month_revenue)

            branch.current_month_jobs = RepairJob.search_count(
                [
                    ('branch_id', '=', branch.id),
                    ('date_received', '>=', month_start),
                    ('date_received', '<', next_month),
                ]
            )

            if branch.monthly_target:
                branch.target_achievement = (branch.current_month_revenue / branch.monthly_target) * 100.0
            else:
                branch.target_achievement = 0.0

            lifetime_revenue = RepairPayment.search_read(
                [('branch_id', '=', branch.id), ('state', '=', 'confirmed')],
                ['amount'],
            )
            branch.total_lifetime_revenue = sum(line.get('amount', 0.0) for line in lifetime_revenue)

            working_days_count = len(branch.working_days) or 26
            branch.daily_target = branch.monthly_target / working_days_count if working_days_count else 0.0

            start_date = branch.date_opened or today
            days_active = (today - start_date).days + 1 if start_date else 1
            branch.average_daily_revenue = branch.total_lifetime_revenue / max(days_active, 1)

    @api.depends('last_day_close_date')
    def _compute_repair_stats(self):
        RepairJob = self.env['repair.job']
        today, month_start, next_month = self._month_period()

        for branch in self:
            total_today = RepairJob.search_count(
                [('branch_id', '=', branch.id), ('date_received', '>=', today), ('date_received', '<', today + relativedelta(days=1))]
            )
            branch.total_jobs_today = total_today

            pending_domain = [
                ('branch_id', '=', branch.id),
                ('state', 'not in', ('collected', 'cancelled')),
            ]
            branch.pending_jobs_count = RepairJob.search_count(pending_domain)

            branch.ready_for_pickup_count = RepairJob.search_count(
                [('branch_id', '=', branch.id), ('state', '=', 'ready')]
            )

            overdue_domain = [
                ('branch_id', '=', branch.id),
                ('date_estimated_completion', '!=', False),
                ('date_estimated_completion', '<', fields.Datetime.now()),
                ('state', 'not in', ('ready', 'collected', 'cancelled')),
            ]
            branch.overdue_jobs_count = RepairJob.search_count(overdue_domain)

            month_jobs_domain = [
                ('branch_id', '=', branch.id),
                ('date_received', '>=', month_start),
                ('date_received', '<', next_month),
            ]
            total_month_jobs = RepairJob.search_count(month_jobs_domain)
            branch.total_jobs_this_month = total_month_jobs

            month_comeback_jobs = RepairJob.search_count(month_jobs_domain + [('is_comeback', '=', True)])
            branch.comeback_rate = (month_comeback_jobs / total_month_jobs) * 100.0 if total_month_jobs else 0.0

    @api.depends('journal_id', 'bank_journal_id')
    def _compute_financial_stats(self):
        RepairJob = self.env['repair.job']
        RepairPayment = self.env['repair.payment']
        today = fields.Date.context_today(self)

        for branch in self:
            today_payments = RepairPayment.search_read(
                [
                    ('branch_id', '=', branch.id),
                    ('state', '=', 'confirmed'),
                    ('payment_date', '=', today),
                ],
                ['amount'],
            )
            branch.todays_collection = sum(line.get('amount', 0.0) for line in today_payments)

            jobs = RepairJob.search([
                ('branch_id', '=', branch.id),
                ('state', '!=', 'cancelled'),
            ])
            branch.outstanding_balance = sum(jobs.mapped('balance_due'))

            petty_balance = 0.0
            if branch.journal_id and branch.journal_id.default_account_id:
                lines = self.env['account.move.line'].search([
                    ('account_id', '=', branch.journal_id.default_account_id.id),
                    ('parent_state', '=', 'posted'),
                ])
                petty_balance = sum(lines.mapped(lambda l: l.debit - l.credit))
            branch.petty_cash_balance = petty_balance

            recon_date = False
            if branch.bank_journal_id:
                statement = self.env['account.bank.statement'].search(
                    [('journal_id', '=', branch.bank_journal_id.id)],
                    order='date desc, id desc',
                    limit=1,
                )
                recon_date = statement.date if statement else False
            branch.last_reconciliation_date = recon_date

    @api.depends('warehouse_id')
    def _compute_inventory_stats(self):
        StockAlert = self.env['repair.stock.alert']
        StockQuant = self.env['stock.quant']

        for branch in self:
            branch.low_stock_count = StockAlert.search_count([
                ('branch_id', '=', branch.id),
                ('state', 'in', ('active', 'acknowledged')),
                ('alert_type', 'in', ('low_stock', 'critical')),
            ])
            branch.out_of_stock_count = StockAlert.search_count([
                ('branch_id', '=', branch.id),
                ('state', 'in', ('active', 'acknowledged')),
                ('alert_type', '=', 'out_of_stock'),
            ])

            if branch.warehouse_id and branch.warehouse_id.lot_stock_id:
                quants = StockQuant.search([
                    ('location_id', 'child_of', branch.warehouse_id.lot_stock_id.id),
                ])
                branch.total_inventory_value = sum(
                    quants.mapped(lambda q: q.quantity * q.product_id.standard_price)
                )
            else:
                branch.total_inventory_value = 0.0

    def action_open_jobs(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Branch Jobs'),
            'res_model': 'repair.job',
            'view_mode': 'list,kanban,form',
            'domain': [('branch_id', '=', self.id)],
            'context': {'default_branch_id': self.id},
        }

    def action_open_staff(self):
        self.ensure_one()
        staff_ids = set(self.staff_ids.ids)
        for emp in (self.manager_id, self.assistant_manager_id, self.accountant_id):
            if emp:
                staff_ids.add(emp.id)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Branch Staff'),
            'res_model': 'hr.employee',
            'view_mode': 'list,form',
            'domain': [('id', 'in', list(staff_ids))],
            'context': {},
        }

    def action_close_day(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Close Day'),
            'res_model': 'branch.day.close.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_branch_id': self.id},
        }

    def action_cash_reconciliation(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Cash Reconciliation'),
            'res_model': 'branch.cash.reconciliation.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_branch_id': self.id},
        }

    def action_view_targets(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Branch Targets'),
            'res_model': 'res.branch',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
            'context': {'show_branch_targets': True},
        }

    def action_print_daily_report(self):
        self.ensure_one()
        report = self.env.ref('repair_branch.action_report_branch_daily', raise_if_not_found=False)
        if report:
            return report.report_action(self)
        return False

    @api.model
    def _check_overdue_jobs(self):
        overdue_jobs = self.env['repair.job'].search([
            ('date_estimated_completion', '!=', False),
            ('date_estimated_completion', '<', fields.Datetime.now()),
            ('state', 'not in', ('ready', 'collected', 'cancelled')),
        ])
        for job in overdue_jobs:
            job.message_post(body=_('This repair job is overdue based on estimated completion date.'))
        return len(overdue_jobs)