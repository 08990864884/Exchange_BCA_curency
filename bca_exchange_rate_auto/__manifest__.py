{
    "name": "BCA Automatic Exchange Rate",
    "version": "16.0.1.0.0",
    "category": "Accounting/Accounting",
    "summary": "Automatically update currency rates from BCA kurs page",
    "author": "Abdurrachman Basurroh",
    "license": "LGPL-3",
    "depends": ["account"],
    "data": [
        "data/ir_cron.xml",
        "views/res_config_settings_views.xml",
    ],
    "installable": True,
    "application": False,
}
