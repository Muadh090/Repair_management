# -*- coding: utf-8 -*-
{
    'name': 'Repair Invoicing',
    'version': '18.0.1.0.0',
    'category': 'Accounting',
    'summary': 'Billing, payments, deposits and refunds for repair jobs',
    'description': """
Repair Invoicing
================
Handles all billing, payments, deposits, refunds and financial
transactions for repair jobs.

Features:
- Invoice generation from repair jobs
- Deposit and advance payment tracking
- Refund management
- Payment wizard for quick payments
- Printable invoice and receipt reports
    """,
    'author': 'Repair Management Team',
    'website': '',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'account',
        'repair_management',
    ],
    'data': [
        'data/invoice_sequence.xml',
        'security/ir.model.access.csv',
        'views/repair_invoice_views.xml',
        'views/repair_payment_views.xml',
        'views/repair_deposit_views.xml',
        'views/repair_invoice_menu.xml',
        'report/repair_invoice_template.xml',
        'report/repair_receipt_template.xml',
        'wizards/repair_payment_wizard_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
