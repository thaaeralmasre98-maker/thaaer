from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.utils import timezone
from django.urls import reverse
from decimal import Decimal
from django.db.models import Sum, Q
import uuid


class NumberSequence(models.Model):
    """For generating sequential numbers like receipt numbers, journal entry references, etc."""
    key = models.CharField(max_length=64, unique=True)
    last_value = models.BigIntegerField(default=0)

    @classmethod
    def next_value(cls, key):
        """Get the next sequential value for a given key"""
        obj, created = cls.objects.get_or_create(key=key, defaults={'last_value': 0})
        obj.last_value += 1
        obj.save()
        return obj.last_value


class Account(models.Model):
    ACCOUNT_TYPE_CHOICES = [
        ('ASSET', 'الأصول / Assets'),
        ('LIABILITY', 'الخصوم / Liabilities'),
        ('EQUITY', 'حقوق الملكية / Equity'),
        ('REVENUE', 'الإيرادات / Revenue'),
        ('EXPENSE', 'المصروفات / Expenses'),
    ]

    code = models.CharField(max_length=20, unique=True, verbose_name='رمز الحساب / Account Code')
    name = models.CharField(max_length=200, verbose_name='اسم الحساب / Account Name')
    name_ar = models.CharField(max_length=200, blank=True, verbose_name='الاسم بالعربية / Arabic Name')
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPE_CHOICES, verbose_name='نوع الحساب / Account Type')
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='children', verbose_name='الحساب الأب / Parent Account')
    description = models.TextField(blank=True, verbose_name='الوصف / Description')
    is_active = models.BooleanField(default=True, verbose_name='نشط / Active')
    balance = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='الرصيد / Balance')
    
    # Special flags for automatic account creation
    is_course_account = models.BooleanField(default=False, verbose_name='حساب الدورة / Course Account')
    course_name = models.CharField(max_length=200, blank=True, verbose_name='اسم الدورة / Course Name')
    is_student_account = models.BooleanField(default=False, verbose_name='حساب الطالب / Student Account')
    student_name = models.CharField(max_length=200, blank=True, verbose_name='اسم الطالب / Student Name')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'الحساب / Account'
        verbose_name_plural = 'الحسابات / Accounts'
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.display_name}"

    @property
    def display_name(self):
        return self.name_ar if self.name_ar else self.name

    def get_absolute_url(self):
        return reverse('accounts:account_detail', kwargs={'pk': self.pk})

    def get_net_balance(self):
        """Calculate net balance from transactions"""
        from django.db.models import Sum, Case, When
        
        transactions = self.transaction_set.filter(journal_entry__is_posted=True)
        
        debit_total = transactions.filter(is_debit=True).aggregate(
            total=Sum('amount'))['total'] or Decimal('0')
        credit_total = transactions.filter(is_debit=False).aggregate(
            total=Sum('amount'))['total'] or Decimal('0')
        
        # For asset and expense accounts, debit increases balance
        if self.account_type in ['ASSET', 'EXPENSE']:
            return debit_total - credit_total
        else:
            # For liability, equity, and revenue accounts, credit increases balance
            return credit_total - debit_total

    def get_debit_balance(self):
        """Get total debit amount"""
        return self.transaction_set.filter(
            is_debit=True, journal_entry__is_posted=True
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

    def get_credit_balance(self):
        """Get total credit amount"""
        return self.transaction_set.filter(
            is_debit=False, journal_entry__is_posted=True
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

    @property
    def rollup_balance(self):
        """Get balance including children accounts"""
        own_balance = self.get_net_balance()
        children_balance = sum(child.rollup_balance for child in self.children.all())
        return own_balance + children_balance

    def recalculate_tree_balances(self):
        """Recalculate balances for this account and all its children"""
        for child in self.children.all():
            child.recalculate_tree_balances()
        
        # Update own balance
        self.balance = self.get_net_balance()
        self.save(update_fields=['balance'])

    @classmethod
    def get_or_create_student_ar_account(cls, student):
        """Create or get student's accounts receivable account"""
        # Ensure AR parent exists
        ar_parent, _ = cls.objects.get_or_create(
            code='1251',
            defaults={
                'name': 'Accounts Receivable - Students',
                'name_ar': 'الذمم المدينة - الطلاب',
                'account_type': 'ASSET',
                'is_active': True,
            }
        )
        
        # Create student AR account
        student_code = f"1251-{student.id:03d}"
        account, created = cls.objects.get_or_create(
            code=student_code,
            defaults={
                'name': f'ST {student.full_name}',
                'name_ar': f'طالب - {student.full_name}',
                'account_type': 'ASSET',
                'parent': ar_parent,
                'is_student_account': True,
                'student_name': student.full_name,
                'is_active': True,
            }
        )
        return account

    @classmethod
    def get_or_create_course_revenue_account(cls, course):
        """Create or get course revenue account"""
        # Ensure course revenue parent exists
        revenue_parent, _ = cls.objects.get_or_create(
            code='2101',
            defaults={
                'name': 'Course Revenues Received (In advance)',
                'name_ar': 'إيرادات الدورات المقبوضة مقدماً',
                'account_type': 'LIABILITY',
                'is_active': True,
            }
        )
        
        # Create course revenue account
        course_code = f"2101-{course.id:03d}"
        account, created = cls.objects.get_or_create(
            code=course_code,
            defaults={
                'name': f'{course.name}',
                'name_ar': f'دورة - {course.name}',
                'account_type': 'LIABILITY',
                'parent': revenue_parent,
                'is_course_account': True,
                'course_name': course.name,
                'is_active': True,
            }
        )
        return account

    @classmethod
    def get_cash_account(cls):
        """Get or create main cash account"""
        account, created = cls.objects.get_or_create(
            code='1211',
            defaults={
                'name': 'Cash',
                'name_ar': 'النقدية',
                'account_type': 'ASSET',
                'is_active': True,
            }
        )
        return account


class CostCenter(models.Model):
    code = models.CharField(max_length=20, unique=True, verbose_name='الرمز / Code')
    name = models.CharField(max_length=100, verbose_name='الاسم / Name')
    name_ar = models.CharField(max_length=100, blank=True, verbose_name='الاسم بالعربية / Arabic Name')
    description = models.TextField(blank=True, verbose_name='الوصف / Description')
    is_active = models.BooleanField(default=True, verbose_name='نشط / Active')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'مركز التكلفة / Cost Center'
        verbose_name_plural = 'مراكز التكلفة / Cost Centers'
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.name_ar if self.name_ar else self.name}"


class Course(models.Model):
    name = models.CharField(max_length=200, verbose_name='اسم الدورة / Course Name')
    name_ar = models.CharField(max_length=200, blank=True, verbose_name='الاسم بالعربية / Arabic Name')
    description = models.TextField(blank=True, verbose_name='الوصف / Description')
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='السعر / Price')
    duration_hours = models.PositiveIntegerField(null=True, blank=True, verbose_name='المدة بالساعات / Duration (Hours)')
    is_active = models.BooleanField(default=True, verbose_name='نشط / Active')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'الدورة / Course'
        verbose_name_plural = 'الدورات / Courses'
        ordering = ['name']

    def __str__(self):
        return self.name_ar if self.name_ar else self.name

    def get_absolute_url(self):
        return reverse('accounts:course_detail', kwargs={'pk': self.pk})

    @property
    def revenue_account(self):
        """Get the revenue account for this course"""
        return Account.get_or_create_course_revenue_account(self)


class Student(models.Model):
    student_id = models.CharField(max_length=20, unique=True, verbose_name='رقم الطالب / Student ID')
    name = models.CharField(max_length=200, verbose_name='الاسم / Name')
    email = models.EmailField(blank=True, verbose_name='البريد الإلكتروني / Email')
    phone = models.CharField(max_length=20, blank=True, verbose_name='الهاتف / Phone')
    address = models.TextField(blank=True, verbose_name='العنوان / Address')
    is_active = models.BooleanField(default=True, verbose_name='نشط / Active')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'الطالب / Student'
        verbose_name_plural = 'الطلاب / Students'
        ordering = ['name']

    def __str__(self):
        return f"{self.student_id} - {self.name}"

    @property
    def ar_account(self):
        """Get the accounts receivable account for this student"""
        return Account.get_or_create_student_ar_account(self)


class JournalEntry(models.Model):
    ENTRY_TYPE_CHOICES = [
        ('MANUAL', 'يدوي / Manual'),
        ('ENROLLMENT', 'تسجيل / Enrollment'),
        ('PAYMENT', 'دفع / Payment'),
        ('COMPLETION', 'إكمال / Completion'),
        ('EXPENSE', 'مصروف / Expense'),
        ('ADJUSTMENT', 'تسوية / Adjustment'),
    ]

    reference = models.CharField(max_length=50, unique=True, verbose_name='المرجع / Reference')
    date = models.DateField(verbose_name='التاريخ / Date')
    description = models.TextField(verbose_name='الوصف / Description')
    entry_type = models.CharField(max_length=20, choices=ENTRY_TYPE_CHOICES, default='MANUAL', verbose_name='نوع القيد / Entry Type')
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, verbose_name='المبلغ الإجمالي / Total Amount')
    is_posted = models.BooleanField(default=False, verbose_name='مُرحل / Posted')
    posted_at = models.DateTimeField(null=True, blank=True, verbose_name='تاريخ الترحيل / Posted At')
    posted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='posted_entries', verbose_name='مُرحل بواسطة / Posted By')
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, verbose_name='أُنشئ بواسطة / Created By')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'قيد اليومية / Journal Entry'
        verbose_name_plural = 'قيود اليومية / Journal Entries'
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.reference} - {self.date}"

    def get_absolute_url(self):
        return reverse('accounts:journal_entry_detail', kwargs={'pk': self.pk})

    def save(self, *args, **kwargs):
        if not self.reference:
            next_num = NumberSequence.next_value('journal_entry')
            self.reference = f"JE-{next_num:06d}"
        super().save(*args, **kwargs)

    def post_entry(self, user):
        """Post the journal entry and update account balances"""
        if self.is_posted:
            raise ValueError("Entry is already posted")
        
        # Validate that debits equal credits
        total_debits = self.transactions.filter(is_debit=True).aggregate(
            total=Sum('amount'))['total'] or Decimal('0')
        total_credits = self.transactions.filter(is_debit=False).aggregate(
            total=Sum('amount'))['total'] or Decimal('0')
        
        if total_debits != total_credits:
            raise ValueError(f"Debits ({total_debits}) must equal credits ({total_credits})")
        
        self.is_posted = True
        self.posted_at = timezone.now()
        self.posted_by = user
        self.save()
        
        # Update account balances
        for transaction in self.transactions.all():
            transaction.account.recalculate_tree_balances()

    def reverse_entry(self, user, description=None):
        """Create a reversing journal entry"""
        if not self.is_posted:
            raise ValueError("Cannot reverse unposted entry")
        
        reversing_entry = JournalEntry.objects.create(
            date=timezone.now().date(),
            description=description or f"Reversal of {self.reference}",
            entry_type='ADJUSTMENT',
            total_amount=self.total_amount,
            created_by=user
        )
        
        # Create reversing transactions
        for transaction in self.transactions.all():
            Transaction.objects.create(
                journal_entry=reversing_entry,
                account=transaction.account,
                amount=transaction.amount,
                is_debit=not transaction.is_debit,  # Reverse the debit/credit
                description=f"Reversal: {transaction.description}",
                cost_center=transaction.cost_center
            )
        
        # Post the reversing entry
        reversing_entry.post_entry(user)
        return reversing_entry


class Transaction(models.Model):
    journal_entry = models.ForeignKey(JournalEntry, on_delete=models.CASCADE, related_name='transactions', verbose_name='قيد اليومية / Journal Entry')
    account = models.ForeignKey(Account, on_delete=models.PROTECT, verbose_name='الحساب / Account')
    amount = models.DecimalField(max_digits=15, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))], verbose_name='المبلغ / Amount')
    is_debit = models.BooleanField(verbose_name='مدين / Debit')
    description = models.CharField(max_length=500, blank=True, verbose_name='الوصف / Description')
    cost_center = models.ForeignKey(CostCenter, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='مركز التكلفة / Cost Center')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'المعاملة / Transaction'
        verbose_name_plural = 'المعاملات / Transactions'

    def __str__(self):
        return f"{self.account.code} - {self.amount} ({'Dr' if self.is_debit else 'Cr'})"

    @property
    def debit_amount(self):
        return self.amount if self.is_debit else Decimal('0')

    @property
    def credit_amount(self):
        return self.amount if not self.is_debit else Decimal('0')


class StudentEnrollment(models.Model):
    PAYMENT_METHOD_CHOICES = [
        ('CASH', 'نقد / Cash'),
        ('BANK', 'بنك / Bank'),
        ('CARD', 'بطاقة / Card'),
        ('TRANSFER', 'تحويل / Transfer'),
    ]

    student = models.ForeignKey('students.Student', on_delete=models.PROTECT, related_name='enrollments', verbose_name='الطالب / Student')
    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name='enrollments', verbose_name='الدورة / Course')
    enrollment_date = models.DateField(verbose_name='تاريخ التسجيل / Enrollment Date')
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='المبلغ الإجمالي / Total Amount')
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name='نسبة الخصم % / Discount Percent')
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='قيمة الخصم / Discount Amount')
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default='CASH', verbose_name='طريقة الدفع / Payment Method')
    notes = models.TextField(blank=True, verbose_name='ملاحظات / Notes')
    is_completed = models.BooleanField(default=False, verbose_name='مكتمل / Completed')
    completion_date = models.DateField(null=True, blank=True, verbose_name='تاريخ الإكمال / Completion Date')
    
    # Journal entry references
    enrollment_journal_entry = models.ForeignKey(JournalEntry, on_delete=models.SET_NULL, null=True, blank=True, related_name='enrollments', verbose_name='قيد التسجيل / Enrollment Entry')
    completion_journal_entry = models.ForeignKey(JournalEntry, on_delete=models.SET_NULL, null=True, blank=True, related_name='completions', verbose_name='قيد الإكمال / Completion Entry')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'تسجيل الطالب / Student Enrollment'
        verbose_name_plural = 'تسجيلات الطلاب / Student Enrollments'
        ordering = ['-enrollment_date']
        unique_together = ('student', 'course')

    def __str__(self):
        return f"{self.student.full_name} - {self.course.name}"

    @property
    def net_amount(self):
        """Calculate net amount after discounts"""
        after_percent = self.total_amount - (self.total_amount * self.discount_percent / Decimal('100'))
        return max(Decimal('0'), after_percent - self.discount_amount)

    @property
    def amount_paid(self):
        """Calculate total amount paid through receipts"""
        return self.payments.aggregate(total=Sum('paid_amount'))['total'] or Decimal('0')

    @property
    def balance_due(self):
        """Calculate remaining balance due"""
        return max(Decimal('0'), self.net_amount - self.amount_paid)

    def create_accrual_enrollment_entry(self, user):
        """Create the accrual journal entry for enrollment"""
        if self.enrollment_journal_entry:
            return self.enrollment_journal_entry
        
        # Get accounts
        student_ar_account = self.student.ar_account
        course_revenue_account = self.course.revenue_account
        
        # Create journal entry
        entry = JournalEntry.objects.create(
            date=self.enrollment_date,
            description=f"Student enrollment: {self.student.full_name} in {self.course.name}",
            entry_type='ENROLLMENT',
            total_amount=self.net_amount,
            created_by=user
        )
        
        # Create transactions
        Transaction.objects.create(
            journal_entry=entry,
            account=student_ar_account,
            amount=self.net_amount,
            is_debit=True,
            description=f"Enrollment receivable - {self.student.full_name}"
        )
        
        Transaction.objects.create(
            journal_entry=entry,
            account=course_revenue_account,
            amount=self.net_amount,
            is_debit=False,
            description=f"Deferred revenue - {self.course.name}"
        )
        
        # Post the entry
        entry.post_entry(user)
        
        # Link to enrollment
        self.enrollment_journal_entry = entry
        self.save(update_fields=['enrollment_journal_entry'])
        
        return entry


class StudentReceipt(models.Model):
    PAYMENT_METHOD_CHOICES = [
        ('CASH', 'نقد / Cash'),
        ('BANK', 'بنك / Bank'),
        ('CARD', 'بطاقة / Card'),
        ('TRANSFER', 'تحويل / Transfer'),
    ]

    receipt_number = models.CharField(max_length=50, unique=True, verbose_name='رقم الإيصال / Receipt Number')
    date = models.DateField(verbose_name='التاريخ / Date')
    student_name = models.CharField(max_length=200, verbose_name='اسم الطالب / Student Name')
    course_name = models.CharField(max_length=200, blank=True, verbose_name='اسم الدورة / Course Name')
    amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='المبلغ / Amount')
    paid_amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='المبلغ المدفوع / Paid Amount')
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name='نسبة الخصم % / Discount Percent')
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='قيمة الخصم / Discount Amount')
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default='CASH', verbose_name='طريقة الدفع / Payment Method')
    notes = models.TextField(blank=True, verbose_name='ملاحظات / Notes')
    is_printed = models.BooleanField(default=False, verbose_name='مطبوع / Printed')
    
    # Foreign key relationships
    student = models.ForeignKey(Student, on_delete=models.PROTECT, null=True, blank=True, related_name='receipts', verbose_name='الطالب / Student')
    student_profile = models.ForeignKey('students.Student', on_delete=models.PROTECT, null=True, blank=True, related_name='receipts', verbose_name='ملف الطالب / Student Profile')
    course = models.ForeignKey(Course, on_delete=models.PROTECT, null=True, blank=True, related_name='receipts', verbose_name='الدورة / Course')
    enrollment = models.ForeignKey(StudentEnrollment, on_delete=models.PROTECT, null=True, blank=True, related_name='payments', verbose_name='التسجيل / Enrollment')
    journal_entry = models.ForeignKey(JournalEntry, on_delete=models.SET_NULL, null=True, blank=True, related_name='receipts', verbose_name='قيد اليومية / Journal Entry')
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, verbose_name='أُنشئ بواسطة / Created By')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'إيصال الطالب / Student Receipt'
        verbose_name_plural = 'إيصالات الطلاب / Student Receipts'
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.receipt_number} - {self.student_name}"

    def save(self, *args, **kwargs):
        if not self.receipt_number:
            next_num = NumberSequence.next_value('student_receipt')
            self.receipt_number = f"SR-{next_num:06d}"
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('accounts:student_receipt_detail', kwargs={'pk': self.pk})

    @property
    def net_amount(self):
        """Calculate net amount after discounts"""
        if self.amount:
            after_percent = self.amount - (self.amount * self.discount_percent / Decimal('100'))
            return max(Decimal('0'), after_percent - self.discount_amount)
        return self.paid_amount

    def get_student_name(self):
        """Get student name from various sources"""
        if self.student_profile:
            return self.student_profile.full_name
        elif self.student:
            return self.student.name
        return self.student_name

    def get_course_name(self):
        """Get course name from various sources"""
        if self.course:
            return self.course.name
        return self.course_name

    def create_accrual_journal_entry(self, user):
        """Create journal entry for payment receipt"""
        if self.journal_entry:
            return self.journal_entry
        
        # Get accounts
        cash_account = Account.get_cash_account()
        
        if self.student_profile:
            student_ar_account = self.student_profile.ar_account
        elif self.student:
            # For legacy accounts model students
            student_ar_account = Account.get_or_create_student_ar_account(self.student)
        else:
            raise ValueError("No student associated with receipt")
        
        # Create journal entry
        entry = JournalEntry.objects.create(
            date=self.date,
            description=f"Payment receipt: {self.get_student_name()} - {self.get_course_name()}",
            entry_type='PAYMENT',
            total_amount=self.paid_amount,
            created_by=user
        )
        
        # Create transactions
        Transaction.objects.create(
            journal_entry=entry,
            account=cash_account,
            amount=self.paid_amount,
            is_debit=True,
            description=f"Cash received from {self.get_student_name()}"
        )
        
        Transaction.objects.create(
            journal_entry=entry,
            account=student_ar_account,
            amount=self.paid_amount,
            is_debit=False,
            description=f"Payment received - {self.get_course_name()}"
        )
        
        # Post the entry
        entry.post_entry(user)
        
        # Link to receipt
        self.journal_entry = entry
        self.save(update_fields=['journal_entry'])
        
        return entry


class ExpenseEntry(models.Model):
    CATEGORY_CHOICES = [
        ('SALARY', 'راتب / Salary'),
        ('TEACHER_SALARY', 'راتب مدرس / Teacher Salary'),
        ('RENT', 'إيجار / Rent'),
        ('UTILITIES', 'مرافق / Utilities'),
        ('SUPPLIES', 'مستلزمات / Supplies'),
        ('MARKETING', 'تسويق / Marketing'),
        ('MAINTENANCE', 'صيانة / Maintenance'),
        ('OTHER', 'أخرى / Other'),
    ]

    PAYMENT_METHOD_CHOICES = [
        ('CASH', 'نقد / Cash'),
        ('BANK', 'بنك / Bank'),
        ('CARD', 'بطاقة / Card'),
        ('TRANSFER', 'تحويل / Transfer'),
    ]

    reference = models.CharField(max_length=50, unique=True, verbose_name='المرجع / Reference')
    date = models.DateField(verbose_name='التاريخ / Date')
    description = models.CharField(max_length=500, verbose_name='الوصف / Description')
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, verbose_name='الفئة / Category')
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='المبلغ / Amount')
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default='CASH', verbose_name='طريقة الدفع / Payment Method')
    vendor = models.CharField(max_length=200, blank=True, verbose_name='المورد / Vendor')
    receipt_number = models.CharField(max_length=100, blank=True, verbose_name='رقم الإيصال / Receipt Number')
    notes = models.TextField(blank=True, verbose_name='ملاحظات / Notes')
    
    # Foreign key relationships
    employee = models.ForeignKey('employ.Employee', on_delete=models.SET_NULL, null=True, blank=True, related_name='expense_entries', verbose_name='الموظف / Employee')
    teacher = models.ForeignKey('employ.Teacher', on_delete=models.SET_NULL, null=True, blank=True, related_name='expense_entries', verbose_name='المعلم / Teacher')
    journal_entry = models.ForeignKey(JournalEntry, on_delete=models.SET_NULL, null=True, blank=True, related_name='expenses', verbose_name='قيد اليومية / Journal Entry')
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, verbose_name='أُنشئ بواسطة / Created By')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'قيد المصروف / Expense Entry'
        verbose_name_plural = 'قيود المصروفات / Expense Entries'
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.reference} - {self.description}"

    def save(self, *args, **kwargs):
        if not self.reference:
            next_num = NumberSequence.next_value('expense_entry')
            self.reference = f"EX-{next_num:06d}"
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('accounts:expense_detail', kwargs={'pk': self.pk})

    def create_journal_entry(self, user):
        """Create journal entry for expense"""
        if self.journal_entry:
            return self.journal_entry
        
        # Get accounts
        cash_account = Account.get_cash_account()
        
        # Get or create expense account based on category
        expense_account = self.get_or_create_expense_account()
        
        # Create journal entry
        entry = JournalEntry.objects.create(
            date=self.date,
            description=f"Expense: {self.description}",
            entry_type='EXPENSE',
            total_amount=self.amount,
            created_by=user
        )
        
        # Create transactions
        Transaction.objects.create(
            journal_entry=entry,
            account=expense_account,
            amount=self.amount,
            is_debit=True,
            description=self.description
        )
        
        Transaction.objects.create(
            journal_entry=entry,
            account=cash_account,
            amount=self.amount,
            is_debit=False,
            description=f"Cash payment - {self.description}"
        )
        
        # Post the entry
        entry.post_entry(user)
        
        # Link to expense
        self.journal_entry = entry
        self.save(update_fields=['journal_entry'])
        
        return entry

    def get_or_create_expense_account(self):
        """Get or create appropriate expense account"""
        # Map categories to account codes
        category_accounts = {
            'SALARY': ('5100', 'Employee Salaries', 'رواتب الموظفين'),
            'TEACHER_SALARY': ('5110', 'Teacher Salaries', 'رواتب المدرسين'),
            'RENT': ('5200', 'Rent Expense', 'مصروف الإيجار'),
            'UTILITIES': ('5300', 'Utilities Expense', 'مصروف المرافق'),
            'SUPPLIES': ('5400', 'Supplies Expense', 'مصروف المستلزمات'),
            'MARKETING': ('5500', 'Marketing Expense', 'مصروف التسويق'),
            'MAINTENANCE': ('5600', 'Maintenance Expense', 'مصروف الصيانة'),
            'OTHER': ('5900', 'Other Expenses', 'مصروفات أخرى'),
        }
        
        code, name, name_ar = category_accounts.get(self.category, category_accounts['OTHER'])
        
        account, created = Account.objects.get_or_create(
            code=code,
            defaults={
                'name': name,
                'name_ar': name_ar,
                'account_type': 'EXPENSE',
                'is_active': True,
            }
        )
        return account


class EmployeeAdvance(models.Model):
    employee = models.ForeignKey('employ.Employee', on_delete=models.SET_NULL, null=True, blank=True, related_name='advances', verbose_name='الموظف / Employee')
    employee_name = models.CharField(max_length=200, blank=True, verbose_name='الموظف / Employee Name')
    date = models.DateField(verbose_name='التاريخ / Date')
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='المبلغ / Amount')
    purpose = models.CharField(max_length=500, verbose_name='الغرض / Purpose')
    repayment_date = models.DateField(null=True, blank=True, verbose_name='تاريخ السداد / Repayment Date')
    is_repaid = models.BooleanField(default=False, verbose_name='مسدد / Repaid')
    repaid_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='المبلغ المسدد / Repaid Amount')
    reference = models.CharField(max_length=50, unique=True, verbose_name='المرجع / Reference')
    journal_entry = models.ForeignKey(JournalEntry, on_delete=models.SET_NULL, null=True, blank=True, related_name='advances', verbose_name='قيد اليومية / Journal Entry')
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, verbose_name='أُنشئ بواسطة / Created By')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'سلفة الموظف / Employee Advance'
        verbose_name_plural = 'سلف الموظفين / Employee Advances'
        ordering = ['-date']

    def __str__(self):
        return f"{self.reference} - {self.employee_name}"

    def save(self, *args, **kwargs):
        if not self.reference:
            next_num = NumberSequence.next_value('employee_advance')
            self.reference = f"ADV-{next_num:06d}"
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('accounts:advance_detail', kwargs={'pk': self.pk})

    @property
    def outstanding_amount(self):
        """Calculate outstanding amount"""
        return max(Decimal('0'), self.amount - self.repaid_amount)

    @property
    def advance_number(self):
        """Alias for reference"""
        return self.reference

    def create_advance_journal_entry(self, user):
        """Create journal entry for employee advance"""
        if self.journal_entry:
            return self.journal_entry
        
        # Get accounts
        cash_account = Account.get_cash_account()
        advance_account = self.get_or_create_advance_account()
        
        # Create journal entry
        entry = JournalEntry.objects.create(
            date=self.date,
            description=f"Employee advance: {self.employee_name} - {self.purpose}",
            entry_type='EXPENSE',
            total_amount=self.amount,
            created_by=user
        )
        
        # Create transactions
        Transaction.objects.create(
            journal_entry=entry,
            account=advance_account,
            amount=self.amount,
            is_debit=True,
            description=f"Advance to {self.employee_name}"
        )
        
        Transaction.objects.create(
            journal_entry=entry,
            account=cash_account,
            amount=self.amount,
            is_debit=False,
            description=f"Cash advance payment - {self.employee_name}"
        )
        
        # Post the entry
        entry.post_entry(user)
        
        # Link to advance
        self.journal_entry = entry
        self.save(update_fields=['journal_entry'])
        
        return entry

    def get_or_create_advance_account(self):
        """Get or create employee advance account"""
        account, created = Account.objects.get_or_create(
            code='1300',
            defaults={
                'name': 'Employee Advances',
                'name_ar': 'سلف الموظفين',
                'account_type': 'ASSET',
                'is_active': True,
            }
        )
        return account


class AccountingPeriod(models.Model):
    name = models.CharField(max_length=100, verbose_name='اسم الفترة / Period Name')
    start_date = models.DateField(verbose_name='تاريخ البداية / Start Date')
    end_date = models.DateField(verbose_name='تاريخ النهاية / End Date')
    is_closed = models.BooleanField(default=False, verbose_name='مقفلة / Closed')
    closed_at = models.DateTimeField(null=True, blank=True, verbose_name='تاريخ الإقفال / Closed At')
    closed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='closed_periods', verbose_name='أُقفل بواسطة / Closed By')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'الفترة المحاسبية / Accounting Period'
        verbose_name_plural = 'الفترات المحاسبية / Accounting Periods'
        ordering = ['-start_date']

    def __str__(self):
        return self.name

    @property
    def is_current(self):
        """Check if this is the current period"""
        today = timezone.now().date()
        return self.start_date <= today <= self.end_date


class Budget(models.Model):
    account = models.ForeignKey(Account, on_delete=models.CASCADE, verbose_name='الحساب / Account')
    period = models.ForeignKey(AccountingPeriod, on_delete=models.CASCADE, verbose_name='الفترة / Period')
    budgeted_amount = models.DecimalField(max_digits=15, decimal_places=2, verbose_name='المبلغ المخطط / Budgeted Amount')
    actual_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='المبلغ الفعلي / Actual Amount')
    notes = models.TextField(blank=True, verbose_name='ملاحظات / Notes')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'الميزانية / Budget'
        verbose_name_plural = 'الميزانيات / Budgets'
        unique_together = ('account', 'period')

    def __str__(self):
        return f"{self.account.code} - {self.period.name}"

    @property
    def variance(self):
        """Calculate variance (actual - budgeted)"""
        return self.actual_amount - self.budgeted_amount

    @property
    def variance_percentage(self):
        """Calculate variance percentage"""
        if self.budgeted_amount > 0:
            return (self.variance / self.budgeted_amount) * 100
        return Decimal('0')

    def calculate_variance(self):
        """Calculate and return variance"""
        return self.variance


class DiscountRule(models.Model):
    reason = models.CharField(max_length=200, unique=True, verbose_name='سبب الخصم / Discount Reason')
    reason_ar = models.CharField(max_length=200, blank=True, verbose_name='السبب بالعربية / Reason in Arabic')
    discount_percent = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0')), MinValueValidator(Decimal('100'))],
        verbose_name='نسبة الخصم % / Discount Percent'
    )
    discount_amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='قيمة الخصم الثابت / Fixed Discount Amount'
    )
    description = models.TextField(blank=True, verbose_name='الوصف / Description')
    is_active = models.BooleanField(default=True, verbose_name='نشط / Active')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'قاعدة الخصم / Discount Rule'
        verbose_name_plural = 'قواعد الخصم / Discount Rules'
        ordering = ['reason']

    def __str__(self):
        return self.reason


class StudentAccountLink(models.Model):
    """Link between student profile and their AR account"""
    student = models.OneToOneField('students.Student', on_delete=models.CASCADE, related_name='account_link', verbose_name='الطالب / Student')
    account = models.OneToOneField(Account, on_delete=models.CASCADE, related_name='student_link', verbose_name='الحساب / Account')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'ربط حساب الطالب / Student Account Link'
        verbose_name_plural = 'روابط حسابات الطلاب / Student Account Links'

    def __str__(self):
        return f"{self.student.full_name} -> {self.account.code}"


class StudentWithdrawal(models.Model):
    """Track student withdrawals from courses"""
    enrollment = models.ForeignKey(StudentEnrollment, on_delete=models.CASCADE, related_name='withdraw_logs')
    refunded_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    performed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Withdrawal: {self.enrollment.student.full_name} from {self.enrollment.course.name}"


# Helper functions for account creation
def get_or_create_employee_salary_account(employee):
    """Create salary account for employee"""
    code = f"5100-{employee.pk:04d}"
    account, created = Account.objects.get_or_create(
        code=code,
        defaults={
            'name': f'Salary - {employee.full_name}',
            'name_ar': f'راتب - {employee.full_name}',
            'account_type': 'EXPENSE',
            'is_active': True,
        }
    )
    return account


def get_or_create_teacher_salary_account(teacher):
    """Create salary account for teacher"""
    code = f"5110-{teacher.pk:04d}"
    account, created = Account.objects.get_or_create(
        code=code,
        defaults={
            'name': f'Teacher Salary - {teacher.full_name}',
            'name_ar': f'راتب مدرس - {teacher.full_name}',
            'account_type': 'EXPENSE',
            'is_active': True,
        }
    )
    return account