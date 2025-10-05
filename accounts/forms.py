﻿from django import forms
from django.forms import inlineformset_factory
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Submit, Row, Column, Field
from employ.models import Employee, Teacher
from .models import (
    Account, JournalEntry, Transaction, StudentReceipt, ExpenseEntry,
    Course, Student, StudentEnrollment, EmployeeAdvance, AccountingPeriod, Budget,
    DiscountRule
)

class AccountForm(forms.ModelForm):
    class Meta:
        model = Account
        fields = ['code', 'account_type', 'parent', 'name', 'name_ar', 'is_course_account', 'course_name', 'description', 'is_active']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'name': forms.TextInput(attrs={'placeholder': 'Account Name'}),
            'name_ar': forms.TextInput(attrs={'placeholder': 'ط§ظ„ط§ط³ظ… ط¨ط§ظ„ط¹ط±ط¨ظٹط©', 'dir': 'rtl'}),
            'code': forms.TextInput(attrs={'placeholder': 'e.g., 1000'}),
            'course_name': forms.TextInput(attrs={'placeholder': 'Course Name (if course account)'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Row(
                Column('code', css_class='form-group col-md-4 mb-0'),
                Column('account_type', css_class='form-group col-md-4 mb-0'),
                Column('parent', css_class='form-group col-md-4 mb-0'),
                css_class='form-row'
            ),
            Row(
                Column('name', css_class='form-group col-md-6 mb-0'),
                Column('name_ar', css_class='form-group col-md-6 mb-0'),
                css_class='form-row'
            ),
            Row(
                Column('is_course_account', css_class='form-group col-md-6 mb-0'),
                Column('course_name', css_class='form-group col-md-6 mb-0'),
                css_class='form-row'
            ),
            'description',
            'is_active',
            Submit('submit', 'حفظ / Save', css_class='btn btn-primary')
        )
class CourseForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = ['name', 'name_ar', 'description', 'price', 'duration_hours', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'Course Name'}),
            'name_ar': forms.TextInput(attrs={'placeholder': 'ط§ط³ظ… ط§ظ„ط¯ظˆط±ط© ط¨ط§ظ„ط¹ط±ط¨ظٹط©', 'dir': 'rtl'}),
            'description': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Course description'}),
            'price': forms.NumberInput(attrs={'step': '0.01', 'min': '0.01', 'placeholder': '0.00'}),
            'duration_hours': forms.NumberInput(attrs={'min': '1', 'placeholder': 'Hours'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Row(
                Column('name', css_class='form-group col-md-6 mb-0'),
                Column('name_ar', css_class='form-group col-md-6 mb-0'),
                css_class='form-row'
            ),
            'description',
            Row(
                Column('price', css_class='form-group col-md-4 mb-0'),
                Column('duration_hours', css_class='form-group col-md-4 mb-0'),
                Column('is_active', css_class='form-group col-md-4 mb-0'),
                css_class='form-row'
            ),
            Submit('submit', 'حفظ / Save', css_class='btn btn-primary')
        )
class StudentForm(forms.ModelForm):
    class Meta:
        model = Student
        fields = ['student_id', 'name', 'email', 'phone', 'address', 'is_active']
        widgets = {
            'student_id': forms.TextInput(attrs={'placeholder': 'Student ID'}),
            'name': forms.TextInput(attrs={'placeholder': 'Student Name'}),
            'email': forms.EmailInput(attrs={'placeholder': 'email@example.com'}),
            'phone': forms.TextInput(attrs={'placeholder': 'Phone Number'}),
            'address': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Address'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Row(
                Column('student_id', css_class='form-group col-md-6 mb-0'),
                Column('name', css_class='form-group col-md-6 mb-0'),
                css_class='form-row'
            ),
            Row(
                Column('email', css_class='form-group col-md-6 mb-0'),
                Column('phone', css_class='form-group col-md-6 mb-0'),
                css_class='form-row'
            ),
            'address',
            'is_active',
            Submit('submit', 'حفظ / Save', css_class='btn btn-primary')
        )

class StudentEnrollmentForm(forms.ModelForm):
    class Meta:
        model = StudentEnrollment
        fields = ['student', 'course', 'enrollment_date', 'total_amount', 'discount_percent', 'discount_amount', 'payment_method', 'notes']
        widgets = {
            'enrollment_date': forms.DateInput(attrs={'type': 'date'}),
            'total_amount': forms.NumberInput(attrs={'step': '0.01', 'min': '0.01', 'placeholder': '0.00'}),
            'discount_percent': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'max': '100', 'placeholder': '0.00'}),
            'discount_amount': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'placeholder': '0.00'}),
            'notes': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Additional notes'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Import the correct Student model
        from students.models import Student as SProfile
        self.fields['student'].queryset = SProfile.objects.filter(is_active=True).order_by('full_name')
        self.fields['course'].queryset = Course.objects.filter(is_active=True).order_by('name')
        
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Row(
                Column('student', css_class='form-group col-md-6 mb-0'),
                Column('course', css_class='form-group col-md-6 mb-0'),
                css_class='form-row'
            ),
            Row(
                Column('enrollment_date', css_class='form-group col-md-4 mb-0'),
                Column('total_amount', css_class='form-group col-md-4 mb-0'),
                Column('payment_method', css_class='form-group col-md-4 mb-0'),
                css_class='form-row'
            ),
            Row(
                Column('discount_percent', css_class='form-group col-md-6 mb-0'),
                Column('discount_amount', css_class='form-group col-md-6 mb-0'),
                css_class='form-row'
            ),
            'notes',
            Submit('submit', 'تسجيل الطالب / Enroll Student', css_class='btn btn-primary')
        )

class EmployeeAdvanceForm(forms.ModelForm):
    class Meta:
        model = EmployeeAdvance
        fields = ['employee', 'employee_name', 'date', 'amount', 'purpose', 'repayment_date']
        widgets = {
            'employee_name': forms.TextInput(attrs={'placeholder': 'Employee Name'}),
            'date': forms.DateInput(attrs={'type': 'date'}),
            'amount': forms.NumberInput(attrs={'step': '0.01', 'min': '0.01', 'placeholder': '0.00'}),
            'purpose': forms.TextInput(attrs={'placeholder': 'Purpose of advance'}),
            'repayment_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['employee'].required = False
        self.fields['employee_name'].required = False
        self.fields['employee'].queryset = Employee.objects.select_related('user').order_by('user__first_name', 'user__last_name', 'user__username')
        self.fields['employee'].empty_label = "اختر الموظف / Select Employee"
        def _employee_label(obj):
            user = getattr(obj, 'user', None)
            if user:
                full_name = user.get_full_name()
                return full_name if full_name else user.get_username()
            return str(obj)
        self.fields['employee'].label_from_instance = _employee_label
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Row(
                Column('employee', css_class='form-group col-md-6 mb-0'),
                Column('employee_name', css_class='form-group col-md-6 mb-0'),
                css_class='form-row'
            ),
            Row(
                Column('date', css_class='form-group col-md-6 mb-0'),
                Column('amount', css_class='form-group col-md-6 mb-0'),
                css_class='form-row'
            ),
            Row(
                Column('repayment_date', css_class='form-group col-md-6 mb-0'),
                css_class='form-row'
            ),
            'purpose',
            Submit('submit', 'إنشاء سلفة / Create Advance', css_class='btn btn-primary')
        )

    def clean(self):
        cleaned_data = super().clean()
        employee = cleaned_data.get('employee')
        employee_name = (cleaned_data.get('employee_name') or '').strip()
        if not employee and not employee_name:
            raise forms.ValidationError('Select an employee or enter an employee name.')
        if employee and not employee_name:
            user = getattr(employee, 'user', None)
            if user:
                full_name = user.get_full_name()
                cleaned_data['employee_name'] = full_name if full_name else user.get_username()
            else:
                cleaned_data['employee_name'] = str(employee)
        return cleaned_data


class AccountingPeriodForm(forms.ModelForm):
    class Meta:
        model = AccountingPeriod
        fields = ['name', 'start_date', 'end_date']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
            'name': forms.TextInput(attrs={'placeholder': 'اسم الفترة / Period Name'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.layout = Layout(
            'name',
            Row(
                Column('start_date', css_class='form-group col-md-6 mb-0'),
                Column('end_date', css_class='form-group col-md-6 mb-0'),
                css_class='form-row'
            ),
            Submit('submit', 'حفظ / Save', css_class='btn btn-primary')
        )

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        
        if start_date and end_date:
            if start_date >= end_date:
                raise forms.ValidationError('يجب أن يكون تاريخ البداية قبل تاريخ النهاية / Start date must be before end date')
        
        return cleaned_data


class BudgetForm(forms.ModelForm):
    class Meta:
        model = Budget
        fields = ['account', 'period', 'budgeted_amount', 'notes']
        widgets = {
            'budgeted_amount': forms.NumberInput(attrs={'step': '0.01', 'min': '0.01', 'placeholder': '0.00'}),
            'notes': forms.Textarea(attrs={'rows': 3, 'placeholder': 'ملاحظات إضافية / Additional notes'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['account'].queryset = Account.objects.filter(is_active=True).order_by('code')
        self.fields['account'].empty_label = "اختر الحساب / Select Account"
        self.fields['period'].empty_label = "اختر الفترة / Select Period"
        
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Row(
                Column('account', css_class='form-group col-md-6 mb-0'),
                Column('period', css_class='form-group col-md-6 mb-0'),
                css_class='form-row'
            ),
            'budgeted_amount',
            'notes',
            Submit('submit', 'حفظ / Save', css_class='btn btn-primary')
        )


class DiscountRuleForm(forms.ModelForm):
    class Meta:
        model = DiscountRule
        fields = ['reason', 'reason_ar', 'discount_percent', 'discount_amount', 'description', 'is_active']
        widgets = {
            'reason': forms.TextInput(attrs={'placeholder': 'Discount Reason'}),
            'reason_ar': forms.TextInput(attrs={'placeholder': 'ط³ط¨ط¨ ط§ظ„طط³ظ… ط¨ط§ظ„ط¹ط±ط¨ظٹط©', 'dir': 'rtl'}),
            'discount_percent': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'max': '100', 'placeholder': '0.00'}),
            'discount_amount': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'placeholder': '0.00'}),
            'description': forms.Textarea(attrs={'rows': 3, 'placeholder': 'ظˆطµظپ ظ‚ط§ط¹ط¯ط© ط§ظ„طط³ظ…'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Row(
                Column('reason', css_class='form-group col-md-6 mb-0'),
                Column('reason_ar', css_class='form-group col-md-6 mb-0'),
                css_class='form-row'
            ),
            Row(
                Column('discount_percent', css_class='form-group col-md-6 mb-0'),
                Column('discount_amount', css_class='form-group col-md-6 mb-0'),
                css_class='form-row'
            ),
            'description',
            'is_active',
            Submit('submit', 'حفظ قاعدة الخصم / Save Discount Rule', css_class='btn btn-primary')
        )

class JournalEntryForm(forms.ModelForm):
    class Meta:
        model = JournalEntry
        fields = ['date', 'reference', 'description']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'description': forms.Textarea(attrs={'rows': 3}),
            'reference': forms.TextInput(attrs={'placeholder': 'JE-001'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['reference'].required = False
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Row(
                Column('reference', css_class='form-group col-md-6 mb-0'),
                Column('date', css_class='form-group col-md-6 mb-0'),
                css_class='form-row'
            ),
            'description',
        )

class TransactionForm(forms.ModelForm):
    class Meta:
        model = Transaction
        fields = ['account', 'amount', 'is_debit', 'cost_center', 'description']
        widgets = {
            'amount': forms.NumberInput(attrs={'step': '0.01', 'min': '0.01'}),
            'description': forms.TextInput(attrs={'placeholder': 'Transaction description'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['account'].queryset = Account.objects.filter(is_active=True).order_by('code')
        self.fields['account'].empty_label = "اختر الحساب / Select Account"

# Create formset for transactions
TransactionFormSet = inlineformset_factory(
    JournalEntry,
    Transaction,
    form=TransactionForm,
    extra=2,
    min_num=2,
    validate_min=True,
    can_delete=True
)


class StudentReceiptForm(forms.ModelForm):
    class Meta:
        model = StudentReceipt
        fields = ['date', 'student_name', 'course_name', 'student_profile', 'student', 'course', 'amount', 'discount_percent', 'discount_amount', 'payment_method', 'notes']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'student_name': forms.TextInput(attrs={'placeholder': 'اسم الطالب / Student Name'}),
            'course_name': forms.TextInput(attrs={'placeholder': 'اسم الدورة / Course Name'}),
            'amount': forms.NumberInput(attrs={'step': '0.01', 'min': '0.01', 'placeholder': '0.00'}),
            'notes': forms.Textarea(attrs={'rows': 3, 'placeholder': 'ملاحظات إضافية / Additional notes'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from students.models import Student as StudentProfile
        self.fields['student_profile'].queryset = StudentProfile.objects.filter(is_active=True).order_by('full_name')
        # Remove the old student field reference since we're using student_profile
        self.fields['course'].queryset = Course.objects.filter(is_active=True).order_by('name')
        self.fields['course'].empty_label = "اختر الدورة (اختياري) / Select Course (Optional)"
        self.fields['course'].required = False
        
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Row(
                Column('date', css_class='form-group col-md-6 mb-0'),
                Column('payment_method', css_class='form-group col-md-6 mb-0'),
                css_class='form-row'
            ),
            Row(
                Column('student_name', css_class='form-group col-md-6 mb-0'),
                Column('course_name', css_class='form-group col-md-6 mb-0'),
                css_class='form-row'
            ),
            Row(
                Column('student_profile', css_class='form-group col-md-6 mb-0'),
                Column('course', css_class='form-group col-md-6 mb-0'),
                css_class='form-row'
            ),
            'amount',
            'notes',
            Submit('submit', 'إنشاء إيصال / Create Receipt', css_class='btn btn-primary')
        )


class ExpenseEntryForm(forms.ModelForm):
    class Meta:
        model = ExpenseEntry
        fields = ['date', 'description', 'category', 'amount', 'payment_method', 'vendor', 'receipt_number', 'employee', 'teacher', 'notes']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'description': forms.TextInput(attrs={'placeholder': 'وصف المصروف / Expense Description'}),
            'amount': forms.NumberInput(attrs={'step': '0.01', 'min': '0.01', 'placeholder': '0.00'}),
            'vendor': forms.TextInput(attrs={'placeholder': 'اسم المورد / Vendor Name'}),
            'receipt_number': forms.TextInput(attrs={'placeholder': 'رقم الإيصال / Receipt Number'}),
            'notes': forms.Textarea(attrs={'rows': 3, 'placeholder': 'ملاحظات إضافية / Additional notes'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['employee'].required = False
        self.fields['teacher'].required = False
        self.fields['employee'].queryset = Employee.objects.select_related('user').order_by('user__first_name', 'user__last_name', 'user__username')
        self.fields['teacher'].queryset = Teacher.objects.order_by('full_name')
        self.fields['employee'].empty_label = "اختر الموظف / Select Employee"
        self.fields['teacher'].empty_label = "اختر المعلم / Select Teacher"
        def _employee_label(obj):
            user = getattr(obj, 'user', None)
            if user:
                full_name = user.get_full_name()
                return full_name if full_name else user.get_username()
            return str(obj)
        self.fields['employee'].label_from_instance = _employee_label
        self.fields['teacher'].label_from_instance = lambda obj: obj.full_name
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Row(
                Column('date', css_class='form-group col-md-4 mb-0'),
                Column('category', css_class='form-group col-md-4 mb-0'),
                Column('payment_method', css_class='form-group col-md-4 mb-0'),
                css_class='form-row'
            ),
            Row(
                Column('description', css_class='form-group col-md-8 mb-0'),
                Column('amount', css_class='form-group col-md-4 mb-0'),
                css_class='form-row'
            ),
            Row(
                Column('vendor', css_class='form-group col-md-6 mb-0'),
                Column('receipt_number', css_class='form-group col-md-6 mb-0'),
                css_class='form-row'
            ),
            Row(
                Column('employee', css_class='form-group col-md-6 mb-0'),
                Column('teacher', css_class='form-group col-md-6 mb-0'),
                css_class='form-row'
            ),
            'notes',
            Submit('submit', 'تسجيل مصروف / Record Expense', css_class='btn btn-primary')
        )

    def clean(self):
        cleaned_data = super().clean()
        employee = cleaned_data.get('employee')
        teacher = cleaned_data.get('teacher')
        if employee and teacher:
            raise forms.ValidationError('Select either an employee or a teacher, not both.')
        category = cleaned_data.get('category')
        if teacher:
            cleaned_data['category'] = 'TEACHER_SALARY'
        elif category == 'TEACHER_SALARY' and not teacher:
            cleaned_data['category'] = 'SALARY'
        return cleaned_data






