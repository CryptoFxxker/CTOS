from django.shortcuts import render

def strategies_home(request):
    """策略执行页面 - 建设中"""
    return render(request, "strategies/index.html")

