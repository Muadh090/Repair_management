# -*- coding: utf-8 -*-

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class RepairBranchStaff(models.Model):
    _name = 'repair.branch.staff'
    _description = 'Repair Branch Staff Assignment'
    _order = 'branch_id, role, employee_id'

    employee_id = fields.Many2one(
        comodel_name='hr.employee',
        string='Employee',
        required=True,
    )
    branch_id = fields.Many2one(
        comodel_name='res.branch',
        string='Branch',
        required=True,
    )
    user_id = fields.Many2one(
        comodel_name='res.users',
        string='User',
    )
    role = fields.Selection(
        selection=[
            ('branch_manager', 'Branch Manager'),
            ('assistant_manager', 'Assistant Manager'),
            ('senior_technician', 'Senior Technician'),
            ('technician', 'Technician'),
            ('receptionist', 'Receptionist'),
            ('accountant', 'Accountant'),
            ('cashier', 'Cashier'),
            ('other', 'Other'),
        ],
        string='Role',
        required=True,
    )
    date_assigned = fields.Date(
        string='Date Assigned',
        default=fields.Date.context_today,
    )
    date_left = fields.Date(
        string='Date Left',
    )
    is_active = fields.Boolean(
        string='Active',
        default=True,
    )
    can_approve_discount = fields.Boolean(
        string='Can Approve Discount',
        default=False,
    )
    max_discount_percent = fields.Float(
        string='Max Discount %',
        default=0.0,
    )
    can_approve_expense = fields.Boolean(
        string='Can Approve Expense',
        default=False,
    )
    max_expense_amount = fields.Float(
        string='Max Expense Amount',
        default=0.0,
    )
    can_transfer_stock = fields.Boolean(
        string='Can Transfer Stock',
        default=False,
    )
    can_close_day = fields.Boolean(
        string='Can Close Day',
        default=False,
    )
    performance_target = fields.Float(
        string='Monthly Jobs Target',
    )
    notes = fields.Text(
        string='Notes',
    )

    jobs_this_month = fields.Integer(
        string='Jobs This Month',
        compute='_compute_jobs_this_month',
    )
    revenue_this_month = fields.Float(
        string='Revenue This Month',
        compute='_compute_revenue_this_month',
    )
    performance_percent = fields.Float(
        string='Performance %',
        compute='_compute_performance_percent',
    )

    _sql_constraints = [
        (
            'uniq_active_staff_branch_role',
            'unique(employee_id, branch_id, role, is_active)',
            'This employee already has this role in this branch.',
        )
    ]

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        if self.employee_id and self.employee_id.user_id:
            self.user_id = self.employee_id.user_id.id

    def _get_month_period(self):
        today = fields.Date.context_today(self)
        start = today.replace(day=1)
        end = start + relativedelta(months=1)
        return start, end

    @api.depends('employee_id', 'branch_id', 'is_active')
    def _compute_jobs_this_month(self):
        RepairJob = self.env['repair.job']
        month_start, next_month = self._get_month_period()

        for rec in self:
            if not rec.employee_id or not rec.branch_id:
                rec.jobs_this_month = 0
                continue

            domain = [
                ('branch_id', '=', rec.branch_id.id),
                ('date_received', '>=', month_start),
                ('date_received', '<', next_month),
                '|',
                ('technician_id', '=', rec.employee_id.id),
                ('technician_ids', 'in', rec.employee_id.id),
            ]
            rec.jobs_this_month = RepairJob.search_count(domain)

    @api.depends('employee_id', 'branch_id')
    def _compute_revenue_this_month(self):
        RepairPayment = self.env['repair.payment']
        month_start, next_month = self._get_month_period()

        for rec in self:
            if not rec.branch_id:
                rec.revenue_this_month = 0.0
                continue

            domain = [
                ('branch_id', '=', rec.branch_id.id),
                ('state', '=', 'confirmed'),
                ('payment_date', '>=', month_start),
                ('payment_date', '<', next_month),
            ]

            if rec.user_id:
                domain.append(('received_by', '=', rec.user_id.id))

            payments = RepairPayment.search_read(domain, ['amount'])
            rec.revenue_this_month = sum(line.get('amount', 0.0) for line in payments)

    @api.depends('jobs_this_month', 'performance_target')
    def _compute_performance_percent(self):
        for rec in self:
            if rec.performance_target:
                rec.performance_percent = (rec.jobs_this_month / rec.performance_target) * 100.0
            else:
                rec.performance_percent = 0.0

    def _get_target_groups(self):
        self.ensure_one()

        # Use custom groups if available; fallback to standard groups.
        role_groups = {
            'branch_manager': [
                'repair_branch.group_branch_manager',
                'base.group_system',
            ],
            'assistant_manager': [
                'repair_branch.group_branch_assistant_manager',
                'base.group_user',
            ],
            'senior_technician': [
                'repair_branch.group_branch_senior_technician',
                'base.group_user',
            ],
            'technician': [
                'repair_branch.group_branch_technician',
                'base.group_user',
            ],
            'receptionist': [
                'repair_branch.group_branch_receptionist',
                'base.group_user',
            ],
            'accountant': [
                'repair_branch.group_branch_accountant',
                'account.group_account_user',
            ],
            'cashier': [
                'repair_branch.group_branch_cashier',
                'base.group_user',
            ],
            'other': [
                'repair_branch.group_branch_other',
                'base.group_user',
            ],
        }

        groups = self.env['res.groups']
        for xmlid in role_groups.get(self.role, []):
            grp = self.env.ref(xmlid, raise_if_not_found=False)
            if grp:
                groups |= grp
        return groups

    def action_grant_system_access(self):
        for rec in self:
            if not rec.user_id:
                raise UserError(_('Please set a user for this staff record first.'))

            target_groups = rec._get_target_groups()
            if not target_groups:
                raise UserError(_('No security group is configured for this role.'))

            rec.user_id.write({'groups_id': [(4, g.id) for g in target_groups]})

    def action_revoke_system_access(self):
        for rec in self:
            if not rec.user_id:
                continue

            target_groups = rec._get_target_groups()
            if target_groups:
                rec.user_id.write({'groups_id': [(3, g.id) for g in target_groups]})
