# -*- coding: utf-8 -*-
{
    'name': 'Repair Management',
    'version': '18.0.1.0.0',
    'category': 'Services',
    'summary': 'Core module for managing repair jobs and services',
    'description': """
Repair Management
=================
Core module of the repair business system.

Features:
- Repair job tracking
- Parts management
- Integration with accounting, inventory, purchasing, HR and expenses
    """,
    'author': 'Repair Management Team',
    'website': '',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'account',
        'stock',
        'hr_expense',
        'purchase',
        'hr',
    ],
    'data': [
        'data/repair_sequence.xml',
        'security/ir.model.access.csv',
        'views/repair_job_views.xml',
        'views/repair_parts_views.xml',
        'views/repair_menu.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
