def employee_data(request):
    if request.user.is_authenticated:
        try:
            from .models import Employee
            if hasattr(request.user, 'employee'):
                return {'employee': request.user.employee}
        except Exception:
            pass
    return {}