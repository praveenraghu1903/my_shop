from django.urls import path
from . import views

urlpatterns = [
    path('sales/new/', views.sales_new, name='sales_new'),
    path('customers/mobile-lookup/', views.customer_mobile_lookup, name='customer_mobile_lookup'),
    path('sales/summary/', views.sales_summary, name='sales_summary'),
    path('purchase/new/', views.purchase_new, name='purchase_new'),
    path('admin_dashboard/', views.dashboard_redirect, name='dashboard_redirect'),
    path('products/import/', views.product_import, name='product_import'),
    path('reports/daily/', views.daily_report_download, name='daily_report_download'),
    path('cost-prices/export/', views.export_cost_price_template, name='export_cost_price_template'),
    path('cost-prices/import/', views.import_cost_prices, name='import_cost_prices'),
    path('cost-prices/page/', views.cost_price_import_page, name='cost_price_import_page'),
]

