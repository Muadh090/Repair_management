# -*- coding: utf-8 -*-
{
    'name': 'Repair Inventory',
    'version': '18.0.1.0.0',
    'category': 'Inventory',
    'summary': 'Parts, stock, warehouses, transfers and purchasing for repair business',
    'description': """
Repair Inventory
================
Manages parts, stock, warehouses per branch, inter-branch transfers,
purchase requests and supplier management for the repair business.

Features:
- Parts catalog with supplier and pricing info
- Branch warehouse stock tracking
- Inter-branch stock transfers
- Purchase request workflow
- Stock adjustment wizard
- Stock level reports
    """,
    'author': 'Repair Management Team',
    'website': '',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'stock',
        'purchase',
        'repair_management',
    ],
    'data': [
        'data/inventory_data.xml',
        'security/ir.model.access.csv',
        'views/repair_parts_catalog_views.xml',
        'views/repair_stock_views.xml',
        'views/repair_transfer_views.xml',
        'views/repair_purchase_request_views.xml',
        'views/repair_inventory_menu.xml',
        'report/repair_stock_report_template.xml',
        'wizards/repair_stock_adjustment_wizard_views.xml',
        'wizards/repair_transfer_wizard_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
