# -*- coding: utf-8 -*-
{
    'name': 'Repair Branch Management',
    'version': '18.0.1.0.0',
    'category': 'Management',
    'summary': 'Head office and branch operations for repair business',
    'description': """
Repair Branch Management
========================
Manages head office and 5 branches including user access control,
branch performance tracking, inter-branch operations, staff management
per branch, daily operations, cash reconciliation and branch targets.
    """,
    'author': 'Repair Management Team',
    'website': '',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'account',
        'stock',
        'hr',
        'repair_management',
        'repair_invoicing',
        'repair_inventory',
    ],
    'data': [
        'data/branch_data.xml',
        'data/branch_security_groups.xml',
        'security/ir.model.access.csv',
        'security/branch_record_rules.xml',
        'views/repair_branch_views.xml',
        'views/repair_branch_staff_views.xml',
        'views/repair_branch_target_views.xml',
        'views/repair_branch_cash_views.xml',
        'views/repair_branch_operations_views.xml',
        'views/repair_branch_menu.xml',
        'report/branch_daily_report_template.xml',
        'report/branch_performance_report_template.xml',
        'wizards/branch_day_close_wizard_views.xml',
        'wizards/branch_cash_reconciliation_wizard_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
