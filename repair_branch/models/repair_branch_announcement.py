# -*- coding: utf-8 -*-

from odoo import api, fields, models


class RepairBranchAnnouncement(models.Model):
    _name = 'repair.branch.announcement'
    _description = 'Repair Branch Announcement'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_posted desc, id desc'

    name = fields.Char(
        string='Title',
        required=True,
        tracking=True,
    )
    message = fields.Html(
        string='Message',
    )
    from_branch_id = fields.Many2one(
        comodel_name='res.branch',
        string='From Branch',
        help='Leave empty when announcement is from head office.',
    )
    to_branch_ids = fields.Many2many(
        comodel_name='res.branch',
        relation='repair_branch_announcement_branch_rel',
        column1='announcement_id',
        column2='branch_id',
        string='To Branches',
        help='Leave empty to target all branches.',
    )
    priority = fields.Selection(
        selection=[
            ('normal', 'Normal'),
            ('important', 'Important'),
            ('urgent', 'Urgent'),
        ],
        string='Priority',
        default='normal',
        tracking=True,
    )
    date_posted = fields.Datetime(
        string='Posted On',
        default=fields.Datetime.now,
        tracking=True,
    )
    posted_by = fields.Many2one(
        comodel_name='res.users',
        string='Posted By',
        default=lambda self: self.env.user,
        readonly=True,
    )
    expiry_date = fields.Date(
        string='Expiry Date',
    )
    is_expired = fields.Boolean(
        string='Is Expired',
        compute='_compute_is_expired',
    )
    acknowledgement_required = fields.Boolean(
        string='Acknowledgement Required',
        default=False,
    )
    acknowledged_by_ids = fields.Many2many(
        comodel_name='res.users',
        relation='repair_branch_announcement_user_rel',
        column1='announcement_id',
        column2='user_id',
        string='Acknowledged By',
    )
    acknowledgement_count = fields.Integer(
        string='Acknowledgement Count',
        compute='_compute_acknowledgement_count',
    )
    attachment_ids = fields.Many2many(
        comodel_name='ir.attachment',
        relation='repair_branch_announcement_attachment_rel',
        column1='announcement_id',
        column2='attachment_id',
        string='Attachments',
    )

    @api.depends('expiry_date')
    def _compute_is_expired(self):
        today = fields.Date.context_today(self)
        for rec in self:
            rec.is_expired = bool(rec.expiry_date and rec.expiry_date < today)

    @api.depends('acknowledged_by_ids')
    def _compute_acknowledgement_count(self):
        for rec in self:
            rec.acknowledgement_count = len(rec.acknowledged_by_ids)

    def action_post(self):
        now = fields.Datetime.now()
        for rec in self:
            rec.write({
                'date_posted': now,
                'posted_by': self.env.user.id,
            })

    def action_acknowledge(self):
        for rec in self:
            if self.env.user.id not in rec.acknowledged_by_ids.ids:
                rec.write({'acknowledged_by_ids': [(4, self.env.user.id)]})
