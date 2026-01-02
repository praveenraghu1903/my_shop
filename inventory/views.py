from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from .models import Store, Product, Stock, Invoice, InvoiceItem, UserProfile, Supplier, Purchase, PurchaseItem, Location, InvoiceContact
from django.contrib import messages
from django.db import transaction
from django.utils import timezone
from django.db.models import Sum
from decimal import Decimal

@login_required
def dashboard_redirect(request):
    if request.user.is_staff or request.user.is_superuser:
        return redirect('/admin/')
    return redirect('sales_new')

@login_required
def sales_new(request):
    # Fetch products with their assigned locations, ordered by category for grouping
    products = Product.objects.prefetch_related('locations').order_by('category', 'name')
    locations = Location.objects.all()
    
    # Get stock levels for Godown (assuming sales come from Godown)
    godown = Store.objects.filter(store_type='GODOWN').first()
    stock_map = {}
    if godown:
        stocks = Stock.objects.filter(store=godown)
        stock_map = {s.product_id: s.quantity for s in stocks}

    # Attach stock quantity to each product object
    for p in products:
        p.stock_quantity = stock_map.get(p.id, 0)
    
    # Get today's summary
    today = timezone.now().date()
    # Filter invoices by the user's store if possible
    try:
        user_store = request.user.userprofile.store
    except UserProfile.DoesNotExist:
        user_store = None

    if request.method == 'POST':
        if not user_store:
            messages.error(request, "You are not assigned to any store.")
            return redirect('sales_new')

        customer_name = request.POST.get('customer_name')
        mobiles = request.POST.getlist('customer_mobile[]')
        primary_mobile = mobiles[0] if mobiles else None
        paid_amount = Decimal(request.POST.get('paid_amount'))

        # Support multiple items via arrays; fallback to single item if arrays not provided
        product_ids = request.POST.getlist('product_ids[]')
        quantities_raw = request.POST.getlist('quantities[]')
        rates_raw = request.POST.getlist('rates[]')
        location_ids = request.POST.getlist('locations[]')

        # Fallback to single-item fields
        if not product_ids:
            single_product_id = request.POST.get('product')
            single_qty = request.POST.get('quantity')
            single_rate = request.POST.get('rate')
            if single_product_id and single_qty and single_rate:
                product_ids = [single_product_id]
                quantities_raw = [single_qty]
                rates_raw = [single_rate]

        try:
            with transaction.atomic():
                godown = Store.objects.filter(store_type='GODOWN').first()
                if not godown:
                    raise Exception("Central Godown not found.")

                # Parse and validate lists
                if not product_ids or len(product_ids) != len(quantities_raw) or len(product_ids) != len(rates_raw):
                    raise Exception("Invalid sale items submitted.")

                items = []
                total_amount = Decimal('0')
                # Pre-check stock availability for all items
                for idx, (pid, q_raw, r_raw) in enumerate(zip(product_ids, quantities_raw, rates_raw)):
                    product = Product.objects.get(id=pid)
                    qty = Decimal(q_raw)
                    rate = Decimal(r_raw)
                    total_amount += qty * rate
                    stock = Stock.objects.filter(product=product, store=godown).first()
                    if not stock or stock.quantity < qty:
                        available = stock.quantity if stock else Decimal('0')
                        raise Exception(f"Insufficient stock for {product.name}. Available: {available}")
                    # Resolve optional location for this item
                    loc_id = location_ids[idx] if idx < len(location_ids) else None
                    loc_obj = None
                    if loc_id:
                        try:
                            loc_obj = Location.objects.get(id=loc_id)
                        except Location.DoesNotExist:
                            loc_obj = None
                    items.append((product, qty, rate, stock, loc_obj))

                # Create invoice
                invoice = Invoice.objects.create(
                    store=user_store,
                    customer_name=customer_name,
                    customer_mobile=primary_mobile,
                    total_amount=total_amount,
                    paid_amount=paid_amount
                )

                # Save all mobile numbers as contacts for the invoice
                for m in mobiles:
                    if m:
                        InvoiceContact.objects.create(invoice=invoice, mobile=m)

                # Deduct stock and create invoice items
                for product, qty, rate, stock, loc in items:
                    stock.quantity -= qty
                    stock.save()
                    InvoiceItem.objects.create(
                        invoice=invoice,
                        product=product,
                        quantity=qty,
                        rate=rate,
                        location=loc
                    )

                messages.success(request, f"Sale recorded successfully! Invoice #{invoice.id}")
                return redirect('sales_new')

        except Exception as e:
            messages.error(request, str(e))

    # Calculate today's stats for the cards
    today_sales = Invoice.objects.filter(date__date=today, store=user_store).aggregate(Sum('total_amount'))['total_amount__sum'] or 0
    today_received = Invoice.objects.filter(date__date=today, store=user_store).aggregate(Sum('paid_amount'))['paid_amount__sum'] or 0
    today_due = today_sales - today_received

    context = {
        'products': products,
        'locations': locations,
        'user_store': user_store,
        'today_sales': today_sales,
        'today_received': today_received,
        'today_due': today_due,
    }
    return render(request, 'inventory/sales_new.html', context)

@staff_member_required
def sales_summary(request):
    today = timezone.now().date()
    
    total_sales = Invoice.objects.filter(date__date=today).aggregate(Sum('total_amount'))['total_amount__sum'] or 0
    total_paid = Invoice.objects.filter(date__date=today).aggregate(Sum('paid_amount'))['paid_amount__sum'] or 0
    total_due = total_sales - total_paid
    total_invoices = Invoice.objects.filter(date__date=today).count()
    
    # Purchases (Expenses)
    total_purchases = Purchase.objects.filter(date__date=today).aggregate(Sum('total_amount'))['total_amount__sum'] or 0
    net_profit = total_sales - total_purchases

    # Store-wise breakdown (Legacy summary)
    stores = Store.objects.filter(store_type='DISPLAY')
    store_stats = []
    for store in stores:
        s_sales = Invoice.objects.filter(date__date=today, store=store).aggregate(Sum('total_amount'))['total_amount__sum'] or 0
        store_stats.append({
            'name': store.name,
            'sales': s_sales
        })

    # Detailed Invoices per Store
    silwani_invoices = Invoice.objects.filter(
        date__date=today, 
        store__name='Silwani'
    ).prefetch_related('items', 'items__product').order_by('-date')
    
    gairatganj_invoices = Invoice.objects.filter(
        date__date=today, 
        store__name='Gairatganj'
    ).prefetch_related('items', 'items__product').order_by('-date')

    context = {
        'total_sales': total_sales,
        'total_paid': total_paid,
        'total_due': total_due,
        'total_invoices': total_invoices,
        'total_purchases': total_purchases,
        'net_profit': net_profit,
        'store_stats': store_stats,
        'silwani_invoices': silwani_invoices,
        'gairatganj_invoices': gairatganj_invoices,
    }
    return render(request, 'inventory/sales_summary.html', context)

@staff_member_required
def purchase_new(request):
    products = Product.objects.all()
    suppliers = Supplier.objects.all()
    recent_purchases = Purchase.objects.order_by('-date')[:10]

    if request.method == 'POST':
        supplier_name = request.POST.get('supplier_name')
        invoice_number = request.POST.get('invoice_number')
        product_id = request.POST.get('product')
        quantity = Decimal(request.POST.get('quantity'))
        rate = Decimal(request.POST.get('rate'))
        
        # Calculate total
        total_amount = quantity * rate
        
        try:
            with transaction.atomic():
                # 1. Get or Create Supplier
                supplier, created = Supplier.objects.get_or_create(name=supplier_name)
                
                # 2. Create Purchase Record
                purchase = Purchase.objects.create(
                    supplier=supplier,
                    invoice_number=invoice_number,
                    total_amount=total_amount
                )
                
                # 3. Create Purchase Item
                PurchaseItem.objects.create(
                    purchase=purchase,
                    product_id=product_id,
                    quantity=quantity,
                    rate=rate
                )
                
                # 4. Add Stock to Godown
                godown = Store.objects.get(store_type='GODOWN')
                stock, created = Stock.objects.get_or_create(product_id=product_id, store=godown)
                stock.quantity += quantity
                stock.save()
                
                messages.success(request, f"Purchase recorded! Stock added to Godown. Purchase ID: {purchase.id}")
                return redirect('purchase_new')

        except Exception as e:
            messages.error(request, f"Error: {str(e)}")

    context = {
        'products': products,
        'suppliers': suppliers,
        'recent_purchases': recent_purchases,
    }
    return render(request, 'inventory/purchase_new.html', context)
