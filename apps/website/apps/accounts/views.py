from django.shortcuts import render

def account_list(request):
    # 示例数据，以后可以接 AccountManager
    accounts = [
        {"exchange": "okx", "sub": "main", "balance": 10000},
        {"exchange": "backpack", "sub": "arb_bot", "balance": 2500},
    ]
    return render(request, "accounts/list.html", {"accounts": accounts})