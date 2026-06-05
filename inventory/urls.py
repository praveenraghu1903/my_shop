from django.urls import path
from . import views

urlpatterns = [
    path('sales/new/', views.sales_new, name='sales_new'),
    path('sales/summary/', views.sales_summary, name='sales_summary'),
    path('purchase/new/', views.purchase_new, name='purchase_new'),
    path('admin_dashboard/', views.dashboard_redirect, name='dashboard_redirect'),
    path('products/import/', views.product_import, name='product_import'),
    path('reports/daily/', views.daily_report_download, name='daily_report_download'),
    # Inventory page (staff)
    path('inventory/', views.inventory_dashboard, name='inventory_dashboard'),
    path('inventory/add-product/', views.inventory_add_product, name='inventory_add_product'),
    path('inventory/add-stock/', views.inventory_add_stock, name='inventory_add_stock'),
    path('inventory/edit-invoice/<int:invoice_id>/', views.inventory_edit_invoice, name='inventory_edit_invoice'),
]

