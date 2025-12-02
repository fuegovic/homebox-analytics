from datetime import datetime
from collections import defaultdict
from src.utils import parse_date, parse_float, location_contains

# --- Core Analysis Logic ---

def analyze_homebox_rows(rows, start_date, end_date):
    """
    Pure logic: takes list of dicts, returns analysis dict.
    No prints, no UI dependencies.
    """
    
    month_sales_products = []
    month_sales_services = []
    
    # Helper to check date range
    def is_in_range(d):
        if not d: return False
        # Compare dates only (strip time)
        return start_date.date() <= d.date() <= end_date.date()

    for r in rows:
        # 1. Check for valid Sold Date
        sold_date = parse_date(r.get('HB.sold_time'))
        
        # Filter by Date Range
        if sold_date and is_in_range(sold_date):
            
            # 2. Categorize: Service vs Product
            # We check Labels AND Location for keywords
            labels = r.get('HB.labels', '').lower()
            location = r.get('HB.location', '').lower()
            
            is_service = (
                'service' in labels or 
                'labor' in labels or 
                'other income' in labels or
                'service' in location or
                'other income' in location
            )
            
            if is_service:
                month_sales_services.append(r)
            else:
                # It's a product sale
                # We exclude "Loss" items from sales counts if they are explicitly marked as Loss
                if 'loss' not in location:
                    month_sales_products.append(r)

    # 3. Calculate Product Metrics
    total_revenue = sum(parse_float(item.get('HB.sold_price', 0)) for item in month_sales_products)
    items_with_cost = [item for item in month_sales_products if parse_float(item.get('HB.purchase_price', 0)) > 0]
    free_items = [item for item in month_sales_products if parse_float(item.get('HB.purchase_price', 0)) == 0]
    cogs = sum(parse_float(item.get('HB.purchase_price', 0)) for item in items_with_cost)
    net_profit = total_revenue - cogs
    
    # ROI
    roi_values = []
    for item in items_with_cost:
        p = parse_float(item.get('HB.purchase_price', 0))
        s = parse_float(item.get('HB.sold_price', 0))
        if p > 0:
            roi_values.append(((s - p) / p) * 100)
    avg_roi = sum(roi_values) / len(roi_values) if roi_values else 0

    # 4. Service Revenue (Other Income)
    service_revenue = sum(parse_float(item.get('HB.sold_price', 0)) for item in month_sales_services)
    other_income_items = month_sales_services

    # 5. Expenses & Assets
    business_items = []
    for r in rows:
        # Check purchase date for expenses (Cash Flow view)
        purchase_date = parse_date(r.get('HB.purchase_time'))
        if purchase_date and is_in_range(purchase_date):
            loc = str(r.get('HB.location', '')).lower()
            # Exclude special buckets from general expenses
            if not any(x in loc for x in ['nfs', 'other income', 'junkagie']):
                business_items.append(r)
            
    total_business_expenses = sum(parse_float(item.get('HB.purchase_price', 0)) for item in business_items)
    
    # Total expenses for the period (including NFS if we were counting it, but we filter it above)
    # We'll calculate total_all_expenses based on the same time range
    period_expenses = []
    for r in rows:
        p_date = parse_date(r.get('HB.purchase_time'))
        if p_date and is_in_range(p_date):
            period_expenses.append(r)
            
    total_all_expenses = sum(parse_float(item.get('HB.purchase_price', 0)) for item in period_expenses)
    
    business_assets = [r for r in rows if location_contains(r.get('HB.location', ''), 'Business Assets')]
    business_assets_value = sum(parse_float(item.get('HB.purchase_price', 0)) for item in business_assets)
    
    # Loss items are usually realized when they are removed/sold, so we check sold_time
    loss_items = []
    for r in rows:
        if location_contains(r.get('HB.location', ''), 'Loss'):
            # Check if the loss was realized in this period (Sold Date)
            # If no sold date, maybe check purchase date? 
            # Usually a loss is a "sale" at $0 or negative.
            s_date = parse_date(r.get('HB.sold_time'))
            if s_date and is_in_range(s_date):
                loss_items.append(r)
                
    loss_value = sum(parse_float(item.get('HB.purchase_price', 0)) for item in loss_items)
    
    junkagie_items = [r for r in rows if location_contains(r.get('HB.location', ''), 'Junkagie')]
    junkagie_count = len(junkagie_items)
    
    # 6. Active Inventory & Stale Inventory
    # Must not be archived, must not be in special buckets
    active_inventory = []
    stale_inventory = []
    now = datetime.now()
    
    for r in rows:
        if r.get('HB.archived') == 'true':
            continue
        loc = str(r.get('HB.location', '')).lower()
        if any(x in loc for x in ['nfs', 'other income', 'junkagie', 'business assets']):
            continue
        
        active_inventory.append(r)
        
        # Stale Check
        p_date = parse_date(r.get('HB.purchase_time'))
        if p_date:
            days_held = (now - p_date).days
            if days_held > 90:
                # Add days_held to the row for display
                r['days_held'] = days_held
                stale_inventory.append(r)
        
    total_active_value = sum(parse_float(item.get('HB.purchase_price', 0)) for item in active_inventory)
    stale_inventory.sort(key=lambda x: x.get('days_held', 0), reverse=True)
    
    # Marketplace (Insured = Posted)
    marketplace_items = [r for r in rows if r.get('HB.insured') == 'true' and r.get('HB.archived') != 'true']
    marketplace_value = sum(parse_float(item.get('HB.purchase_price', 0)) for item in marketplace_items)

    # 7. Velocity
    days_to_sell = []
    for item in month_sales_products:
        p_date = parse_date(item.get('HB.purchase_time'))
        s_date = parse_date(item.get('HB.sold_time'))
        if p_date and s_date:
            days_to_sell.append((s_date - p_date).days)
    
    avg_days = sum(days_to_sell) / len(days_to_sell) if days_to_sell else 0
    quick_flips = len([d for d in days_to_sell if d <= 14])

    # 8. Inventory by Location
    inv_by_loc = defaultdict(lambda: {'count': 0, 'value': 0})
    for item in rows:
        if item.get('HB.archived') != 'true':
            loc = item.get('HB.location', 'Unknown')
            inv_by_loc[loc]['count'] += 1
            inv_by_loc[loc]['value'] += parse_float(item.get('HB.purchase_price', 0))

    return {
        'start_date': start_date,
        'end_date': end_date,
        'product_revenue': total_revenue,
        'service_revenue': service_revenue,
        'total_revenue': total_revenue + service_revenue,
        'cogs': cogs,
        'net_profit': net_profit,
        'service_profit': service_revenue,
        'total_profit': net_profit + service_revenue,
        'avg_roi': avg_roi,
        'items_sold': len(month_sales_products),
        'items_with_cost': len(items_with_cost),
        'free_items_count': len(free_items),
        'avg_sale_price': total_revenue / len(month_sales_products) if month_sales_products else 0,
        'avg_profit_per_item': net_profit / len(month_sales_products) if month_sales_products else 0,
        'business_expenses': total_business_expenses,
        'total_expenses': total_all_expenses,
        'business_assets_value': business_assets_value,
        'business_assets_count': len(business_assets),
        'business_assets': business_assets,
        'loss_value': loss_value,
        'loss_count': len(loss_items),
        'junkagie_count': junkagie_count,
        'junkagie_potential': junkagie_count * 5,
        'active_inventory_value': 0, # Deprecated specific check, using total_active
        'active_inventory_count': 0,
        'total_active_value': total_active_value,
        'total_active_count': len(active_inventory),
        'stale_inventory': stale_inventory,
        'stale_count': len(stale_inventory),
        'marketplace_value': marketplace_value,
        'marketplace_count': len(marketplace_items),
        'avg_days_to_sell': avg_days,
        'quick_flips': quick_flips,
        'fastest_sale': min(days_to_sell) if days_to_sell else 0,
        'slowest_sale': max(days_to_sell) if days_to_sell else 0,
        'month_sales': month_sales_products,
        'items_with_cost': items_with_cost,
        'free_items': free_items,
        'other_income_items': other_income_items,
        'inventory_by_location': dict(inv_by_loc)
    }
