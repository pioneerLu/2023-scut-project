from django.shortcuts import render

def hall_view(request):
    return render(request, 'hall/index.html')
