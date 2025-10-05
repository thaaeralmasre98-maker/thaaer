from django.db import models
from django.core.validators import MinLengthValidator
from datetime import date
from decimal import Decimal
from django.contrib.auth.models import User
from django.db.models import Sum, Count, Q
from django.utils import timezone
from django.db.models.signals import post_save
from django.dispatch import receiver


class Employee(models.Model):
    POSITION_CHOICES = [
        ('admin', 'إداري'),
        ('accountant', 'محاسب'),
        ('mentor', 'مرشد'),
        ('manager', 'مدير'),
        ('marketing', 'تسويق'),
        ('reception', 'استقبال'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='employee')
    position = models.CharField(max_length=20, choices=POSITION_CHOICES)
    phone_number = models.CharField(max_length=20)
    hire_date = models.DateField(auto_now_add=True)
    salary = models.DecimalField(max_digits=10, decimal_places=2)

    last_salary_payment_date = models.DateField(
        null=True,
        blank=True,
        verbose_name='تاريخ آخر دفعة راتب'
    )

    def __str__(self):
        return f"{self.user.get_full_name()} - {self.get_position_display()}"

    @property
    def full_name(self):
        if self.user:
            full_name = self.user.get_full_name()
            return full_name if full_name else self.user.get_username()
        return ''

    @property
    def vacations(self):
        return Vacation.objects.filter(employee=self)

    def get_salary_status(self, year=None, month=None):
        """Return True if an employee salary is already recorded for the period."""
        if year is None:
            year = timezone.now().year
        if month is None:
            month = timezone.now().month
        try:
            from accounts.models import ExpenseEntry
            salary_qs = ExpenseEntry.objects.filter(
                employee=self,
                date__year=year,
                date__month=month
            )
            if salary_qs.exists():
                return True
            name_hint = self.full_name
            if name_hint:
                legacy_qs = ExpenseEntry.objects.filter(
                    teacher__isnull=True,
                    description__icontains=name_hint,
                    category__in=['SALARY', 'TEACHER_SALARY'],
                    date__year=year,
                    date__month=month
                )
                if legacy_qs.exists():
                    return True
            return False
        except Exception:
            return False

    def get_salary_account(self):
        from accounts.models import get_or_create_employee_salary_account
        return get_or_create_employee_salary_account(self)

    @property
    def salary_account(self):
        return self.get_salary_account()


class Teacher(models.Model):
    class BranchChoices(models.TextChoices):
        LITERARY = 'أدبي', 'أدبي'
        SCIENTIFIC = 'علمي', 'علمي'
        NINTH_GRADE = 'تاسع', 'الصف التاسع'

    full_name = models.CharField(
        max_length=100,
        verbose_name='الاسم الكامل',
        validators=[MinLengthValidator(3)]
    )
    phone_number = models.CharField(
        max_length=20,
        verbose_name='رقم الهاتف',
        validators=[MinLengthValidator(8)]
    )
    branches = models.CharField(
        max_length=100,
        verbose_name='الفروع',
        help_text='الفروع التي يدرّسها المدرّس مفصولة بفاصلة'
    )
    hire_date = models.DateField(default=date.today, verbose_name='تاريخ التعيين')
    notes = models.TextField(blank=True, null=True, verbose_name='ملاحظات')

    hourly_rate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        default=Decimal('0.00'),
        verbose_name='أجر الساعة',
        help_text='الأجر عن كل حصة دراسية'
    )
    monthly_salary = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        default=Decimal('0.00'),
        verbose_name='راتب شهري ثابت',
        help_text='يستخدم مع نوع الراتب الشهري أو المختلط'
    )
    salary_type = models.CharField(
        max_length=20,
        choices=[
            ('hourly', 'ساعي'),
            ('monthly', 'شهري ثابت'),
            ('mixed', 'مختلط (شهري + ساعي)')
        ],
        default='hourly',
        verbose_name='نوع الراتب'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.full_name

    def get_branches_list(self):
        if self.branches:
            return [branch.strip() for branch in self.branches.split(',') if branch.strip()]
        return []

    class Meta:
        verbose_name = 'مدرّس'
        verbose_name_plural = 'مدرّسون'
        ordering = ['-created_at']

    def get_daily_sessions(self, date=None):
        if date is None:
            date = timezone.now().date()
        from attendance.models import TeacherAttendance
        attendance = TeacherAttendance.objects.filter(
            teacher=self,
            date=date,
            status='present'
        ).first()
        return attendance.session_count if attendance else 0

    def get_monthly_sessions(self, year=None, month=None):
        if year is None:
            year = timezone.now().year
        if month is None:
            month = timezone.now().month
        from attendance.models import TeacherAttendance
        return TeacherAttendance.objects.filter(
            teacher=self,
            date__year=year,
            date__month=month,
            status='present'
        ).aggregate(total=Sum('session_count'))['total'] or 0

    def get_yearly_sessions(self, year=None):
        if year is None:
            year = timezone.now().year
        from attendance.models import TeacherAttendance
        return TeacherAttendance.objects.filter(
            teacher=self,
            date__year=year,
            status='present'
        ).aggregate(total=Sum('session_count'))['total'] or 0

    def calculate_monthly_salary(self, year=None, month=None):
        if year is None:
            year = timezone.now().year
        if month is None:
            month = timezone.now().month
        monthly_sessions = self.get_monthly_sessions(year, month)
        if self.salary_type == 'hourly':
            return Decimal(monthly_sessions) * (self.hourly_rate or Decimal('0'))
        if self.salary_type == 'monthly':
            return self.monthly_salary or Decimal('0')
        if self.salary_type == 'mixed':
            monthly_base = self.monthly_salary or Decimal('0')
            hourly_total = Decimal(monthly_sessions) * (self.hourly_rate or Decimal('0'))
            return monthly_base + hourly_total
        return Decimal('0.00')

    def get_salary_account(self):
        from accounts.models import get_or_create_teacher_salary_account
        return get_or_create_teacher_salary_account(self)

    @property
    def salary_account(self):
        return self.get_salary_account()

    def get_salary_status(self, year=None, month=None):
        if year is None:
            year = timezone.now().year
        if month is None:
            month = timezone.now().month
        try:
            from accounts.models import ExpenseEntry
            salary_qs = ExpenseEntry.objects.filter(
                teacher=self,
                date__year=year,
                date__month=month
            )
            if salary_qs.exists():
                return True

            name_hint = (self.full_name or '').strip()
            if name_hint:
                legacy_qs = ExpenseEntry.objects.filter(
                    teacher__isnull=True,
                    description__icontains=name_hint,
                    category__in=['SALARY', 'TEACHER_SALARY'],
                    date__year=year,
                    date__month=month
                )
                if legacy_qs.exists():
                    return True
            return False
        except Exception:
            return False


class Vacation(models.Model):
    VACATION_TYPES = [
        ('إدارية', 'إدارية'),
        ('مرضية', 'مرضية'),
        ('سنوية', 'سنوية'),
    ]

    STATUS_CHOICES = [
        ('معلقة', 'معلقة'),
        ('مقبولة', 'مقبولة'),
        ('مرفوضة', 'مرفوضة'),
    ]

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='vacations')
    vacation_type = models.CharField(max_length=20, choices=VACATION_TYPES, verbose_name='نوع الإجازة')
    reason = models.TextField(verbose_name='السبب')
    start_date = models.DateField(verbose_name='تاريخ البدء')
    end_date = models.DateField(verbose_name='تاريخ الانتهاء')
    submission_date = models.DateField(auto_now_add=True, verbose_name='تاريخ التقديم')
    is_replacement_secured = models.BooleanField(default=False, verbose_name='تم تأمين بديل')
    manager_opinion = models.TextField(blank=True, null=True, verbose_name='رأي الإدارة')
    general_manager_opinion = models.TextField(blank=True, null=True, verbose_name='رأي المدير العام')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='معلقة')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"إجازة {self.employee.user.get_full_name()} - {self.get_vacation_type_display()}"

    class Meta:
        verbose_name = 'إجازة'
        verbose_name_plural = 'إجازات'
        ordering = ['-created_at']


@receiver(post_save, sender=Employee)
def ensure_employee_salary_account(sender, instance, **kwargs):
    from accounts.models import get_or_create_employee_salary_account
    get_or_create_employee_salary_account(instance)


@receiver(post_save, sender=Teacher)
def ensure_teacher_salary_account(sender, instance, **kwargs):
    from accounts.models import get_or_create_teacher_salary_account
    get_or_create_teacher_salary_account(instance)

