from datetime import date, timedelta
from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import View, TemplateView, ListView, DetailView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy, reverse
from django.contrib import messages
from django.http import JsonResponse
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils import timezone
from django.db.models import Sum, Count
from accounts.models import ExpenseEntry, EmployeeAdvance, Account
from .models import Teacher, Employee, Vacation
from .forms import TeacherForm, EmployeeRegistrationForm, AdminVacationForm
from attendance.models import TeacherAttendance
from django.contrib.auth.models import User
from django.contrib.auth.forms import SetPasswordForm
from decimal import Decimal

from accounts.forms import EmployeeAdvanceForm

class EmployeeAdvanceListView(LoginRequiredMixin, ListView):
    model = EmployeeAdvance
    template_name = 'employ/employee_advance_list.html'
    context_object_name = 'advances'
    
    def get_queryset(self):
        return EmployeeAdvance.objects.select_related('employee__user', 'created_by').order_by('-date')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Calculate summary statistics
        advances = self.get_queryset()
        context['total_advances'] = advances.count()
        context['outstanding_advances'] = advances.filter(is_repaid=False).count()
        context['total_outstanding_amount'] = sum(adv.outstanding_amount for adv in advances.filter(is_repaid=False))
        context['total_advance_amount'] = sum(adv.amount for adv in advances)
        
        return context


class EmployeeAdvanceCreateView(LoginRequiredMixin, CreateView):
    model = EmployeeAdvance
    form_class = EmployeeAdvanceForm
    template_name = 'employ/employee_advance_form.html'
    success_url = reverse_lazy('employ:employee_advance_list')
    
    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        
        # Create accounting journal entry
        try:
            self.object.create_advance_journal_entry(self.request.user)
            messages.success(
                self.request, 
                f'طھظ… ط¥ظ†ط´ط§ط، ط³ظ„ظپط© ظ„ظ„ظ…ظˆط¸ظپ {self.object.employee.user.get_full_name()} ط¨ظ…ط¨ظ„ط؛ {self.object.amount} ظ„.ط³'
            )
        except Exception as e:
            messages.error(self.request, f'ط®ط·ط£ ظپظٹ ط¥ظ†ط´ط§ط، ط§ظ„ظ‚ظٹط¯ ط§ظ„ظ…ط­ط§ط³ط¨ظٹ: {str(e)}')
        
        return response


class EmployeeAdvanceDetailView(LoginRequiredMixin, DetailView):
    model = EmployeeAdvance
    template_name = 'employ/employee_advance_detail.html'
    context_object_name = 'advance'


class EmployeeAdvanceRepayView(LoginRequiredMixin, View):
    def post(self, request, pk):
        advance = get_object_or_404(EmployeeAdvance, pk=pk)
        repayment_amount = Decimal(request.POST.get('repayment_amount', '0'))
        
        if repayment_amount <= 0:
            messages.error(request, 'ظٹط¬ط¨ ط¥ط¯ط®ط§ظ„ ظ…ط¨ظ„ط؛ ط³ط¯ط§ط¯ طµط­ظٹط­')
            return redirect('employ:employee_advance_detail', pk=pk)
        
        if repayment_amount > advance.outstanding_amount:
            messages.error(request, 'ظ…ط¨ظ„ط؛ ط§ظ„ط³ط¯ط§ط¯ ط£ظƒط¨ط± ظ…ظ† ط§ظ„ظ…ط¨ظ„ط؛ ط§ظ„ظ…طھط¨ظ‚ظٹ')
            return redirect('employ:employee_advance_detail', pk=pk)
        
        try:
            advance.create_repayment_entry(repayment_amount, request.user)
            messages.success(request, 'تم تسجيل سداد السلفة بنجاح.')
        except Exception as e:
            messages.error(request, f'تعذر تسجيل راتب {teacher.full_name}: {e}')
        
        return redirect('employ:employee_advance_detail', pk=pk)


class teachers(LoginRequiredMixin, ListView):
    model = Teacher
    template_name = 'employ/teachers.html'
    context_object_name = 'teachers'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        teachers = context.get('teachers') or context.get('object_list') or Teacher.objects.all()

        today = timezone.now().date()
        current_year = today.year
        current_month = today.month

        if today.day >= 25:
            period_date = today
        else:
            period_date = today.replace(day=1) - timedelta(days=1)

        salary_year = period_date.year
        salary_month = period_date.month

        teachers_data = []
        paid_count = 0
        unpaid_count = 0

        for teacher in teachers:
            monthly_sessions = teacher.get_monthly_sessions(salary_year, salary_month)
            salary_amount = teacher.calculate_monthly_salary(salary_year, salary_month)
            salary_status = teacher.get_salary_status(salary_year, salary_month)

            if salary_status:
                paid_count += 1
            else:
                unpaid_count += 1

            teachers_data.append({
                'teacher': teacher,
                'monthly_sessions': monthly_sessions,
                'calculated_salary': salary_amount,
                'salary_status': salary_status,
            })

        today_sessions = (TeacherAttendance.objects
                          .filter(date=today, status='present')
                          .aggregate(total=Sum('session_count'))['total'] or 0)

        context.update({
            'today': today,
            'salary_year': salary_year,
            'salary_month': salary_month,
            'salary_period_label': f"{salary_year}/{salary_month:02d}",
            'salary_period_is_current': (salary_year == current_year and salary_month == current_month),
            'teachers_data': teachers_data,
            'paid_count': paid_count,
            'unpaid_count': unpaid_count,
            'today_sessions': today_sessions,
        })
        return context
class CreateTeacherView(LoginRequiredMixin, CreateView):
    model = Teacher
    form_class = TeacherForm
    template_name = 'employ/teacher_form.html'
    success_url = reverse_lazy('employ:teachers')

    def form_valid(self, form):
        messages.success(self.request, 'تم إنشاء بيانات المعلم بنجاح.')
        return super().form_valid(form)
class hr(ListView):
    template_name = 'employ/hr.html'
    model = Employee
    context_object_name = 'employees'
    
    def get_queryset(self):
        queryset = Employee.objects.select_related('user').all()
        
        # Apply filters
        position = self.request.GET.get('position')
        search = self.request.GET.get('search')
        
        if position:
            queryset = queryset.filter(position=position)
        
        if search:
            queryset = queryset.filter(
                user__first_name__icontains=search
            ) | queryset.filter(
                user__last_name__icontains=search
            )
        
        return queryset


class EmployeeCreateView(CreateView):
    form_class = EmployeeRegistrationForm
    template_name = 'employ/employee_form.html'
    success_url = reverse_lazy('employ:hr')
    
    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f'طھظ… طھط³ط¬ظٹظ„ ط§ظ„ظ…ظˆط¸ظپ {self.object.get_full_name()} ط¨ظ†ط¬ط§ط­')
        return response


class EmployeeUpdateView(UpdateView):
    model = Employee
    fields = ['position', 'phone_number', 'salary']
    template_name = 'employ/employee_update.html'
    success_url = reverse_lazy('employ:hr')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['password_form'] = SetPasswordForm(self.object.user)
        return context
    
    def form_valid(self, form):
        # Handle password change if requested
        if 'change_password' in self.request.POST:
            password_form = SetPasswordForm(self.object.user, self.request.POST)
            if password_form.is_valid():
                password_form.save()
                messages.success(self.request, 'طھظ… طھط؛ظٹظٹط± ظƒظ„ظ…ط© ط§ظ„ظ…ط±ظˆط± ط¨ظ†ط¬ط§ط­')
            else:
                messages.error(self.request, 'ط®ط·ط£ ظپظٹ طھط؛ظٹظٹط± ظƒظ„ظ…ط© ط§ظ„ظ…ط±ظˆط±')
            return redirect(self.success_url)
        
        # Update user information
        user = self.object.user
        user.username = self.request.POST.get('username', user.username)
        user.first_name = self.request.POST.get('first_name', user.first_name)
        user.last_name = self.request.POST.get('last_name', user.last_name)
        user.email = self.request.POST.get('email', user.email)
        user.save()
        
        response = super().form_valid(form)
        messages.success(self.request, 'طھظ… طھط­ط¯ظٹط« ط¨ظٹط§ظ†ط§طھ ط§ظ„ظ…ظˆط¸ظپ ط¨ظ†ط¬ط§ط­')
        return response


class EmployeeDeleteView(DeleteView):
    model = Employee
    success_url = reverse_lazy('employ:hr')
    
    def delete(self, request, *args, **kwargs):
        employee = self.get_object()
        employee_name = employee.user.get_full_name()
        
        # Delete the user (which will cascade to employee)
        employee.user.delete()
        
        messages.success(request, 'تم تسجيل سداد السلفة بنجاح.')
        return JsonResponse({'success': True})


def select_employee(request):
    if request.method == 'POST':
        employee_id = request.POST.get('employee_id')
        return redirect('employ:employee_update', pk=employee_id)
    
    employees = Employee.objects.select_related('user').all()
    return render(request, 'employ/select_employee.html', {'employees': employees})


class EmployeeProfileView(LoginRequiredMixin, DetailView):
    model = Employee
    template_name = 'employ/employee_profile.html'
    context_object_name = 'employee'

    def _get_period_from_request(self):
        today = timezone.now().date()
        year_param = self.request.GET.get('year')
        month_param = self.request.GET.get('month')

        def sanitize(value, default, low=1, high=12):
            try:
                ivalue = int(value)
                if low <= ivalue <= high:
                    return ivalue
            except (TypeError, ValueError):
                pass
            return default

        if year_param is not None or month_param is not None:
            year = sanitize(year_param, today.year, low=1900, high=2100)
            month = sanitize(month_param, today.month)
            period_date = today.replace(year=year, month=month, day=1)
        else:
            period_date = today
            year = today.year
            month = today.month
        return today, period_date, year, month

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        employee = context['employee']
        today, period_date, salary_year, salary_month = self._get_period_from_request()

        salary_qs = ExpenseEntry.objects.filter(employee=employee).select_related('journal_entry').prefetch_related('journal_entry__transactions__account').order_by('-date', '-created_at')
        period_salary_qs = salary_qs.filter(date__year=salary_year, date__month=salary_month)
        salary_amount = employee.salary or Decimal('0')
        period_paid_total = period_salary_qs.aggregate(total=Sum('amount'))['total'] or Decimal('0')
        period_advances = list(EmployeeAdvance.objects.filter(
            employee=employee,
            is_repaid=False,
            date__year=salary_year,
            date__month=salary_month
        ))
        period_advance_outstanding = sum((adv.outstanding_amount for adv in period_advances), Decimal('0'))
        period_paid_total += period_advance_outstanding
        salary_status = period_salary_qs.exists() or (salary_amount > 0 and period_advance_outstanding >= salary_amount)
        salary_total_paid = salary_qs.aggregate(total=Sum('amount'))['total'] or Decimal('0')
        last_salary_payment = salary_qs.first()
        period_remaining_amount = salary_amount - period_paid_total
        if period_remaining_amount < Decimal('0'):
            period_remaining_amount = Decimal('0')

        salary_entries = []
        for payment in salary_qs[:10]:
            debit_account = None
            if payment.journal_entry:
                try:
                    debit_tx = payment.journal_entry.transactions.filter(is_debit=True).select_related('account').first()
                    if debit_tx and hasattr(debit_tx, 'account'):
                        debit_account = debit_tx.account
                except Exception:
                    debit_account = None
            salary_entries.append({
                'entry': payment,
                'debit_account': debit_account,
            })

        salary_account_code = f"5100-{employee.pk:04d}"
        salary_account = Account.objects.filter(code=salary_account_code).first()

        vacations_qs = Vacation.objects.filter(employee=employee).order_by('-start_date')
        status_totals = dict(vacations_qs.values('status').annotate(total=Count('id')).values_list('status', 'total'))
        vacations_list = list(vacations_qs)
        vacation_status_breakdown = [
            {
                'code': code,
                'label': label,
                'count': status_totals.get(code, 0),
            }
            for code, label in Vacation.STATUS_CHOICES
        ]
        vacations_total = len(vacations_list)
        vacations_current_year = sum(1 for vac in vacations_list if vac.start_date.year == today.year)
        upcoming_vacations = [vac for vac in vacations_list if vac.start_date >= today][:5]
        pending_status = Vacation.STATUS_CHOICES[0][0] if Vacation.STATUS_CHOICES else None
        pending_vacations_count = status_totals.get(pending_status, 0) if pending_status else 0

        advances_qs = EmployeeAdvance.objects.filter(employee=employee).order_by('-date')
        advances_list = list(advances_qs)
        advance_outstanding_total = sum((adv.outstanding_amount for adv in advances_list), Decimal('0'))
        outstanding_advances = [adv for adv in advances_list if not adv.is_repaid]

        months = [
            (1, 'كانون الثاني'), (2, 'شباط'), (3, 'آذار'), (4, 'نيسان'),
            (5, 'أيار'), (6, 'حزيران'), (7, 'تموز'), (8, 'آب'),
            (9, 'أيلول'), (10, 'تشرين الأول'), (11, 'تشرين الثاني'), (12, 'كانون الأول')
        ]

        context.update({
            'salary_year': salary_year,
            'salary_month': salary_month,
            'salary_period_label': f"{salary_year}/{salary_month:02d}",
            'salary_period_is_current': (salary_year == today.year and salary_month == today.month),
            'salary_amount': salary_amount,
            'salary_status': salary_status,
            'salary_total_paid': salary_total_paid,
            'salary_period_paid_total': period_paid_total,
            'salary_period_remaining': period_remaining_amount,
            'salary_period_advance_outstanding': period_advance_outstanding,
            'salary_entries': salary_entries,
            'last_salary_payment': last_salary_payment,
            'salary_account': salary_account,
            'salary_account_code': salary_account_code,
            'vacations': vacations_list,
            'salary_period_advances': period_advances,
            'display_name': _employee_full_name(employee),
            'vacations_total': vacations_total,
            'vacations_current_year': vacations_current_year,
            'vacation_status_breakdown': vacation_status_breakdown,
            'vacation_pending_count': pending_vacations_count,
            'upcoming_vacations': upcoming_vacations,
            'advances': advances_list,
            'advances_total': len(advances_list),
            'advance_outstanding_total': advance_outstanding_total,
            'outstanding_advances_count': len(outstanding_advances),
            'months': months,
            'today': today,
        })
        return context


class VacationListView(ListView):
    model = Vacation
    template_name = 'employ/vacation_list.html'
    context_object_name = 'vacations'
    
    def get_queryset(self):
        queryset = Vacation.objects.select_related('employee__user').all()
        
        # Apply filters
        employee_name = self.request.GET.get('employee_name')
        start_date = self.request.GET.get('start_date')
        end_date = self.request.GET.get('end_date')
        
        if employee_name:
            queryset = queryset.filter(
                employee__user__first_name__icontains=employee_name
            ) | queryset.filter(
                employee__user__last_name__icontains=employee_name
            )
        
        if start_date:
            queryset = queryset.filter(start_date__gte=start_date)
        
        if end_date:
            queryset = queryset.filter(end_date__lte=end_date)
        
        return queryset.order_by('-start_date')


class VacationCreateView(CreateView):
    model = Vacation
    form_class = AdminVacationForm
    template_name = 'employ/vacation_form.html'
    success_url = reverse_lazy('employ:vacation_list')

    def get_initial(self):
        initial = super().get_initial()
        employee_id = self.request.GET.get('employee')
        if employee_id:
            try:
                initial['employee'] = Employee.objects.get(pk=employee_id)
            except Employee.DoesNotExist:
                pass
        return initial

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, 'طھظ… طھط³ط¬ظٹظ„ ط§ظ„ط¥ط¬ط§ط²ط© ط¨ظ†ط¬ط§ط­')
        return response


class VacationUpdateView(UpdateView):
    model = Vacation
    form_class = AdminVacationForm
    template_name = 'employ/vacation_form.html'
    success_url = reverse_lazy('employ:vacation_list')
    
    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, 'طھظ… طھط­ط¯ظٹط« ط§ظ„ط¥ط¬ط§ط²ط© ط¨ظ†ط¬ط§ط­')
        return response


class SalaryManagementView(TemplateView):
    template_name = 'employ/salary_management.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get filter parameters
        selected_year = int(self.request.GET.get('year', timezone.now().year))
        selected_month = int(self.request.GET.get('month', timezone.now().month))
        
        # Month choices
        months = [
            (1, 'ظٹظ†ط§ظٹط±'), (2, 'ظپط¨ط±ط§ظٹط±'), (3, 'ظ…ط§ط±ط³'), (4, 'ط£ط¨ط±ظٹظ„'),
            (5, 'ظ…ط§ظٹظˆ'), (6, 'ظٹظˆظ†ظٹظˆ'), (7, 'ظٹظˆظ„ظٹظˆ'), (8, 'ط£ط؛ط³ط·ط³'),
            (9, 'ط³ط¨طھظ…ط¨ط±'), (10, 'ط£ظƒطھظˆط¨ط±'), (11, 'ظ†ظˆظپظ…ط¨ط±'), (12, 'ط¯ظٹط³ظ…ط¨ط±')
        ]
        
        # Get all teachers with their salary data
        teachers = Teacher.objects.all()
        teachers_salary_data = []
        total_calculated_amount = Decimal('0.00')
        paid_count = 0
        unpaid_count = 0
        
        for teacher in teachers:
            monthly_sessions = teacher.get_monthly_sessions(selected_year, selected_month)
            calculated_salary = teacher.calculate_monthly_salary(selected_year, selected_month)
            salary_status = teacher.get_salary_status(selected_year, selected_month)
            
            teachers_salary_data.append({
                'teacher': teacher,
                'monthly_sessions': monthly_sessions,
                'calculated_salary': calculated_salary,
                'salary_status': salary_status
            })
            
            total_calculated_amount += calculated_salary
            if salary_status:
                paid_count += 1
            else:
                unpaid_count += 1
        
        context.update({
            'teachers_salary_data': teachers_salary_data,
            'selected_year': selected_year,
            'selected_month': selected_month,
            'months': months,
            'total_calculated_amount': total_calculated_amount,
            'paid_count': paid_count,
            'unpaid_count': unpaid_count,
            'today': timezone.now().date()
        })
        
        return context



class TeacherProfileView(DetailView):
    model = Teacher
    template_name = 'employ/teacher_profile.html'
    context_object_name = 'teacher'

    def _get_period_from_request(self):
        today = timezone.now().date()
        year_param = self.request.GET.get('year')
        month_param = self.request.GET.get('month')

        def sanitize(value, default, low=1, high=12):
            try:
                ivalue = int(value)
                if low <= ivalue <= high:
                    return ivalue
            except (TypeError, ValueError):
                pass
            return default

        if year_param is not None or month_param is not None:
            year = sanitize(year_param, today.year, low=1900, high=2100)
            month = sanitize(month_param, today.month)
            period_date = today.replace(year=year, month=month, day=1)
        else:
            if today.day >= 28:
                period_date = today
            else:
                period_date = today.replace(day=1) - timedelta(days=1)
            year = period_date.year
            month = period_date.month

        return today, period_date, year, month

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        teacher = self.get_object()
        today, period_date, salary_year, salary_month = self._get_period_from_request()

        context['daily_sessions'] = teacher.get_daily_sessions(today)
        context['monthly_sessions'] = teacher.get_monthly_sessions(today.year, today.month)
        context['yearly_sessions'] = teacher.get_yearly_sessions(today.year)

        context['salary_year'] = salary_year
        context['salary_month'] = salary_month
        context['salary_period_date'] = period_date
        context['salary_period_label'] = f"{salary_year}/{salary_month:02d}"
        context['salary_period_is_current'] = (salary_year == today.year and salary_month == today.month)
        context['salary_amount'] = teacher.calculate_monthly_salary(salary_year, salary_month)
        context['monthly_salary'] = context['salary_amount']
        context['salary_status'] = teacher.get_salary_status(salary_year, salary_month)

        context['daily_attendance'] = TeacherAttendance.objects.filter(teacher=teacher, date=today).first()

        monthly_attendance = TeacherAttendance.objects.filter(
            teacher=teacher,
            date__year=today.year,
            date__month=today.month
        )

        context['monthly_stats'] = {
            'present_days': monthly_attendance.filter(status='present').count(),
            'absent_days': monthly_attendance.filter(status='absent').count(),
            'total_days': monthly_attendance.count(),
        }

        yearly_attendance = TeacherAttendance.objects.filter(
            teacher=teacher,
            date__year=today.year
        )

        context['yearly_stats'] = {
            'present_days': yearly_attendance.filter(status='present').count(),
            'absent_days': yearly_attendance.filter(status='absent').count(),
            'total_days': yearly_attendance.count(),
            'total_sessions': yearly_attendance.filter(status='present').aggregate(total=Sum('session_count'))['total'] or 0,
        }

        context['today'] = today
        return context
class TeacherDeleteView(LoginRequiredMixin, DeleteView):
    model = Teacher
    template_name = 'employ/teacher_confirm_delete.html'
    success_url = reverse_lazy('employ:teachers')

    def delete(self, request, *args, **kwargs):
        teacher = self.get_object()
        messages.success(request, f'تم حذف بيانات المعلم {teacher.full_name}.')
        return super().delete(request, *args, **kwargs)


def _employee_full_name(employee):
    if not employee:
        return ''
    name_attr = getattr(employee, 'full_name', None)
    if name_attr:
        return name_attr
    user = getattr(employee, 'user', None)
    if user:
        full_name = user.get_full_name()
        return full_name if full_name else user.get_username()
    return str(employee)


class PayEmployeeSalaryView(View):
    def post(self, request, pk):
        employee = get_object_or_404(Employee, pk=pk)

        def _sanitize_int(value, default, allowed=None):
            if value is None:
                return default
            cleaned = ''.join(ch for ch in str(value) if ch.isdigit())
            if cleaned:
                try:
                    numeric = int(cleaned)
                    if allowed and numeric not in allowed:
                        return default
                    return numeric
                except ValueError:
                    pass
            return default

        year = _sanitize_int(request.POST.get('year'), timezone.now().year)
        month = _sanitize_int(request.POST.get('month'), timezone.now().month, allowed=set(range(1, 13)))
        return_to_profile = request.POST.get('return_to_profile')

        salary_amount = employee.salary or Decimal('0')
        if salary_amount <= 0:
            messages.error(request, 'لا يمكن حساب راتب هذا الموظف.')
            if return_to_profile:
                return redirect('employ:employee_profile', pk=employee.pk)
            return redirect('accounts:employee_financial_profile', entity_type='employee', pk=employee.pk)

        if employee.get_salary_status(year, month):
            messages.warning(request, f'راتب { _employee_full_name(employee) } مسجل بالفعل لشهر {month:02d}/{year}.')
            if return_to_profile:
                return redirect('employ:employee_profile', pk=employee.pk)
            return redirect('accounts:employee_financial_profile', entity_type='employee', pk=employee.pk)

        display_name = _employee_full_name(employee)

        try:
            expense = ExpenseEntry.objects.create(
                date=timezone.now().date(),
                description=f'Salary - {display_name} ({month:02d}/{year}) [Employee #{employee.pk}]',
                category='SALARY',
                amount=salary_amount,
                payment_method='CASH',
                vendor=display_name or employee.user.get_username(),
                notes=f'Employee salary payment for {display_name} ({month:02d}/{year}) [Employee #{employee.pk}]',
                created_by=request.user,
                employee=employee
            )

            expense.create_journal_entry(request.user)

            messages.success(
                request,
                f'تم تسجيل راتب {display_name} ({month:02d}/{year}) بنجاح.'
            )
        except Exception as e:
            messages.error(request, f'حدث خطأ أثناء تسجيل الراتب: {e}')
            if return_to_profile:
                return redirect('employ:employee_profile', pk=employee.pk)
            return redirect('accounts:employee_financial_profile', entity_type='employee', pk=employee.pk)

        if return_to_profile:
            return redirect('employ:employee_profile', pk=employee.pk)
        return redirect('accounts:employee_financial_profile', entity_type='employee', pk=employee.pk)


class PayTeacherSalaryView(View):
    def post(self, request, pk):
        teacher = get_object_or_404(Teacher, pk=pk)

        def _sanitize_int(value, default, allowed=None):
            if value is None:
                return default
            cleaned = ''.join(ch for ch in str(value) if ch.isdigit())
            if cleaned:
                try:
                    numeric = int(cleaned)
                    if allowed and numeric not in allowed:
                        return default
                    return numeric
                except ValueError:
                    pass
            return default

        year = _sanitize_int(request.POST.get('year'), timezone.now().year)
        month = _sanitize_int(request.POST.get('month'), timezone.now().month, allowed=set(range(1, 13)))
        return_to_profile = request.POST.get('return_to_profile')

        calculated_salary = teacher.calculate_monthly_salary(year, month)

        if calculated_salary <= 0:
            messages.error(request, 'Unable to calculate salary for this teacher.')
            if return_to_profile:
                return redirect('employ:teacher_profile', pk=teacher.pk)
            return redirect('employ:salary_management')

        if teacher.get_salary_status(year, month):
            messages.warning(request, f'Salary for {teacher.full_name} is already recorded for {month:02d}/{year}.')
            if return_to_profile:
                return redirect('employ:teacher_profile', pk=teacher.pk)
            return redirect('employ:salary_management')

        try:
            expense = ExpenseEntry.objects.create(
                date=timezone.now().date(),
                description=f'Salary - {teacher.full_name} ({month:02d}/{year}) [Teacher #{teacher.pk}]',
                category='TEACHER_SALARY',
                amount=calculated_salary,
                payment_method='CASH',
                vendor=teacher.full_name,
                notes=f'Teacher salary payment for {teacher.full_name} ({month:02d}/{year}) [Teacher #{teacher.pk}]',
                created_by=request.user,
                teacher=teacher
            )

            expense.create_journal_entry(request.user)

            messages.success(
                request,
                f'Salary for {teacher.full_name} ({month:02d}/{year}) recorded successfully.'
            )
        except Exception as e:
            messages.error(request, f'تعذر تسجيل سداد السلفة: {e}')
            if return_to_profile:
                return redirect('employ:teacher_profile', pk=teacher.pk)
            return redirect('employ:salary_management')

        if return_to_profile:
            return redirect('employ:teacher_profile', pk=teacher.pk)
        return redirect('employ:salary_management')
