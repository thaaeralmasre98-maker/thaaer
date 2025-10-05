from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import (
    DetailView, ListView, CreateView, UpdateView, DeleteView, TemplateView, View
)
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.urls import reverse_lazy, reverse
from django.db.models import Sum, Q, Count
from django.http import JsonResponse, HttpResponse, Http404
from datetime import datetime, date
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_GET
from django.utils.decorators import method_decorator

from .models import (
    Account, JournalEntry, Transaction, StudentReceipt, ExpenseEntry, 
    AccountingPeriod, Budget, Course, Student, StudentEnrollment, EmployeeAdvance, 
    CostCenter, DiscountRule
)
from .forms import (
    AccountForm, JournalEntryForm, TransactionFormSet, StudentReceiptForm, ExpenseEntryForm,
    AccountingPeriodForm, BudgetForm, CourseForm, StudentForm, StudentEnrollmentForm, 
    EmployeeAdvanceForm, DiscountRuleForm
)

from students.models import Student as SProfile
from employ.models import Employee, Teacher


def _employee_display_name(employee):
    if not employee:
        return ''
    user = getattr(employee, 'user', None)
    if user:
        full_name = user.get_full_name()
        return full_name if full_name else user.get_username()
    return str(employee)


def _employee_name_variants(employee):
    variants = []
    display_name = _employee_display_name(employee)
    if display_name:
        variants.append(display_name)
    user = getattr(employee, 'user', None)
    if user:
        if user.username and user.username not in variants:
            variants.append(user.username)
        email = getattr(user, 'email', '')
        if email and email not in variants:
            variants.append(email)
    cleaned = []
    for value in variants:
        trimmed = value.strip()
        if trimmed and trimmed not in cleaned:
            cleaned.append(trimmed)
    return cleaned


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'accounts/dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        try:
            # Calculate key metrics safely
            asset_accounts = Account.objects.filter(account_type='ASSET', is_active=True)
            total_assets = sum(acc.get_net_balance() for acc in asset_accounts)
            
            liability_accounts = Account.objects.filter(account_type='LIABILITY', is_active=True)
            total_liabilities = sum(acc.get_net_balance() for acc in liability_accounts)
            
            equity_accounts = Account.objects.filter(account_type='EQUITY', is_active=True)
            total_equity = sum(acc.get_net_balance() for acc in equity_accounts)
            
            revenue_accounts = Account.objects.filter(account_type='REVENUE', is_active=True)
            total_revenue = sum(acc.get_net_balance() for acc in revenue_accounts)
            
            expense_accounts = Account.objects.filter(account_type='EXPENSE', is_active=True)
            total_expenses = sum(acc.get_net_balance() for acc in expense_accounts)
            
            # Get fund balance (cash + bank accounts)
            cash_accounts = Account.objects.filter(
                code__in=['1110', '1115'], is_active=True
            )
            fund_balance = sum(acc.get_net_balance() for acc in cash_accounts)
            
            # Get employee advances safely
            try:
                outstanding_advances = EmployeeAdvance.objects.filter(is_repaid=False)
                employee_advances = sum(adv.outstanding_amount for adv in outstanding_advances)
            except:
                employee_advances = Decimal('0.00')
            
            # Calculate financial ratios
            current_ratio = 0
            profit_margin = 0
            debt_ratio = 0
            working_capital = Decimal('0.00')
            
            if total_liabilities > 0:
                current_ratio = float(total_assets / total_liabilities) if total_liabilities > 0 else 0
                debt_ratio = float(total_liabilities / total_assets * 100) if total_assets > 0 else 0
            
            if total_revenue > 0:
                profit_margin = float((total_revenue - total_expenses) / total_revenue * 100)
            
            working_capital = total_assets - total_liabilities
            
            context.update({
                'total_assets': total_assets,
                'total_liabilities': total_liabilities,
                'total_equity': total_equity,
                'total_revenue': total_revenue,
                'total_expenses': total_expenses,
                'net_income': total_revenue - total_expenses,
                'recent_entries': JournalEntry.objects.select_related('created_by').order_by('-date', '-created_at')[:5],
                'account_count': Account.objects.filter(is_active=True).count(),
                'unposted_entries': JournalEntry.objects.filter(is_posted=False).count(),
                'current_ratio': current_ratio,
                'profit_margin': profit_margin,
                'debt_ratio': debt_ratio,
                'working_capital': working_capital,
                'fund_balance': fund_balance,
                'employee_advances': employee_advances,
                'total_courses': Course.objects.filter(is_active=True).count(),
                'total_students': SProfile.objects.filter(is_active=True).count(),
                'active_enrollments': StudentEnrollment.objects.filter(is_completed=False).count(),
            })
        except Exception as e:
            # Fallback values if calculations fail
            context.update({
                'total_assets': Decimal('0.00'),
                'total_liabilities': Decimal('0.00'),
                'total_equity': Decimal('0.00'),
                'total_revenue': Decimal('0.00'),
                'total_expenses': Decimal('0.00'),
                'net_income': Decimal('0.00'),
                'recent_entries': [],
                'account_count': 0,
                'unposted_entries': 0,
                'current_ratio': 0,
                'profit_margin': 0,
                'debt_ratio': 0,
                'working_capital': Decimal('0.00'),
                'fund_balance': Decimal('0.00'),
                'employee_advances': Decimal('0.00'),
                'total_courses': 0,
                'total_students': 0,
                'active_enrollments': 0,
                'error_message': str(e)
            })
        
        return context


class ChartOfAccountsView(LoginRequiredMixin, ListView):
    model = Account
    template_name = 'accounts/chart_of_accounts.html'
    context_object_name = 'accounts'
    
    def get_queryset(self):
        # Prefetch children (and one level deeper) so that rollup_balance
        # property doesn't cause N+1 queries in templates.
        # Avoid duplicating the same 'children' prefetch with different querysets.
        from django.db.models import Prefetch
        base = Account.objects.select_related('parent')
        nested_children = Prefetch(
            'children', queryset=Account.objects.select_related('parent').prefetch_related('children')
        )
        return base.prefetch_related(nested_children).filter(is_active=True).order_by('code')


class AccountCreateView(LoginRequiredMixin, CreateView):
    model = Account
    form_class = AccountForm
    template_name = 'accounts/account_form.html'
    success_url = reverse_lazy('accounts:chart_of_accounts')
    
    def form_valid(self, form):
        messages.success(self.request, 'تم إنشاء الحساب بنجاح / Account created successfully')
        return super().form_valid(form)


class AccountDetailView(LoginRequiredMixin, DetailView):
    model = Account
    template_name = 'accounts/account_detail.html'
    context_object_name = 'account'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        account = self.get_object()
        
        # Get recent transactions for this account
        context['recent_transactions'] = Transaction.objects.filter(
            account=account
        ).select_related('journal_entry').order_by('-journal_entry__date')[:10]
        
        return context


class AccountUpdateView(LoginRequiredMixin, UpdateView):
    model = Account
    form_class = AccountForm
    template_name = 'accounts/account_form.html'
    
    def form_valid(self, form):
        messages.success(self.request, 'تم تحديث الحساب بنجاح / Account updated successfully')
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse_lazy('accounts:account_detail', kwargs={'pk': self.object.pk})


class AccountDeleteView(LoginRequiredMixin, DeleteView):
    model = Account
    template_name = 'accounts/account_confirm_delete.html'
    success_url = reverse_lazy('accounts:chart_of_accounts')
    
    def delete(self, request, *args, **kwargs):
        messages.success(request, 'تم حذف الحساب بنجاح / Account deleted successfully')
        return super().delete(request, *args, **kwargs)


class JournalEntryListView(LoginRequiredMixin, ListView):
    model = JournalEntry
    template_name = 'accounts/journal_entry_list.html'
    context_object_name = 'journal_entries'
    paginate_by = 20
    
    def get_queryset(self):
        return JournalEntry.objects.select_related('created_by').order_by('-date', '-created_at')


class JournalEntryCreateView(LoginRequiredMixin, CreateView):
    model = JournalEntry
    form_class = JournalEntryForm
    template_name = 'accounts/journal_entry_form.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['transaction_formset'] = TransactionFormSet(self.request.POST)
        else:
            context['transaction_formset'] = TransactionFormSet()
        return context
    
    def form_valid(self, form):
        context = self.get_context_data()
        transaction_formset = context['transaction_formset']
        
        if transaction_formset.is_valid():
            # Calculate total amount
            total_debits = sum(
                f.cleaned_data.get('amount', Decimal('0.00'))
                for f in transaction_formset.forms
                if f.cleaned_data.get('is_debit', False) and not f.cleaned_data.get('DELETE', False)
            )
            total_credits = sum(
                f.cleaned_data.get('amount', Decimal('0.00'))
                for f in transaction_formset.forms
                if not f.cleaned_data.get('is_debit', False) and not f.cleaned_data.get('DELETE', False)
            )
            
            if total_debits != total_credits:
                messages.error(self.request, 'إجمالي المدين يجب أن يساوي إجمالي الدائن / Total debits must equal total credits')
                return self.form_invalid(form)
            
            form.instance.created_by = self.request.user
            form.instance.total_amount = total_debits
            self.object = form.save()
            
            transaction_formset.instance = self.object
            transaction_formset.save()
            
            messages.success(self.request, 'تم إنشاء قيد اليومية بنجاح / Journal entry created successfully')
            return redirect(self.object.get_absolute_url())
        else:
            return self.form_invalid(form)


class JournalEntryDetailView(LoginRequiredMixin, DetailView):
    model = JournalEntry
    template_name = 'accounts/journal_entry_detail.html'
    context_object_name = 'journal_entry'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['transactions'] = self.object.transactions.select_related('account').all()
        return context


class JournalEntryUpdateView(LoginRequiredMixin, UpdateView):
    model = JournalEntry
    form_class = JournalEntryForm
    template_name = 'accounts/journal_entry_form.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['transaction_formset'] = TransactionFormSet(
                self.request.POST, instance=self.object
            )
        else:
            context['transaction_formset'] = TransactionFormSet(instance=self.object)
        return context
    
    def form_valid(self, form):
        if self.object.is_posted:
            messages.error(self.request, 'لا يمكن تعديل قيد مرحل / Cannot edit posted journal entry')
            return redirect(self.object.get_absolute_url())
        
        context = self.get_context_data()
        transaction_formset = context['transaction_formset']
        
        if transaction_formset.is_valid():
            # Validate balance
            total_debits = sum(
                f.cleaned_data.get('amount', Decimal('0.00'))
                for f in transaction_formset.forms
                if f.cleaned_data.get('is_debit', False) and not f.cleaned_data.get('DELETE', False)
            )
            total_credits = sum(
                f.cleaned_data.get('amount', Decimal('0.00'))
                for f in transaction_formset.forms
                if not f.cleaned_data.get('is_debit', False) and not f.cleaned_data.get('DELETE', False)
            )
            
            if total_debits != total_credits:
                messages.error(self.request, 'إجمالي المدين يجب أن يساوي إجمالي الدائن / Total debits must equal total credits')
                return self.form_invalid(form)
            
            form.instance.total_amount = total_debits
            self.object = form.save()
            transaction_formset.save()
            
            messages.success(self.request, 'تم تحديث قيد اليومية بنجاح / Journal entry updated successfully')
            return redirect(self.object.get_absolute_url())
        else:
            return self.form_invalid(form)


class PostJournalEntryView(LoginRequiredMixin, View):
    def post(self, request, pk):
        journal_entry = get_object_or_404(JournalEntry, pk=pk)
        
        try:
            journal_entry.post_entry(request.user)
            messages.success(request, 'تم ترحيل قيد اليومية بنجاح / Journal entry posted successfully')
            
            # Refresh account tree balances after posting
            root_accounts = Account.objects.filter(parent=None)
            for root_account in root_accounts:
                try:
                    root_account.recalculate_tree_balances()
                except:
                    pass  # Skip if recalculation fails
                
        except ValueError as e:
            messages.error(request, f'خطأ في الترحيل / Posting error: {str(e)}')
        
        return redirect(journal_entry.get_absolute_url())


class ReverseJournalEntryView(LoginRequiredMixin, View):
    def post(self, request, pk):
        journal_entry = get_object_or_404(JournalEntry, pk=pk)
        
        try:
            reversing_entry = journal_entry.reverse_entry(
                user=request.user,
                description=f"Reversal of {journal_entry.reference}"
            )
            messages.success(
                request, 
                f'تم عكس القيد بنجاح / Journal entry reversed successfully. New entry: {reversing_entry.reference}'
            )
            return redirect(reversing_entry.get_absolute_url())
        except ValueError as e:
            messages.error(request, f'خطأ في عكس القيد / Reversal error: {str(e)}')
            return redirect(journal_entry.get_absolute_url())


class ReportsView(LoginRequiredMixin, TemplateView):
    template_name = 'accounts/reports.html'


class TrialBalanceView(LoginRequiredMixin, TemplateView):
    template_name = 'accounts/trial_balance.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get all accounts with transactions
        accounts = Account.objects.filter(is_active=True).order_by('code')
        trial_balance_data = []
        total_debits = Decimal('0.00')
        total_credits = Decimal('0.00')
        
        for account in accounts:
            debit_balance = account.get_debit_balance()
            credit_balance = account.get_credit_balance()
            net_balance = account.get_net_balance()
            
            if debit_balance > 0 or credit_balance > 0:
                if net_balance > 0:
                    if account.account_type in ['ASSET', 'EXPENSE']:
                        debit_amount = net_balance
                        credit_amount = Decimal('0.00')
                    else:
                        debit_amount = Decimal('0.00')
                        credit_amount = net_balance
                else:
                    if account.account_type in ['ASSET', 'EXPENSE']:
                        debit_amount = Decimal('0.00')
                        credit_amount = abs(net_balance)
                    else:
                        debit_amount = abs(net_balance)
                        credit_amount = Decimal('0.00')
                
                trial_balance_data.append({
                    'account': account,
                    'debit_amount': debit_amount,
                    'credit_amount': credit_amount,
                })
                
                total_debits += debit_amount
                total_credits += credit_amount
        
        context.update({
            'trial_balance_data': trial_balance_data,
            'total_debits': total_debits,
            'total_credits': total_credits,
            'is_balanced': total_debits == total_credits,
        })
        
        return context


class IncomeStatementView(LoginRequiredMixin, TemplateView):
    template_name = 'accounts/income_statement.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get revenue and expense accounts
        revenue_accounts = Account.objects.filter(
            account_type='REVENUE', is_active=True
        ).order_by('code')
        expense_accounts = Account.objects.filter(
            account_type='EXPENSE', is_active=True
        ).order_by('code')
        
        total_revenue = sum(acc.get_net_balance() for acc in revenue_accounts)
        total_expenses = sum(acc.get_net_balance() for acc in expense_accounts)
        net_income = total_revenue - total_expenses
        
        context.update({
            'revenue_accounts': revenue_accounts,
            'expense_accounts': expense_accounts,
            'total_revenue': total_revenue,
            'total_expenses': total_expenses,
            'net_income': net_income,
        })
        
        return context


class BalanceSheetView(LoginRequiredMixin, TemplateView):
    template_name = 'accounts/balance_sheet.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get balance sheet accounts
        asset_accounts = Account.objects.filter(
            account_type='ASSET', is_active=True
        ).order_by('code')
        liability_accounts = Account.objects.filter(
            account_type='LIABILITY', is_active=True
        ).order_by('code')
        equity_accounts = Account.objects.filter(
            account_type='EQUITY', is_active=True
        ).order_by('code')
        
        total_assets = sum(acc.get_net_balance() for acc in asset_accounts)
        total_liabilities = sum(acc.get_net_balance() for acc in liability_accounts)
        total_equity = sum(acc.get_net_balance() for acc in equity_accounts)
        
        context.update({
            'asset_accounts': asset_accounts,
            'liability_accounts': liability_accounts,
            'equity_accounts': equity_accounts,
            'total_assets': total_assets,
            'total_liabilities': total_liabilities,
            'total_equity': total_equity,
        })
        
        return context


class LedgerView(LoginRequiredMixin, TemplateView):
    template_name = 'accounts/ledger.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        account_id = kwargs.get('account_id')
        account = get_object_or_404(Account, id=account_id)
        
        # Get all transactions for this account and its descendants
        transactions = account.transactions_with_descendants().select_related('journal_entry').order_by('journal_entry__date', 'journal_entry__created_at')
        
        # Calculate running balance
        running_balance = Decimal('0.00')
        transaction_data = []
        
        for transaction in transactions:
            if transaction.is_debit:
                if account.account_type in ['ASSET', 'EXPENSE']:
                    running_balance += transaction.amount
                else:
                    running_balance -= transaction.amount
            else:  # Credit
                if account.account_type in ['LIABILITY', 'EQUITY', 'REVENUE']:
                    running_balance += transaction.amount
                else:
                    running_balance -= transaction.amount
            
            transaction_data.append({
                'transaction': transaction,
                'running_balance': running_balance,
            })
        
        context.update({
            'account': account,
            'transaction_data': transaction_data,
        })
        
        return context


class StudentReceiptCreateView(LoginRequiredMixin, CreateView):
    model = StudentReceipt
    form_class = StudentReceiptForm
    template_name = 'accounts/student_receipt_form.html'
    
    def form_valid(self, form):
        form.instance.created_by = self.request.user
        
        # CRITICAL: Ensure student has AR account before creating receipt
        if form.instance.student_profile:
            try:
                ar_account = form.instance.student_profile.ar_account
                print(f"Student AR Account ready: {ar_account.code}")
            except Exception as e:
                messages.error(self.request, f'خطأ في إنشاء حساب الطالب: {str(e)}')
                return self.form_invalid(form)
        
        # Handle enrollment for accrual accounting
        if form.instance.student_profile and form.instance.course:
            enrollment, created = StudentEnrollment.objects.get_or_create(
                student=form.instance.student_profile,
                course=form.instance.course,
                defaults={
                    'enrollment_date': form.instance.date,
                    'total_amount': form.instance.course.price,
                    'discount_percent': form.instance.student_profile.discount_percent or Decimal('0'),
                    'discount_amount': form.instance.student_profile.discount_amount or Decimal('0'),
                    'payment_method': form.instance.payment_method
                }
            )
            form.instance.enrollment = enrollment
            
            # Create enrollment entry if new
            if created:
                try:
                    enrollment.create_accrual_enrollment_entry(self.request.user)
                    print(f"Created enrollment entry for {enrollment}")
                except Exception as e:
                    messages.warning(self.request, f'تحذير: لم يتم إنشاء قيد التسجيل: {str(e)}')
        
        response = super().form_valid(form)
        
        # Create accrual accounting journal entry
        try:
            self.object.create_accrual_journal_entry(self.request.user)
            messages.success(
                self.request, 
                f'تم إنشاء إيصال الطالب والقيود المحاسبية بنجاح / Student receipt and accounting entries created successfully'
            )
            print(f"Successfully created journal entry for receipt {self.object.receipt_number}")
        except Exception as e:
            print(f"Error creating journal entry: {e}")
            messages.error(self.request, f'خطأ في إنشاء القيد المحاسبي / Error creating journal entry: {str(e)}')
        
        return response
    
    def get_success_url(self):
        return reverse_lazy('accounts:student_receipt_detail', kwargs={'pk': self.object.pk})


class StudentReceiptDetailView(LoginRequiredMixin, DetailView):
    model = StudentReceipt
    template_name = 'accounts/student_receipt_detail.html'
    context_object_name = 'receipt'


class ExpenseCreateView(LoginRequiredMixin, CreateView):
    model = ExpenseEntry
    form_class = ExpenseEntryForm
    template_name = 'accounts/expense_form.html'
    
    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        
        # Create automatic journal entry
        try:
            self.object.create_journal_entry(self.request.user)
            messages.success(
                self.request, 
                f'تم تسجيل المصروف وقيد اليومية بنجاح / Expense and journal entry created successfully'
            )
        except Exception as e:
            messages.error(self.request, f'خطأ في إنشاء القيد المحاسبي / Error creating journal entry: {str(e)}')
        
        return response
    
    def get_success_url(self):
        return reverse_lazy('accounts:expense_detail', kwargs={'pk': self.object.pk})


class ExpenseDetailView(LoginRequiredMixin, DetailView):
    model = ExpenseEntry
    template_name = 'accounts/expense_detail.html'
    context_object_name = 'expense'


class ReceiptsExpensesView(LoginRequiredMixin, TemplateView):
    template_name = 'accounts/receipts_expenses.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get current cash balance
        cash_account = Account.objects.filter(code='1110').first()
        cash_balance = cash_account.get_net_balance() if cash_account else Decimal('0.00')
        
        # Get recent receipts and expenses
        recent_receipts = StudentReceipt.objects.select_related('created_by')[:10]
        recent_expenses = ExpenseEntry.objects.select_related('created_by')[:10]
        
        # Get today's totals
        today = timezone.now().date()
        today_receipts_total = StudentReceipt.objects.filter(date=today).aggregate(
            total=Sum('amount'))['total'] or Decimal('0.00')
        today_expenses_total = ExpenseEntry.objects.filter(date=today).aggregate(
            total=Sum('amount'))['total'] or Decimal('0.00')
        
        context.update({
            'cash_balance': cash_balance,
            'recent_receipts': recent_receipts,
            'recent_expenses': recent_expenses,
            'today_receipts_total': today_receipts_total,
            'today_expenses_total': today_expenses_total,
            'net_today': today_receipts_total - today_expenses_total,
            'receipt_form': StudentReceiptForm(),
            'expense_form': ExpenseEntryForm(),
        })
        
        return context


class CourseListView(LoginRequiredMixin, ListView):
    model = Course
    template_name = 'accounts/course_list.html'
    context_object_name = 'courses'
    
    def get_queryset(self):
        return Course.objects.filter(is_active=True).order_by('name')


class CourseCreateView(LoginRequiredMixin, CreateView):
    model = Course
    form_class = CourseForm
    template_name = 'accounts/course_form.html'
    success_url = reverse_lazy('accounts:course_list')
    
    def form_valid(self, form):
        messages.success(self.request, 'تم إنشاء الدورة بنجاح / Course created successfully')
        return super().form_valid(form)


class CourseDetailView(LoginRequiredMixin, DetailView):
    model = Course
    template_name = 'accounts/course_detail.html'
    context_object_name = 'course'


class CourseUpdateView(LoginRequiredMixin, UpdateView):
    model = Course
    form_class = CourseForm
    template_name = 'accounts/course_form.html'
    
    def form_valid(self, form):
        messages.success(self.request, 'تم تحديث الدورة بنجاح / Course updated successfully')
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse_lazy('accounts:course_detail', kwargs={'pk': self.object.pk})


class EmployeeAdvanceListView(LoginRequiredMixin, ListView):
    model = EmployeeAdvance
    template_name = 'accounts/advance_list.html'
    context_object_name = 'advances'
    
    def get_queryset(self):
        return EmployeeAdvance.objects.select_related('created_by').order_by('-date')


class EmployeeAdvanceCreateView(LoginRequiredMixin, CreateView):
    model = EmployeeAdvance
    form_class = EmployeeAdvanceForm
    template_name = 'accounts/advance_form.html'
    success_url = reverse_lazy('accounts:advance_list')
    
    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        
        # Create journal entry
        try:
            self.object.create_advance_entry(self.request.user)
            messages.success(
                self.request, 
                'تم إنشاء السلفة والقيد المحاسبي بنجاح / Employee advance and journal entry created successfully'
            )
        except Exception as e:
            messages.error(self.request, f'خطأ في إنشاء القيد المحاسبي / Error creating journal entry: {str(e)}')
        
        # Refresh account tree balances
        root_accounts = Account.objects.filter(parent=None)
        for root_account in root_accounts:
            try:
                root_account.recalculate_tree_balances()
            except:
                pass
        
        return response


class EmployeeAdvanceDetailView(LoginRequiredMixin, DetailView):
    model = EmployeeAdvance
    template_name = 'accounts/advance_detail.html'
    context_object_name = 'advance'


class EmployeeFinancialOverviewView(LoginRequiredMixin, TemplateView):
    template_name = 'accounts/employee_financial_overview.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        employees = Employee.objects.select_related('user').order_by('user__first_name', 'user__last_name', 'user__username')
        employee_rows = []
        for employee in employees:
            salary_qs = ExpenseEntry.objects.filter(employee=employee).order_by('-date', '-created_at')
            total_paid = salary_qs.aggregate(total=Sum('amount'))['total'] or Decimal('0')
            last_payment = salary_qs.first()
            variants = _employee_name_variants(employee)
            filters = Q(employee=employee)
            for variant in variants:
                filters |= Q(employee_name__iexact=variant)
            advances = EmployeeAdvance.objects.filter(filters).order_by('-date')
            outstanding_total = sum((adv.outstanding_amount for adv in advances), Decimal('0'))
            employee_rows.append({
                'object': employee,
                'display_name': _employee_display_name(employee),
                'position': employee.get_position_display(),
                'monthly_salary': employee.salary,
                'total_paid': total_paid,
                'outstanding_advances': outstanding_total,
                'last_payment': last_payment,
                'detail_url': reverse('accounts:employee_financial_profile', kwargs={'entity_type': 'employee', 'pk': employee.pk}),
            })

        teachers = Teacher.objects.order_by('full_name')
        teacher_rows = []
        for teacher in teachers:
            salary_qs = ExpenseEntry.objects.filter(teacher=teacher).order_by('-date', '-created_at')
            total_paid = salary_qs.aggregate(total=Sum('amount'))['total'] or Decimal('0')
            last_payment = salary_qs.first()
            teacher_rows.append({
                'object': teacher,
                'display_name': teacher.full_name,
                'monthly_salary': teacher.calculate_monthly_salary(),
                'total_paid': total_paid,
                'last_payment': last_payment,
                'detail_url': reverse('accounts:employee_financial_profile', kwargs={'entity_type': 'teacher', 'pk': teacher.pk}),
            })

        context.update({
            'employee_rows': employee_rows,
            'teacher_rows': teacher_rows,
            'salary_parent_code': '5100',
        })
        return context


class EmployeeFinancialProfileView(LoginRequiredMixin, TemplateView):
    template_name = 'accounts/employee_financial_profile.html'

    def dispatch(self, request, *args, **kwargs):
        self.entity_type = kwargs.get('entity_type')
        if self.entity_type not in {'employee', 'teacher'}:
            raise Http404('Unsupported profile type')
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        pk = self.kwargs.get('pk')
        if self.entity_type == 'employee':
            entity = get_object_or_404(Employee.objects.select_related('user'), pk=pk)
            salary_qs = ExpenseEntry.objects.filter(employee=entity).select_related('journal_entry').prefetch_related('journal_entry__transactions__account').order_by('-date', '-created_at')
            monthly_salary = entity.salary
            display_name = _employee_display_name(entity)
            salary_account_code = '5100'
            variants = _employee_name_variants(entity)
            filters = Q(employee=entity)
            for variant in variants:
                filters |= Q(employee_name__iexact=variant)
            advances = EmployeeAdvance.objects.filter(filters).order_by('-date')
        else:
            entity = get_object_or_404(Teacher, pk=pk)
            salary_qs = ExpenseEntry.objects.filter(teacher=entity).select_related('journal_entry').prefetch_related('journal_entry__transactions__account').order_by('-date', '-created_at')
            monthly_salary = entity.calculate_monthly_salary()
            display_name = entity.full_name
            salary_account_code = '5101'
            advances = EmployeeAdvance.objects.none()

        salary_total = salary_qs.aggregate(total=Sum('amount'))['total'] or Decimal('0')
        last_payment = salary_qs.first()
        salary_entries = []
        for entry in salary_qs:
            debit_account = None
            if entry.journal_entry:
                for tx in entry.journal_entry.transactions.all():
                    if tx.is_debit:
                        debit_account = tx.account
                        break
            salary_entries.append({
                'entry': entry,
                'account': debit_account,
            })

        advance_total = advances.aggregate(total=Sum('amount'))['total'] or Decimal('0')
        outstanding_total = sum((adv.outstanding_amount for adv in advances), Decimal('0'))

        context.update({
            'entity_type': self.entity_type,
            'entity': entity,
            'employee': entity if self.entity_type == 'employee' else None,
            'display_name': display_name,
            'monthly_salary': monthly_salary,
            'salary_total': salary_total,
            'last_payment': last_payment,
            'salary_entries': salary_entries,
            'advances': advances,
            'advance_total': advance_total,
            'advance_outstanding_total': outstanding_total,
            'salary_account_code': salary_account_code,
            'salary_parent_code': '5100',
            'back_url': reverse('accounts:employee_financial_overview'),
        })
        return context


class OutstandingCoursesView(LoginRequiredMixin, TemplateView):
    template_name = 'accounts/outstanding_courses.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        courses = Course.objects.filter(is_active=True).order_by('name')
        course_data = []
        
        for course in courses:
            # Get all students with receipts for this course
            enrolled_students = SProfile.objects.filter(
                receipts__course=course
            ).distinct()
            
            students_count = enrolled_students.count()
            fully_paid_count = 0
            not_fully_paid_count = 0
            outstanding_total = Decimal('0')
            
            for student in enrolled_students:
                # Calculate net due after discount
                course_price = course.price or Decimal('0')
                discount_percent = student.discount_percent or Decimal('0')
                discount_amount = student.discount_amount or Decimal('0')
                
                after_percent = course_price - (course_price * discount_percent / Decimal('100'))
                net_due = max(Decimal('0'), after_percent - discount_amount)
                
                # Calculate total paid
                paid_total = StudentReceipt.objects.filter(
                    student_profile=student,
                    course=course
                ).aggregate(total=Sum('paid_amount'))['total'] or Decimal('0')
                
                remaining = net_due - paid_total
                
                if remaining <= Decimal('0'):
                    fully_paid_count += 1
                else:
                    not_fully_paid_count += 1
                    outstanding_total += remaining
            
            # Include ALL courses
            course_data.append({
                'course': course,
                'students_count': students_count,
                'fully_paid': fully_paid_count,
                'not_fully_paid': not_fully_paid_count,
                'outstanding_total': outstanding_total
            })
        
        context['course_data'] = course_data
        return context


class OutstandingCourseStudentsView(LoginRequiredMixin, TemplateView):
    template_name = 'accounts/outstanding_course_students.html'
    
    def get_context_data(self, course_id=None, **kwargs):
        context = super().get_context_data(**kwargs)
        course = get_object_or_404(Course, pk=course_id)
        
        # Get all students with receipts for this course
        enrolled_students = SProfile.objects.filter(
            receipts__course=course
        ).distinct()
        
        student_data = []
        
        for student in enrolled_students:
            # Calculate net due after discount
            course_price = course.price or Decimal('0')
            discount_percent = student.discount_percent or Decimal('0')
            discount_amount = student.discount_amount or Decimal('0')
            
            after_percent = course_price - (course_price * discount_percent / Decimal('100'))
            net_due = max(Decimal('0'), after_percent - discount_amount)
            
            # Calculate total paid
            paid_total = StudentReceipt.objects.filter(
                student_profile=student,
                course=course
            ).aggregate(total=Sum('paid_amount'))['total'] or Decimal('0')
            
            remaining = net_due - paid_total
            
            # Only include students with outstanding balance
            if remaining > Decimal('0'):
                student_data.append({
                    'student': student,
                    'course_price': course_price,
                    'net_due': net_due,
                    'paid_total': paid_total,
                    'remaining': remaining
                })
        
        context.update({
            'course': course,
            'student_data': student_data
        })
        
        return context


class BudgetListView(LoginRequiredMixin, ListView):
    model = Budget
    template_name = 'accounts/budget_list.html'
    context_object_name = 'budgets'
    
    def get_queryset(self):
        return Budget.objects.select_related('account', 'period').all()
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Calculate budget summary
        budgets = self.get_queryset()
        total_budgeted = sum(b.budgeted_amount for b in budgets)
        total_actual = sum(b.actual_amount for b in budgets)
        total_variance = total_actual - total_budgeted
        
        context.update({
            'total_budgeted': total_budgeted,
            'total_actual': total_actual,
            'total_variance': total_variance,
        })
        
        return context


class BudgetCreateView(LoginRequiredMixin, CreateView):
    model = Budget
    form_class = BudgetForm
    template_name = 'accounts/budget_form.html'
    success_url = reverse_lazy('accounts:budget_list')
    
    def form_valid(self, form):
        messages.success(self.request, 'تم إنشاء الميزانية بنجاح / Budget created successfully')
        return super().form_valid(form)


class BudgetUpdateView(LoginRequiredMixin, UpdateView):
    model = Budget
    form_class = BudgetForm
    template_name = 'accounts/budget_form.html'
    success_url = reverse_lazy('accounts:budget_list')
    
    def form_valid(self, form):
        messages.success(self.request, 'تم تحديث الميزانية بنجاح / Budget updated successfully')
        return super().form_valid(form)


class BudgetDetailView(LoginRequiredMixin, DetailView):
    model = Budget
    template_name = 'accounts/budget_detail.html'
    context_object_name = 'budget'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        budget = self.get_object()
        
        # Calculate actual amount from transactions
        actual_amount = Transaction.objects.filter(
            account=budget.account,
            journal_entry__date__range=[budget.period.start_date, budget.period.end_date],
            journal_entry__is_posted=True
        ).aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0.00')
        
        # Update actual amount
        budget.actual_amount = actual_amount
        budget.variance = budget.calculate_variance()
        budget.save()
        
        context['budget'] = budget
        return context


class AccountingPeriodListView(LoginRequiredMixin, ListView):
    model = AccountingPeriod
    template_name = 'accounts/period_list.html'
    context_object_name = 'periods'
    
    def get_queryset(self):
        return AccountingPeriod.objects.all().order_by('-start_date')


class AccountingPeriodCreateView(LoginRequiredMixin, CreateView):
    model = AccountingPeriod
    form_class = AccountingPeriodForm
    template_name = 'accounts/period_form.html'
    success_url = reverse_lazy('accounts:period_list')
    
    def form_valid(self, form):
        messages.success(self.request, 'تم إنشاء الفترة المحاسبية بنجاح / Accounting period created successfully')
        return super().form_valid(form)


class AccountingPeriodUpdateView(LoginRequiredMixin, UpdateView):
    model = AccountingPeriod
    form_class = AccountingPeriodForm
    template_name = 'accounts/period_form.html'
    success_url = reverse_lazy('accounts:period_list')
    
    def form_valid(self, form):
        if self.object.is_closed:
            messages.error(self.request, 'لا يمكن تعديل فترة مقفلة / Cannot edit closed period')
            return redirect(self.success_url)
        messages.success(self.request, 'تم تحديث الفترة المحاسبية بنجاح / Accounting period updated successfully')
        return super().form_valid(form)


class AccountingPeriodDetailView(LoginRequiredMixin, DetailView):
    model = AccountingPeriod
    template_name = 'accounts/period_detail.html'
    context_object_name = 'period'


class ClosePeriodView(LoginRequiredMixin, View):
    def post(self, request, pk):
        period = get_object_or_404(AccountingPeriod, pk=pk)
        
        if period.is_closed:
            messages.error(request, 'الفترة مقفلة بالفعل / Period is already closed')
        else:
            period.is_closed = True
            period.closed_at = timezone.now()
            period.closed_by = request.user
            period.save()
            messages.success(request, 'تم إقفال الفترة المحاسبية بنجاح / Accounting period closed successfully')
        
        return redirect('accounts:period_list')


class CostCenterListView(LoginRequiredMixin, ListView):
    model = CostCenter
    template_name = 'accounts/cost_center_list.html'
    context_object_name = 'cost_centers'
    
    def get_queryset(self):
        return CostCenter.objects.all().order_by('code')


class CostCenterCreateView(LoginRequiredMixin, CreateView):
    model = CostCenter
    fields = ['code', 'name', 'name_ar', 'description', 'is_active']
    template_name = 'accounts/cost_center_form.html'
    success_url = reverse_lazy('accounts:cost_center_list')


class CostCenterUpdateView(LoginRequiredMixin, UpdateView):
    model = CostCenter
    fields = ['code', 'name', 'name_ar', 'description', 'is_active']
    template_name = 'accounts/cost_center_form.html'
    success_url = reverse_lazy('accounts:cost_center_list')


# Discount Rule Management Views
class DiscountRuleListView(LoginRequiredMixin, ListView):
    model = DiscountRule
    template_name = 'accounts/discount_rule_list.html'
    context_object_name = 'discount_rules'
    
    def get_queryset(self):
        return DiscountRule.objects.all().order_by('reason')


class DiscountRuleCreateView(LoginRequiredMixin, CreateView):
    model = DiscountRule
    form_class = DiscountRuleForm
    template_name = 'accounts/discount_rule_form.html'
    success_url = reverse_lazy('accounts:discount_rule_list')
    
    def form_valid(self, form):
        messages.success(self.request, 'تم إنشاء قاعدة الحسم بنجاح / Discount rule created successfully')
        return super().form_valid(form)


class DiscountRuleDetailView(LoginRequiredMixin, DetailView):
    model = DiscountRule
    template_name = 'accounts/discount_rule_detail.html'
    context_object_name = 'object'


class DiscountRuleUpdateView(LoginRequiredMixin, UpdateView):
    model = DiscountRule
    form_class = DiscountRuleForm
    template_name = 'accounts/discount_rule_form.html'
    
    def form_valid(self, form):
        messages.success(self.request, 'تم تحديث قاعدة الحسم بنجاح / Discount rule updated successfully')
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse_lazy('accounts:discount_rule_detail', kwargs={'pk': self.object.pk})


class DiscountRuleDeleteView(LoginRequiredMixin, DeleteView):
    model = DiscountRule
    template_name = 'accounts/discount_rule_delete.html'
    success_url = reverse_lazy('accounts:discount_rule_list')
    
    def delete(self, request, *args, **kwargs):
        messages.success(request, 'تم حذف قاعدة الحسم بنجاح / Discount rule deleted successfully')
        return super().delete(request, *args, **kwargs)


# AJAX Views
@require_GET
def ajax_course_price(request, pk):
    course = get_object_or_404(Course, pk=pk)
    return JsonResponse({'price': float(course.price)})


@require_GET
def ajax_discount_rule(request, reason):
    try:
        discount_rule = DiscountRule.objects.get(reason=reason, is_active=True)
        return JsonResponse({
            'success': True,
            'discount_percent': float(discount_rule.discount_percent),
            'discount_amount': float(discount_rule.discount_amount),
            'description': discount_rule.description
        })
    except DiscountRule.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Discount rule not found'
        })


@login_required
def student_receipt_print(request, pk):
    receipt = get_object_or_404(StudentReceipt, pk=pk)
    
    # Calculate totals for print view
    course_price = receipt.course.price or Decimal('0') if receipt.course else receipt.amount or Decimal('0')
    
    # Calculate net due and paid total
    if receipt.student_profile and receipt.course:
        # Use student's default discounts
        discount_percent = receipt.student_profile.discount_percent or Decimal('0')
        discount_amount = receipt.student_profile.discount_amount or Decimal('0')
        
        after_percent = course_price - (course_price * discount_percent / Decimal('100'))
        net_due = max(Decimal('0'), after_percent - discount_amount)
        
        # Calculate paid total including this receipt
        paid_total = StudentReceipt.objects.filter(
            student_profile=receipt.student_profile,
            course=receipt.course,
            date__lte=receipt.date
        ).aggregate(total=Sum('paid_amount'))['total'] or Decimal('0')
    else:
        # Fallback for legacy receipts
        net_due = receipt.net_amount or receipt.amount or Decimal('0')
        paid_total = receipt.paid_amount or Decimal('0')
        discount_percent = receipt.discount_percent or Decimal('0')
        discount_amount = receipt.discount_amount or Decimal('0')
    
    remaining = max(Decimal('0'), net_due - paid_total)
    
    return render(request, 'accounts/student_receipt_print.html', {
        'receipt': receipt, 
        'course_price': course_price,
        'net_due': net_due,
        'paid_total': paid_total, 
        'remaining': remaining,
        'discount_percent': discount_percent,
        'discount_amount': discount_amount
    })


# Additional actions and exports

class EnrollmentWithdrawView(LoginRequiredMixin, View):
    """POST /accounts/enrollments/<student_id>/withdraw/ with JSON {course_id, refund_amount?}"""
    def post(self, request, student_id):
        import json
        try:
            payload = json.loads(request.body.decode('utf-8'))
        except Exception:
            payload = request.POST
        course_id = payload.get('course_id')
        refund_str = payload.get('refund_amount')
        refund_amt = None
        if refund_str not in (None, '', 'null'):
            try:
                refund_amt = Decimal(str(refund_str))
            except Exception:
                refund_amt = None

        student = get_object_or_404(Student, pk=student_id)
        enrollment = get_object_or_404(StudentEnrollment, student=student, course_id=course_id)

        try:
            je = enrollment.withdraw(user=request.user, refund_amount=refund_amt)
            if request.headers.get('Accept') == 'application/json' or request.is_ajax():
                return JsonResponse({'ok': True, 'journal_entry_id': je.id})
            messages.success(request, "تم سحب الطالب وإنشاء قيد الإرجاع/إلغاء الذمم.")
        except Exception as e:
            if request.headers.get('Accept') == 'application/json' or request.is_ajax():
                return JsonResponse({'ok': False, 'error': str(e)}, status=400)
            messages.error(request, f"فشل سحب الطالب: {e}")
        # Redirect fallback
        return redirect(reverse_lazy('students:student_profile', kwargs={'pk': student.id}))


class TrialBalanceExportExcelView(LoginRequiredMixin, View):
    def get(self, request):
        accounts = Account.objects.filter(is_active=True).order_by('code')
        rows = []
        for a in accounts:
            net = a.get_net_balance()
            rows.append({'Code': a.code, 'Name': a.display_name, 'Type': a.account_type, 'Net': float(net)})
        import pandas as pd
        df = pd.DataFrame(rows)
        resp = HttpResponse(content_type='application/vnd.ms-excel')
        resp['Content-Disposition'] = 'attachment; filename="trial_balance.xlsx"'
        df.to_excel(resp, index=False, sheet_name='TrialBalance')
        return resp


class IncomeStatementExportExcelView(LoginRequiredMixin, View):
    def get(self, request):
        rev = Account.objects.filter(account_type='REVENUE', is_active=True).order_by('code')
        exp = Account.objects.filter(account_type='EXPENSE', is_active=True).order_by('code')
        rows = [{'Section': 'Revenue', 'Code': a.code, 'Name': a.display_name, 'Amount': float(a.get_net_balance())} for a in rev]
        rows += [{'Section': 'Expense', 'Code': a.code, 'Name': a.display_name, 'Amount': float(a.get_net_balance())} for a in exp]
        import pandas as pd
        df = pd.DataFrame(rows)
        resp = HttpResponse(content_type='application/vnd.ms-excel')
        resp['Content-Disposition'] = 'attachment; filename="income_statement.xlsx"'
        df.to_excel(resp, index=False, sheet_name='IncomeStatement')
        return resp


class BalanceSheetExportExcelView(LoginRequiredMixin, View):
    def get(self, request):
        assets = Account.objects.filter(account_type='ASSET', is_active=True).order_by('code')
        liab = Account.objects.filter(account_type='LIABILITY', is_active=True).order_by('code')
        eq = Account.objects.filter(account_type='EQUITY', is_active=True).order_by('code')
        rows = []
        for a in assets: rows.append({'Section':'Assets','Code':a.code,'Name':a.display_name,'Amount':float(a.get_net_balance())})
        for a in liab: rows.append({'Section':'Liabilities','Code':a.code,'Name':a.display_name,'Amount':float(a.get_net_balance())})
        for a in eq: rows.append({'Section':'Equity','Code':a.code,'Name':a.display_name,'Amount':float(a.get_net_balance())})
        import pandas as pd
        df = pd.DataFrame(rows)
        resp = HttpResponse(content_type='application/vnd.ms-excel')
        resp['Content-Disposition'] = 'attachment; filename="balance_sheet.xlsx"'
        df.to_excel(resp, index=False, sheet_name='BalanceSheet')
        return resp


class LedgerExportExcelView(LoginRequiredMixin, View):
    def get(self, request, account_id):
        account = get_object_or_404(Account, id=account_id)
        tx = Transaction.objects.filter(account=account).select_related('journal_entry').order_by('journal_entry__date', 'journal_entry__created_at')
        rows = []
        rb = Decimal('0.00')
        for t in tx:
            amt = t.amount if (t.is_debit and account.account_type in ['ASSET','EXPENSE']) or ((not t.is_debit) and account.account_type in ['LIABILITY','EQUITY','REVENUE']) else -t.amount
            rb += amt
            rows.append({
                'Date': t.journal_entry.date.isoformat(),
                'Reference': t.journal_entry.reference,
                'Description': t.description,
                'Debit': float(t.amount if t.is_debit else 0),
                'Credit': float(t.amount if not t.is_debit else 0),
                'RunningBalance': float(rb),
            })
        import pandas as pd
        df = pd.DataFrame(rows)
        resp = HttpResponse(content_type='application/vnd.ms-excel')
        resp['Content-Disposition'] = f'attachment; filename="ledger_{account.code}.xlsx"'
        df.to_excel(resp, index=False, sheet_name='Ledger')
        return resp




# =============
class EnrollmentWithdrawView(LoginRequiredMixin, View):
    def post(self, request, student_id):
        from django.http import JsonResponse
        import json
        
        data = json.loads(request.body)
        course_id = data.get('course_id')
        refund_amount = data.get('refund_amount', 0)
        
        try:
            enrollment = StudentEnrollment.objects.get(
                student_id=student_id, 
                course_id=course_id
            )
            
            # إنشاء قيد الإرجاع
            journal_entry = self.create_withdrawal_entry(enrollment, request.user, refund_amount)
            
            # تحديث حالة التسجيل
            enrollment.is_completed = True
            enrollment.closed_at = timezone.now()
            enrollment.save()
            
            return JsonResponse({
                'success': True,
                'message': 'تم السحب بنجاح',
                'entry_id': journal_entry.id
            })
            
        except StudentEnrollment.DoesNotExist:
            return JsonResponse({
                'success': False,
                'message': 'التسجيل غير موجود'
            }, status=404)
    
    def create_withdrawal_entry(self, enrollment, user, refund_amount):
        """إنشاء قيد محاسبي لسحب الطالب"""
        refund_amount = Decimal(refund_amount or 0)
        
        # إنشاء قيد اليومية
        entry = JournalEntry.objects.create(
            reference=f"WDR-{enrollment.student.id}-{enrollment.course.id}",
            date=timezone.now().date(),
            description=f"سحب الطالب {enrollment.student.full_name} من دورة {enrollment.course.name}",
            entry_type='WITHDRAWAL',
            total_amount=refund_amount,
            created_by=user
        )
        
        # إذا كان هناك مبلغ مرتجع
        if refund_amount > 0:
            # مدين: المصروفات (إرجاعات المبيعات)
            returns_account = Account.objects.get_or_create(
                code='5110',
                defaults={
                    'name': 'إرجاعات المبيعات',
                    'name_ar': 'إرجاعات المبيعات',
                    'account_type': 'EXPENSE',
                    'is_active': True
                }
            )[0]
            
            # دائن: النقدية
            cash_account = Account.objects.get_or_create(
                code='1110',
                defaults={
                    'name': 'النقدية',
                    'name_ar': 'النقدية',
                    'account_type': 'ASSET',
                    'is_active': True
                }
            )[0]
            
            Transaction.objects.create(
                journal_entry=entry,
                account=returns_account,
                amount=refund_amount,
                is_debit=True,
                description=f"إرجاع للطالب {enrollment.student.full_name}"
            )
            
            Transaction.objects.create(
                journal_entry=entry,
                account=cash_account,
                amount=refund_amount,
                is_debit=False,
                description=f"صرف نقدي للإرجاع"
            )
        
        # عكس قيد التسجيل الأصلي
        if enrollment.enrollment_journal_entry:
            # مدين: إيراد الدورات (عكس)
            Transaction.objects.create(
                journal_entry=entry,
                account=enrollment.course.earned_revenue_account,
                amount=enrollment.net_amount,
                is_debit=True,
                description=f"عكس إيراد دورة {enrollment.course.name}"
            )
            
            # دائن: ذمم الطالب (عكس)
            Transaction.objects.create(
                journal_entry=entry,
                account=enrollment.student.ar_account,
                amount=enrollment.net_amount,
                is_debit=False,
                description=f"عكس ذمم مدينة للطالب"
            )
        
        # ترحيل القيد
        entry.post_entry(user)
        
        return entry
    # ============
