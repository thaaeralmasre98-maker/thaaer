from django import forms
from .models import Teacher, Employee, Vacation
from django.forms import DateInput
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import Group, User
from decimal import Decimal
from accounts.models import EmployeeAdvance


class TeacherForm(forms.ModelForm):
    branches = forms.MultipleChoiceField(
        choices=Teacher.BranchChoices.choices,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        required=True,
        label='الفروع التي يدرسها'
    )
    
    class Meta:
        model = Teacher
        fields = ['full_name', 'phone_number', 'hire_date', 'salary_type', 'hourly_rate', 'monthly_salary', 'notes']
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'أدخل الاسم الكامل'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'أدخل رقم الهاتف'}),
            'hire_date': DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'salary_type': forms.Select(attrs={'class': 'form-control'}),
            'hourly_rate': forms.NumberInput(attrs={'step': '0.01', 'class': 'form-control', 'placeholder': '0.00'}),
            'monthly_salary': forms.NumberInput(attrs={'step': '0.01', 'class': 'form-control', 'placeholder': '0.00'}),
            'notes': forms.Textarea(attrs={'rows': 3, 'class': 'form-control', 'placeholder': 'ملاحظات إضافية'}),
        }
        labels = {
            'full_name': 'الاسم الكامل',
            'phone_number': 'رقم الهاتف',
            'hire_date': 'تاريخ التعيين',
            'salary_type': 'نوع الراتب',
            'hourly_rate': 'أجر الساعة (ل.س)',
            'monthly_salary': 'الراتب الشهري الثابت (ل.س)',
            'notes': 'ملاحظات',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set initial values for branches if editing existing teacher
        if self.instance and self.instance.pk and self.instance.branches:
            self.fields['branches'].initial = self.instance.get_branches_list()
        
        # Make salary fields conditional based on salary type
        self.fields['hourly_rate'].required = False
        self.fields['monthly_salary'].required = False
        self.fields['notes'].required = False

    def clean(self):
        cleaned_data = super().clean()
        branches = cleaned_data.get('branches', [])
        salary_type = cleaned_data.get('salary_type')
        hourly_rate = cleaned_data.get('hourly_rate')
        monthly_salary = cleaned_data.get('monthly_salary')
        
        # Validate branches
        if not branches:
            raise forms.ValidationError('يجب اختيار فرع واحد على الأقل')

        # Validate salary fields based on salary type
        if salary_type == 'hourly' and not hourly_rate:
            self.add_error('hourly_rate', 'يجب إدخال أجر الساعة للراتب بالساعة')
        
        if salary_type == 'monthly' and not monthly_salary:
            self.add_error('monthly_salary', 'يجب إدخال الراتب الشهري للراتب الثابت')
        
        if salary_type == 'mixed' and (not hourly_rate or not monthly_salary):
            if not hourly_rate:
                self.add_error('hourly_rate', 'يجب إدخال أجر الساعة للراتب المختلط')
            if not monthly_salary:
                self.add_error('monthly_salary', 'يجب إدخال الراتب الشهري للراتب المختلط')

        return cleaned_data
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        
        # Convert branches list to comma-separated string
        branches = self.cleaned_data.get('branches', [])
        if isinstance(branches, list):
            instance.branches = ','.join(branches)
        
        # Set default values for salary fields if not provided
        if not instance.hourly_rate:
            instance.hourly_rate = Decimal('0.00')
        if not instance.monthly_salary:
            instance.monthly_salary = Decimal('0.00')
        
        if commit:
            instance.save()
        
        return instance


class EmployeeRegistrationForm(UserCreationForm):
    position = forms.ChoiceField(choices=Employee.POSITION_CHOICES, label='الوظيفة')
    phone_number = forms.CharField(label='رقم الهاتف')
    salary = forms.DecimalField(
        label='الراتب',
        required=True,
        min_value=0,
        max_digits=10,
        decimal_places=2
    )
    
    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'password1', 'password2']
        labels = {
            'username': 'اسم المستخدم',
            'first_name': 'الاسم الأول',
            'last_name': 'الاسم الأخير',
            'email': 'البريد الإلكتروني',
            'password1': 'كلمة السر',
            'password2': 'تأكيد كلمة السر',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and hasattr(self.instance, 'employee'):
            employee = self.instance.employee
            self.fields['position'].initial = employee.position
            self.fields['phone_number'].initial = employee.phone_number
            self.fields['salary'].initial = employee.salary

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data["password1"]
        user.set_password(password)
        
        if commit:
            user.save()
            employee = Employee.objects.create(
                user=user,
                position=self.cleaned_data['position'],
                phone_number=self.cleaned_data['phone_number'],
                salary=self.cleaned_data['salary']
            )
            
            # تحديث الصلاحيات حسب الوظيفة
            user.groups.clear()
            group_name = self.get_group_name()
            try:
                group = Group.objects.get(name=group_name)
                user.groups.add(group)
            except Group.DoesNotExist:
                pass  # Skip if group doesn't exist
        
        return user
    
    def get_group_name(self):
        position = self.cleaned_data.get('position', 'employee')
        return {
            'admin': 'Admins',
            'accountant': 'Accountants',
            'mentor': 'Mentor',
            'manager': 'Managers',
            'marketing': 'Marketing',
            'reception': 'Reception',
        }.get(position, 'Employees')


class VacationForm(forms.ModelForm):
    class Meta:
        model = Vacation
        fields = ['vacation_type', 'reason', 'start_date', 'end_date', 'is_replacement_secured']
        widgets = {
            'start_date': DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'end_date': DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'reason': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
        }
        labels = {
            'vacation_type': 'نوع الإجازة',
            'reason': 'سبب الإجازة',
            'start_date': 'تاريخ بدء الإجازة',
            'end_date': 'تاريخ انتهاء الإجازة',
            'is_replacement_secured': 'تم تأمين البديل',
        }


class AdminVacationForm(forms.ModelForm):
    employee = forms.ModelChoiceField(
        queryset=Employee.objects.all(),
        label='اختيار الموظف',
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    class Meta:
        model = Vacation
        fields = ['employee', 'vacation_type', 'reason', 'start_date', 'end_date', 'is_replacement_secured', 'manager_opinion', 'general_manager_opinion', 'status']
        widgets = {
            'start_date': DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'end_date': DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'reason': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'manager_opinion': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
            'general_manager_opinion': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
        }
        labels = {
            'vacation_type': 'نوع الإجازة',
            'reason': 'سبب الإجازة',
            'start_date': 'تاريخ بدء الإجازة',
            'end_date': 'تاريخ انتهاء الإجازة',
            'is_replacement_secured': 'تم تأمين البديل',
            'manager_opinion': 'رأي المدير',
            'general_manager_opinion': 'رأي المدير العام',
            'status': 'حالة الإجازة',
        }