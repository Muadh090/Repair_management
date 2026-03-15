# -*- coding: utf-8 -*-

from odoo import api, fields, models


class RepairTechnicianTarget(models.Model):
    _name = 'repair.technician.target'
    _description = 'Repair Technician Target'

    branch_target_id = fields.Many2one(
        comodel_name='repair.branch.target',
        string='Branch Target',
        ondelete='cascade',
    )
    technician_id = fields.Many2one(
        comodel_name='hr.employee',
        string='Technician',
        required=True,
    )
    jobs_target = fields.Integer(
        string='Jobs Target',
    )
    jobs_actual = fields.Integer(
        string='Jobs Actual',
        compute='_compute_actuals',
    )
    revenue_target = fields.Float(
        string='Revenue Target',
    )
    revenue_actual = fields.Float(
        string='Revenue Actual',
        compute='_compute_actuals',
    )
    achievement_percent = fields.Float(
        string='Achievement (%)',
        compute='_compute_achievement',
    )
    commission_rate = fields.Float(
        string='Commission Rate (%)',
    )
    commission_earned = fields.Float(
        string='Commission Earned',
        compute='_compute_commission',
    )
    bonus_threshold = fields.Float(
        string='Bonus Threshold (%)',
    )
    bonus_amount = fields.Float(
        string='Bonus Amount',
    )
    bonus_earned = fields.Float(
        string='Bonus Earned',
        compute='_compute_bonus',
    )

    _sql_constraints = [
        (
            'uniq_target_technician',
            'unique(branch_target_id, technician_id)',
            'A target for this technician already exists in this branch period.',
        )
    ]

    @api.depends('branch_target_id', 'technician_id')
    def _compute_actuals(self):
        RepairJob = self.env['repair.job']
        RepairPayment = self.env['repair.payment']

        for rec in self:
            rec.jobs_actual = 0
            rec.revenue_actual = 0.0

            if not rec.branch_target_id or not rec.technician_id:
                continue

            target = rec.branch_target_id
            if not target.branch_id or not target.month or not target.year:
                continue

            start_date, end_date, start_dt, end_dt = target._get_period_range()

            jobs_domain = [
                ('branch_id', '=', target.branch_id.id),
                ('date_received', '>=', start_dt),
                ('date_received', '<=', end_dt),
                '|',
                ('technician_id', '=', rec.technician_id.id),
                ('technician_ids', 'in', rec.technician_id.id),
            ]
            rec.jobs_actual = RepairJob.search_count(jobs_domain)

            if rec.technician_id.user_id:
                payments = RepairPayment.search_read(
                    [
                        ('branch_id', '=', target.branch_id.id),
                        ('state', '=', 'confirmed'),
                        ('payment_date', '>=', start_date),
                        ('payment_date', '<=', end_date),
                        ('received_by', '=', rec.technician_id.user_id.id),
                    ],
                    ['amount'],
                )
                rec.revenue_actual = sum(p.get('amount', 0.0) for p in payments)

    @api.depends('jobs_actual', 'jobs_target', 'revenue_actual', 'revenue_target')
    def _compute_achievement(self):
        for rec in self:
            jobs_ach = (rec.jobs_actual / rec.jobs_target) * 100.0 if rec.jobs_target else 0.0
            revenue_ach = (rec.revenue_actual / rec.revenue_target) * 100.0 if rec.revenue_target else 0.0

            if rec.jobs_target and rec.revenue_target:
                rec.achievement_percent = (jobs_ach + revenue_ach) / 2.0
            elif rec.jobs_target:
                rec.achievement_percent = jobs_ach
            elif rec.revenue_target:
                rec.achievement_percent = revenue_ach
            else:
                rec.achievement_percent = 0.0

    @api.depends('revenue_actual', 'commission_rate')
    def _compute_commission(self):
        for rec in self:
            rec.commission_earned = rec.revenue_actual * (rec.commission_rate / 100.0)

    @api.depends('achievement_percent', 'bonus_threshold', 'bonus_amount')
    def _compute_bonus(self):
        for rec in self:
            rec.bonus_earned = rec.bonus_amount if rec.achievement_percent >= rec.bonus_threshold and rec.bonus_threshold > 0 else 0.0
