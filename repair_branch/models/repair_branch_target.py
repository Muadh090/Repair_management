# -*- coding: utf-8 -*-

import calendar

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class RepairBranchTarget(models.Model):
    _name = 'repair.branch.target'
    _description = 'Repair Branch Monthly Target'
    _order = 'year desc, month desc, branch_id'

    name = fields.Char(
        string='Name',
        compute='_compute_name_and_period',
        store=True,
    )
    branch_id = fields.Many2one(
        comodel_name='res.branch',
        string='Branch',
        required=True,
    )
    month = fields.Integer(
        string='Month',
        required=True,
    )
    year = fields.Integer(
        string='Year',
        required=True,
    )
    period_display = fields.Char(
        string='Period',
        compute='_compute_name_and_period',
        store=True,
    )

    revenue_target = fields.Float(
        string='Revenue Target',
        required=True,
    )
    revenue_actual = fields.Float(
        string='Revenue Actual',
        compute='_compute_revenue_metrics',
    )
    revenue_achievement = fields.Float(
        string='Revenue Achievement (%)',
        compute='_compute_revenue_metrics',
    )
    revenue_variance = fields.Float(
        string='Revenue Variance',
        compute='_compute_revenue_metrics',
    )

    jobs_target = fields.Integer(
        string='Jobs Target',
    )
    jobs_actual = fields.Integer(
        string='Jobs Actual',
        compute='_compute_job_metrics',
    )
    jobs_achievement = fields.Float(
        string='Jobs Achievement (%)',
        compute='_compute_job_metrics',
    )
    new_customer_target = fields.Integer(
        string='New Customer Target',
    )
    new_customers_actual = fields.Integer(
        string='New Customers Actual',
        compute='_compute_job_metrics',
    )

    technician_target_ids = fields.One2many(
        comodel_name='repair.technician.target',
        inverse_name='branch_target_id',
        string='Technician Targets',
    )

    expense_budget = fields.Float(
        string='Expense Budget',
    )
    expense_actual = fields.Float(
        string='Expense Actual',
        compute='_compute_expense_metrics',
    )
    expense_variance = fields.Float(
        string='Expense Variance',
        compute='_compute_expense_metrics',
    )
    expense_achievement = fields.Float(
        string='Expense Achievement (%)',
        compute='_compute_expense_metrics',
    )

    overall_score = fields.Float(
        string='Overall Score',
        compute='_compute_performance',
    )
    performance_grade = fields.Selection(
        selection=[
            ('excellent', 'Excellent (>120%)'),
            ('good', 'Good (100-120%)'),
            ('average', 'Average (80-100%)'),
            ('below', 'Below Average (60-80%)'),
            ('poor', 'Poor (<60%)'),
        ],
        string='Performance Grade',
        compute='_compute_performance',
    )
    manager_comments = fields.Text(
        string='Manager Comments',
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('active', 'Active'),
            ('closed', 'Closed'),
        ],
        string='State',
        default='draft',
    )

    _sql_constraints = [
        (
            'uniq_branch_period_target',
            'unique(branch_id, month, year)',
            'A target already exists for this branch and month.',
        )
    ]

    @api.constrains('month', 'year')
    def _check_period_values(self):
        for rec in self:
            if rec.month < 1 or rec.month > 12:
                raise ValidationError('Month must be between 1 and 12.')
            if rec.year < 2000:
                raise ValidationError('Year value is invalid.')

    def _get_period_range(self):
        self.ensure_one()
        start_date = fields.Date.from_string(f'{self.year:04d}-{self.month:02d}-01')
        month_end = calendar.monthrange(self.year, self.month)[1]
        end_date = fields.Date.from_string(f'{self.year:04d}-{self.month:02d}-{month_end:02d}')
        start_dt = fields.Datetime.from_string(f'{self.year:04d}-{self.month:02d}-01 00:00:00')
        end_dt = fields.Datetime.from_string(f'{self.year:04d}-{self.month:02d}-{month_end:02d} 23:59:59')
        return start_date, end_date, start_dt, end_dt

    @api.depends('branch_id', 'month', 'year')
    def _compute_name_and_period(self):
        for rec in self:
            if rec.month and 1 <= rec.month <= 12 and rec.year:
                month_name = calendar.month_name[rec.month]
                rec.period_display = f'{month_name} {rec.year}'
            else:
                rec.period_display = ''
            rec.name = f'{rec.branch_id.name or "Branch"} - {rec.period_display}' if rec.period_display else (rec.branch_id.name or 'Branch Target')

    @api.depends('branch_id', 'month', 'year', 'revenue_target')
    def _compute_revenue_metrics(self):
        RepairPayment = self.env['repair.payment']
        for rec in self:
            rec.revenue_actual = 0.0
            rec.revenue_achievement = 0.0
            rec.revenue_variance = 0.0
            if not rec.branch_id or not rec.month or not rec.year:
                continue

            start_date, end_date, _, _ = rec._get_period_range()
            payments = RepairPayment.search_read(
                [
                    ('branch_id', '=', rec.branch_id.id),
                    ('state', '=', 'confirmed'),
                    ('payment_date', '>=', start_date),
                    ('payment_date', '<=', end_date),
                ],
                ['amount'],
            )
            rec.revenue_actual = sum(p.get('amount', 0.0) for p in payments)
            rec.revenue_variance = rec.revenue_actual - rec.revenue_target
            rec.revenue_achievement = (rec.revenue_actual / rec.revenue_target) * 100.0 if rec.revenue_target else 0.0

    @api.depends('branch_id', 'month', 'year', 'jobs_target', 'new_customer_target')
    def _compute_job_metrics(self):
        RepairJob = self.env['repair.job']
        for rec in self:
            rec.jobs_actual = 0
            rec.jobs_achievement = 0.0
            rec.new_customers_actual = 0
            if not rec.branch_id or not rec.month or not rec.year:
                continue

            _, _, start_dt, end_dt = rec._get_period_range()
            base_domain = [
                ('branch_id', '=', rec.branch_id.id),
                ('date_received', '>=', start_dt),
                ('date_received', '<=', end_dt),
            ]
            rec.jobs_actual = RepairJob.search_count(base_domain)
            rec.jobs_achievement = (rec.jobs_actual / rec.jobs_target) * 100.0 if rec.jobs_target else 0.0

            period_jobs = RepairJob.search(base_domain + [('customer_id', '!=', False)])
            new_customer_count = 0
            for partner in period_jobs.mapped('customer_id'):
                first_branch_job = RepairJob.search(
                    [
                        ('branch_id', '=', rec.branch_id.id),
                        ('customer_id', '=', partner.id),
                    ],
                    order='date_received asc, id asc',
                    limit=1,
                )
                if first_branch_job and start_dt <= first_branch_job.date_received <= end_dt:
                    new_customer_count += 1
            rec.new_customers_actual = new_customer_count

    @api.depends('branch_id', 'month', 'year', 'expense_budget')
    def _compute_expense_metrics(self):
        PettyCash = self.env['repair.petty.cash']
        for rec in self:
            rec.expense_actual = 0.0
            rec.expense_variance = 0.0
            rec.expense_achievement = 0.0
            if not rec.branch_id or not rec.month or not rec.year:
                continue

            _, _, start_dt, end_dt = rec._get_period_range()
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
            rec.expense_actual = sum(e.get('amount', 0.0) for e in expenses)
            rec.expense_variance = rec.expense_budget - rec.expense_actual
            rec.expense_achievement = (rec.expense_variance / rec.expense_budget) * 100.0 if rec.expense_budget else 0.0

    @api.depends(
        'revenue_achievement',
        'jobs_achievement',
        'new_customers_actual',
        'new_customer_target',
        'expense_achievement',
    )
    def _compute_performance(self):
        for rec in self:
            new_customer_achievement = (
                (rec.new_customers_actual / rec.new_customer_target) * 100.0
                if rec.new_customer_target else 0.0
            )
            rec.overall_score = (
                (rec.revenue_achievement * 0.40)
                + (rec.jobs_achievement * 0.30)
                + (new_customer_achievement * 0.10)
                + (rec.expense_achievement * 0.20)
            )

            if rec.overall_score > 120:
                rec.performance_grade = 'excellent'
            elif rec.overall_score >= 100:
                rec.performance_grade = 'good'
            elif rec.overall_score >= 80:
                rec.performance_grade = 'average'
            elif rec.overall_score >= 60:
                rec.performance_grade = 'below'
            else:
                rec.performance_grade = 'poor'
