from django.apps import AppConfig

class GamAccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'gam_accounts'
    verbose_name = 'GAM Accounts'
    
    def ready(self):
        import gam_accounts.signals