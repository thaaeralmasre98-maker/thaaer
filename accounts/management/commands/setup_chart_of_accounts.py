from django.core.management.base import BaseCommand
from accounts.models import Account


class Command(BaseCommand):
    help = 'Setup basic chart of accounts structure'

    def handle(self, *args, **options):
        accounts_to_create = [
            # Assets
            ('1000', 'ASSET', None, 'Assets', 'الأصول'),
            ('1200', 'ASSET', '1000', 'Current Assets', 'الأصول المتداولة'),
            ('1211', 'ASSET', '1200', 'Cash', 'النقدية'),
            ('1251', 'ASSET', '1200', 'Accounts Receivable - Students', 'الذمم المدينة - الطلاب'),
            ('1300', 'ASSET', '1200', 'Employee Advances', 'سلف الموظفين'),
            
            # Liabilities
            ('2000', 'LIABILITY', None, 'Liabilities', 'الخصوم'),
            ('2100', 'LIABILITY', '2000', 'Current Liabilities', 'الخصوم المتداولة'),
            ('2101', 'LIABILITY', '2100', 'Course Revenues Received (In advance)', 'إيرادات الدورات المقبوضة مقدماً'),
            
            # Equity
            ('3000', 'EQUITY', None, 'Equity', 'حقوق الملكية'),
            ('3100', 'EQUITY', '3000', 'Owner\'s Equity', 'حقوق المالك'),
            
            # Revenue
            ('4000', 'REVENUE', None, 'Revenue', 'الإيرادات'),
            ('4100', 'REVENUE', '4000', 'Course Revenue', 'إيرادات الدورات'),
            
            # Expenses
            ('5000', 'EXPENSE', None, 'Expenses', 'المصروفات'),
            ('5100', 'EXPENSE', '5000', 'Employee Salaries', 'رواتب الموظفين'),
            ('5110', 'EXPENSE', '5000', 'Teacher Salaries', 'رواتب المدرسين'),
            ('5200', 'EXPENSE', '5000', 'Rent Expense', 'مصروف الإيجار'),
            ('5300', 'EXPENSE', '5000', 'Utilities Expense', 'مصروف المرافق'),
            ('5400', 'EXPENSE', '5000', 'Supplies Expense', 'مصروف المستلزمات'),
            ('5500', 'EXPENSE', '5000', 'Marketing Expense', 'مصروف التسويق'),
            ('5600', 'EXPENSE', '5000', 'Maintenance Expense', 'مصروف الصيانة'),
            ('5900', 'EXPENSE', '5000', 'Other Expenses', 'مصروفات أخرى'),
        ]
        
        created_count = 0
        
        for code, account_type, parent_code, name, name_ar in accounts_to_create:
            parent = None
            if parent_code:
                try:
                    parent = Account.objects.get(code=parent_code)
                except Account.DoesNotExist:
                    self.stdout.write(
                        self.style.WARNING(f'Parent account {parent_code} not found for {code}')
                    )
                    continue
            
            account, created = Account.objects.get_or_create(
                code=code,
                defaults={
                    'name': name,
                    'name_ar': name_ar,
                    'account_type': account_type,
                    'parent': parent,
                    'is_active': True,
                }
            )
            
            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'Created account: {code} - {name}')
                )
            else:
                self.stdout.write(f'Account already exists: {code} - {name}')
        
        self.stdout.write(
            self.style.SUCCESS(f'Setup complete. Created {created_count} new accounts.')
        )