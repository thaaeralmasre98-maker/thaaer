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
        
        all_courses = Course.objects.filter(is_active=True).order_by('name')
        available_courses = []
        
        for course in all_courses:
            # Calculate paid amount for this student in this course
            total_paid = StudentReceipt.objects.filter(
                student_profile=student,
                course=course
            ).aggregate(total=Sum('paid_amount'))['total'] or Decimal('0.00')
            
            remaining = max(Decimal('0.00'), course.price - total_paid)
            
            if remaining > Decimal('0.01'):  # If there's remaining amount
                available_courses.append({
                    'course': course,
                    'remaining': remaining
                })
        
        context['courses'] = available_courses
        context['cost_centers'] = CostCenter.objects.filter(is_active=True).order_by('code')

        course_enrollments = (
            StudentEnrollment.objects.filter(student=student, is_completed=False)
            .select_related('course')
            .annotate(total_paid=Sum('payments__paid_amount'))
            .order_by('course__name')
        )

        context['course_enrollments'] = course_enrollments

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
    
    # الدورات لواجهة إصدار الإيصال - فقط الدورات التي لم يتم سدادها بالكامل
    from accounts.models import Course, CostCenter
    from django.db.models import Sum
    
    all_courses = Course.objects.filter(is_active=True).order_by('name')
    available_courses = []
    
    for course in all_courses:
        # حساب المبلغ المدفوع للطالب في هذه الدورة
        total_paid = StudentReceipt.objects.filter(
            student_profile=student,
            course=course
        ).aggregate(total=Sum('paid_amount'))['total'] or Decimal('0.00')
        
        remaining = max(Decimal('0.00'), course.price - total_paid)
        
        if remaining > Decimal('0.01'):  # إذا كان هناك متبقي
            available_courses.append({
                'course': course,
                'remaining': remaining
            })
    
    cost_centers = CostCenter.objects.filter(is_active=True).order_by('code')

    course_enrollments = (
        StudentEnrollment.objects
        .filter(student=student, is_completed=False)
        .select_related('course')
        .annotate(total_paid=Sum('payments__paid_amount'))
        .order_by('course__name')
    )

    context = {
        'student': student,
        'enrollments': enrollments,
        'courses': available_courses,  # فقط الدورات المتاحة
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
    amount = request.POST.get('amount') or 0
    paid_amount = request.POST.get('paid_amount') or 0
    discount_percent = request.POST.get('discount_percent') or (student.discount_percent or 0)
    discount_amount = request.POST.get('discount_amount') or (student.discount_amount or 0)
    
    try:
        amount = Decimal(str(amount))
        paid_amount = Decimal(str(paid_amount))
        discount_percent = Decimal(str(discount_percent))
        discount_amount = Decimal(str(discount_amount))
    except Exception:
        return JsonResponse({'ok': False, 'error': 'BAD_NUMBER_FORMAT'}, status=400)
    
    course = None
    remaining_amount = Decimal('0.00')
    
    if course_id:
        try:
            course = Course.objects.get(pk=course_id)
            if amount == 0:
                amount = Decimal(course.price)
            
            # حساب المبلغ المتبقي للطالب في هذه الدورة
            previous_payments = StudentReceipt.objects.filter(
                student_profile=student,
                course=course
            ).aggregate(total_paid=Sum('paid_amount'))['total_paid'] or Decimal('0.00')
            
            course_price = course.price
            remaining_amount = max(Decimal('0.00'), course_price - previous_payments)
            
            # التأكد من أن المبلغ المدفوع لا يتجاوز المتبقي
            if paid_amount > remaining_amount:
                paid_amount = remaining_amount
            
        except Course.DoesNotExist:
            course = None
    
    # Create receipt
    receipt = StudentReceipt.objects.create(
        date=timezone.now().date(),
        student_profile=student,
        student_name=student.full_name,
        course=course,
        course_name=(course.name if course else ''),
        amount=amount,
        paid_amount=paid_amount,
        discount_percent=discount_percent,
        discount_amount=discount_amount,
        payment_method='CASH',
        created_by=request.user,
    )
    
    journal_warning = None
    try:
        receipt.create_accrual_journal_entry(request.user)
    except Exception as e:
        # Do not block printing; log and return warning for UI
        journal_warning = f"JOURNAL_ERROR: {e}"
        try:
            # Simple server-side log for debugging
            import logging
            logging.getLogger(__name__).exception("Failed to post journal for receipt %s", receipt.id)
        except Exception:
            pass
    
    from django.urls import reverse
    print_url = reverse('accounts:student_receipt_print', args=[receipt.id])
    return JsonResponse({
        'ok': True, 
        'receipt_id': receipt.id, 
        'print_url': print_url,
        'remaining_amount': float(remaining_amount - paid_amount) if course else 0,
        'warning': journal_warning
    })

def register_course(request, student_id):
    student = get_object_or_404(Student, pk=student_id)
    enrollment = StudentEnrollment.objects.create(
        student=student,
        enrollment_date=timezone.now()  # أضف هذا السطر
    )
    enrollment.post_opening_entry()  # إذا كان لديك هذه الدالة
    messages.success(request, 'تم تسجيل الطالب في الدورة وإنشاء الحسابات بنجاح.')
    return redirect('students:student_profile', student_id=student.id)

def quick_receipt(request, student_id):
    student = get_object_or_404(Student, pk=student_id)
    if request.method == 'POST':
        amount = request.POST.get('amount')
        if amount:
            receipt = StudentReceipt.objects.create(student=student, amount=amount)
            receipt.create_accrual_journal_entry()  # إذا كان لديك هذه الدالة
            messages.success(request, 'تم استلام الدفعة وتسجيل القيد المالي.')
            return redirect('students:student_profile', student_id=student.id)
    return render(request, 'students/quick_receipt.html', {'student': student})
