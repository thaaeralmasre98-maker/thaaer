from django import forms 
from django.views.generic import ListView, CreateView ,DeleteView , UpdateView
from django.views.generic.edit import FormView
from django.urls import reverse_lazy
from django.db.models import Q, Sum
from django.contrib.auth import get_user_model
from attendance.models import Attendance
from classroom.models import Classroomenrollment
from django.http import JsonResponse
from django.utils import timezone
from django.shortcuts import render , redirect, get_object_or_404
from django.views.generic import View , TemplateView ,ListView ,DetailView
from .models import Student
from django.contrib import messages
from django.utils.dateparse import parse_date
from .forms import StudentForm
from collections import defaultdict
from decimal import Decimal
from django.views.decorators.http import require_POST
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from accounts.models import Transaction, StudentReceipt, StudentEnrollment
from django.contrib.auth.mixins import UserPassesTestMixin

User = get_user_model()

def register_course(request, student_id):
    """Register student for a course and create enrollment with accrual entry"""
    student = get_object_or_404(Student, pk=student_id)
    
    if request.method == 'POST':
        course_id = request.POST.get('course_id')
        if not course_id:
            messages.error(request, 'يجب اختيار دورة')
            return redirect('students:student_profile', student_id=student.id)
        
        try:
            from accounts.models import Course, StudentEnrollment
            course = Course.objects.get(pk=course_id)
            
            # Check if already enrolled
            if StudentEnrollment.objects.filter(student=student, course=course).exists():
                messages.warning(request, 'الطالب مسجل بالفعل في هذه الدورة')
                return redirect('students:student_profile', student_id=student.id)
            
            # Create enrollment
            enrollment = StudentEnrollment.objects.create(
                student=student,
                course=course,
                enrollment_date=timezone.now().date(),
                total_amount=course.price,
                discount_percent=student.discount_percent or Decimal('0'),
                discount_amount=student.discount_amount or Decimal('0'),
                payment_method='CASH'
            )
            
            # Create accrual journal entry
            enrollment.create_accrual_enrollment_entry(request.user)
            
            messages.success(request, f'تم تسجيل الطالب في دورة {course.name} وإنشاء الحسابات المحاسبية بنجاح')
            
        except Exception as e:
            messages.error(request, f'خطأ في التسجيل: {str(e)}')
    
    return redirect('students:student_profile', student_id=student.id)

# Add missing view classes
class StudentProfileView(DetailView):
    model = Student
    template_name = 'students/student_profile.html'
    context_object_name = 'student'
    pk_url_kwarg = 'student_id'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        student = self.get_object()
        
        # Get classroom enrollments
        from classroom.models import Classroomenrollment
        enrollments = Classroomenrollment.objects.filter(student=student).select_related('classroom')
        context['enrollments'] = enrollments
        
        # Get available courses for receipt generation
        from accounts.models import Course, CostCenter
        from django.db.models import Sum
        
        # Get all available courses for registration
        all_courses = Course.objects.filter(is_active=True).order_by('name')
        
        context['available_courses'] = all_courses
        context['cost_centers'] = CostCenter.objects.filter(is_active=True).order_by('code')

        # Get current enrollments
        from accounts.models import StudentEnrollment
        course_enrollments = StudentEnrollment.objects.filter(
            student=student, 
            is_completed=False
        ).select_related('course').order_by('course__name')

        context['course_enrollments'] = course_enrollments
        
        # Get courses with remaining balance for receipts
        available_courses = []
        for enrollment in course_enrollments:
            remaining = enrollment.balance_due
            if remaining > Decimal('0.01'):
                available_courses.append({
                    'course': enrollment.course,
                    'remaining': remaining,
                    'enrollment': enrollment
                })
        
        context['courses'] = available_courses

        return context

class StudentStatementView(DetailView):
    model = Student
    template_name = 'students/student_statement.html'
    context_object_name = 'student'
    pk_url_kwarg = 'student_id'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        student = self.get_object()
        account = getattr(student, 'account', None)

        # Get all receipts with user information
        receipts = (StudentReceipt.objects
                    .filter(student_profile=student)
                    .select_related('course', 'created_by')
                    .order_by('-date', '-id'))

        # Calculate payments per course
        paid_by_course = defaultdict(float)
        courses = {}
        for rcp in receipts:
            if rcp.course_id:
                courses[rcp.course_id] = rcp.course
                paid_by_course[rcp.course_id] += float(rcp.net_amount or 0)

        # Calculate remaining per course
        per_course = []
        for cid, course in courses.items():
            price = float(getattr(enrollment, 'net_amount', course.price) or 0)
            paid = paid_by_course.get(cid, 0.0)
            outstanding = max(0.0, price - paid)
            per_course.append({
                'course': course, 
                'price': price, 
                'paid': paid, 
                'outstanding': outstanding
            })
        per_course.sort(key=lambda x: x['course'].name)

        # Get all financial transactions
        rows, bal = [], 0
        if account:
            txns = (Transaction.objects
                    .filter(account=account)
                    .select_related('journal_entry', 'journal_entry__created_by')
                    .order_by('journal_entry__date', 'id'))
            
            for t in txns:
                bal += (t.debit_amount - t.credit_amount)
                rows.append({
                    'date': t.journal_entry.date,
                    'ref': t.journal_entry.reference,
                    'desc': t.description,
                    'debit': t.debit_amount,
                    'credit': t.credit_amount,
                    'balance': bal,
                    'created_by': t.journal_entry.created_by.get_full_name() or t.journal_entry.created_by.username
                })

        context.update({
            'account': account,
            'rows': rows, 
            'balance': bal,
            'receipts': receipts, 
            'per_course': per_course,
        })
        
        return context

class DeactivateStudentView(UpdateView):
    model = Student
    fields = ['is_active']
    template_name = 'students/deactivate_student.html'
    success_url = reverse_lazy('students:student')
    
    def form_valid(self, form):
        form.instance.is_active = False
        response = super().form_valid(form)
        messages.success(self.request, 'تم إلغاء تفعيل الطالب بنجاح')
        return response

class student(ListView):
    template_name = 'students/student.html'
    model = Student
    context_object_name = 'student'
    
    def get_queryset(self):
        # ترتيب الطلاب أبجديًا حسب الاسم
        queryset = Student.objects.all().order_by('full_name')
        
        # إضافة وظيفة البحث
        search_query = self.request.GET.get('search')
        if search_query:
            queryset = queryset.filter(
                Q(full_name__icontains=search_query) |
                Q(student_number__icontains=search_query) |
                Q(branch__icontains=search_query) |
                Q(father_phone__icontains=search_query)
            )
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # إضافة قيمة البحث للقالب للحفاظ عليها في واجهة المستخدم
        context['search_query'] = self.request.GET.get('search', '')
        return context
    
    
class student_groups(TemplateView):
    template_name = 'students/student_groups.html'
    
    
def student_profile(request, student_id):
    student = get_object_or_404(Student, id=student_id)
    from classroom.models import Classroomenrollment
    enrollments = Classroomenrollment.objects.filter(student=student).select_related('classroom')
    
    # Get available courses for registration
    from accounts.models import Course, CostCenter
    from django.db.models import Sum
    
    all_courses = Course.objects.filter(is_active=True).order_by('name')
    
    cost_centers = CostCenter.objects.filter(is_active=True).order_by('code')

    # Get current enrollments
    from accounts.models import StudentEnrollment
    course_enrollments = StudentEnrollment.objects.filter(
        student=student, 
        is_completed=False
    ).select_related('course').order_by('course__name')
    
    # Get courses with remaining balance for receipts
    available_courses = []
    for enrollment in course_enrollments:
        remaining = enrollment.balance_due
        if remaining > Decimal('0.01'):
            available_courses.append({
                'course': enrollment.course,
                'remaining': remaining,
                'enrollment': enrollment
            })

    context = {
        'student': student,
        'enrollments': enrollments,
        'available_courses': all_courses,  # All courses for registration
        'courses': available_courses,  # Courses with remaining balance for receipts
        'cost_centers': cost_centers,
        'course_enrollments': course_enrollments,
    }
    return render(request, 'students/student_profile.html', context)
    
class grades(TemplateView):
    template_name = 'students/grades.html'
    
class courses(TemplateView):
    template_name = 'students/courses.html'
    
class CreateStudentView(CreateView):
    model = Student
    form_class = StudentForm
    template_name = 'students/create_student.html'
    success_url = reverse_lazy('students:student')
    
    def form_valid(self, form):
        form.instance.added_by = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, 'تم إضافة الطالب بنجاح')
        return response
    
    def form_invalid(self, form):
        messages.error(self.request, 'حدث خطأ في إدخال البيانات')
        return super().form_invalid(form)
    
class StudentDeleteView(DeleteView):
    model = Student
    success_url = reverse_lazy('students:student')
    
    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.object.delete()
        return JsonResponse({'success': True})
    
class UpdateStudentView(UserPassesTestMixin, UpdateView):
    model = Student
    form_class = StudentForm
    template_name = 'students/update_student.html'
    success_url = reverse_lazy('students:student')
    
    def test_func(self):
        # يسمح فقط للمستخدم الذي أضاف الطالب أو للمشرفين
        student = self.get_object()
        return self.request.user == student.added_by or self.request.user.is_superuser
    
    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, 'تم تعديل بيانات الطالب بنجاح')
        return response
    
    def form_invalid(self, form):
        messages.error(self.request, 'حدث خطأ في تعديل البيانات')
        return super().form_invalid(form)    
    
class stunum(TemplateView):
    template_name = 'students/stunum.html'    
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # حساب عدد الطلاب الإجمالي
        context['students_count'] = Student.objects.count()
        
        # حساب عدد الطلاب حسب الجنس
        context['male_count'] = Student.objects.filter(gender='male').count()
        context['female_count'] = Student.objects.filter(gender='female').count()
        
        # حساب عدد الطلاب حسب الفرع الدراسي
        context['scientific_count'] = Student.objects.filter(branch='علمي').count()
        context['literary_count'] = Student.objects.filter(branch='أدبي').count()
        context['ninth_grade_count'] = Student.objects.filter(branch='تاسع').count()
        
        return context

def student_statement(request, student_id):
    student = get_object_or_404(Student, id=student_id)
    account = getattr(student, 'account', None)

    # الحصول على جميع الإيصالات مع معلومات المستخدم
    receipts = (StudentReceipt.objects
                .filter(student_profile=student)
                .select_related('course', 'created_by')
                .order_by('-date', '-id'))

    # حساب المدفوعات لكل دورة
    paid_by_course = defaultdict(float)
    courses = {}
    for rcp in receipts:
        if rcp.course_id:
            courses[rcp.course_id] = rcp.course
            paid_by_course[rcp.course_id] += float(rcp.net_amount or 0)

    # حساب المتبقي لكل دورة
    per_course = []
    for cid, course in courses.items():
        price = float(getattr(enrollment, 'net_amount', course.price) or 0)
        paid = paid_by_course.get(cid, 0.0)
        outstanding = max(0.0, price - paid)
        per_course.append({
            'course': course, 
            'price': price, 
            'paid': paid, 
            'outstanding': outstanding
        })
    per_course.sort(key=lambda x: x['course'].name)

    # الحصول على جميع الحركات المالية
    rows, bal = [], 0
    if account:
        txns = (Transaction.objects
                .filter(account=account)
                .select_related('journal_entry', 'journal_entry__created_by')
                .order_by('journal_entry__date', 'id'))
        
        for t in txns:
            bal += (t.debit_amount - t.credit_amount)
            rows.append({
                'date': t.journal_entry.date,
                'ref': t.journal_entry.reference,
                'desc': t.description,
                'debit': t.debit_amount,
                'credit': t.credit_amount,
                'balance': bal,
                'created_by': t.journal_entry.created_by.get_full_name() or t.journal_entry.created_by.username
            })

    return render(request, 'students/student_statement.html', {
        'student': student, 
        'account': account,
        'rows': rows, 
        'balance': bal,
        'receipts': receipts, 
        'per_course': per_course,
    })

@require_POST
@csrf_exempt
def quick_receipt(request, student_id):
    from decimal import Decimal
    from accounts.models import StudentReceipt, Course
    from django.db.models import Sum
    
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'INVALID_METHOD'}, status=405)
    
    student = get_object_or_404(Student, id=student_id)
    
    # Parse inputs
    course_id = request.POST.get('course_id')
    paid_amount = request.POST.get('paid_amount') or 0
    
    try:
        paid_amount = Decimal(str(paid_amount))
    except Exception:
        return JsonResponse({'ok': False, 'error': 'BAD_NUMBER_FORMAT'}, status=400)
    
    if not course_id:
        return JsonResponse({'ok': False, 'error': 'COURSE_REQUIRED'}, status=400)
    
    try:
        course = Course.objects.get(pk=course_id)
        
        # Get enrollment for this student and course
        from accounts.models import StudentEnrollment
        enrollment = StudentEnrollment.objects.filter(
            student=student,
            course=course,
            is_completed=False
        ).first()
        
        if not enrollment:
            return JsonResponse({'ok': False, 'error': 'NO_ENROLLMENT_FOUND'}, status=400)
        
        # Check remaining balance
        remaining_amount = enrollment.balance_due
        if paid_amount > remaining_amount:
            paid_amount = remaining_amount
        
    except Course.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'COURSE_NOT_FOUND'}, status=400)
    
    # Create receipt
    receipt = StudentReceipt.objects.create(
        date=timezone.now().date(),
        student_profile=student,
        student_name=student.full_name,
        course=course,
        course_name=course.name,
        amount=enrollment.total_amount,
        paid_amount=paid_amount,
        discount_percent=enrollment.discount_percent,
        discount_amount=enrollment.discount_amount,
        payment_method='CASH',
        enrollment=enrollment,
        created_by=request.user,
    )
    
    journal_warning = None
    try:
        receipt.create_accrual_journal_entry(request.user)
    except Exception as e:
        journal_warning = f"JOURNAL_ERROR: {e}"
    
    from django.urls import reverse
    print_url = reverse('accounts:student_receipt_print', args=[receipt.id])
    return JsonResponse({
        'ok': True, 
        'receipt_id': receipt.id, 
        'print_url': print_url,
        'remaining_amount': float(remaining_amount - paid_amount),
        'warning': journal_warning
    })

def quick_receipt(request, student_id):
    student = get_object_or_404(Student, pk=student_id)
    if request.method == 'POST':
        amount = request.POST.get('amount')
        if amount:
            receipt = StudentReceipt.objects.create(student=student, amount=amount)
            receipt.create_accrual_journal_entry(request.user)
            messages.success(request, 'تم استلام الدفعة وتسجيل القيد المالي.')
            return redirect('students:student_profile', student_id=student.id)
    return render(request, 'students/quick_receipt.html', {'student': student})
