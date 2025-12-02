import csv
import re
from datetime import datetime
from collections import defaultdict
import glob
import sys

try:
    import requests
except Exception:
    requests = None

def parse_date(date_str):
    """Parse date string, handling invalid dates"""
    if not date_str or str(date_str).startswith('0001'):
        return None
    try:
        clean_str = str(date_str).split('T')[0]
        return datetime.strptime(clean_str, '%Y-%m-%d')
    except:
        return None

def parse_float(value):
    """Safely parse float values"""
    try:
        return float(value) if value else 0.0
    except:
        return 0.0


def location_contains(location: str, text: str) -> bool:
    return text.lower() in str(location).lower()


MONTH_LOOKUP = {
    name.lower(): idx
    for idx, name in enumerate(
        ["January", "February", "March", "April", "May", "June",
         "July", "August", "September", "October", "November", "December"], 1
    )
}
MONTH_LOOKUP.update({
    name[:3].lower(): idx for name, idx in
    zip(
        ["January", "February", "March", "April", "May", "June",
         "July", "August", "September", "October", "November", "December"],
        range(1, 13)
    )
})


def infer_month_year_from_location(location: str):
    """Best-effort month/year extraction from location text like 'Other Income / November 2025'."""
    if not location:
        return None, None

    loc = str(location).lower()

    # Direct YYYY-MM or YYYY/MM patterns
    match = re.search(r"(20\d{2})[\-/](\d{1,2})", loc)
    if match:
        year = int(match.group(1))
        month = int(match.group(2))
        if 1 <= month <= 12:
            return month, year

    for key, month in MONTH_LOOKUP.items():
        if key in loc:
            year_match = re.search(rf"{key}\s*(20\d{{2}})", loc, re.IGNORECASE)
            year = int(year_match.group(1)) if year_match else None
            return month, year

    return None, None

def load_csv_rows(csv_file):
    """Load CSV into a list of row dicts (matching HB.* keys)."""
    rows = []
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows

def validate_rows(rows):
    """Validate data rows"""
    issues = []
    # Validation is minimal now since 0001 dates are normal empty fields
    return issues

def print_validation_issues(issues):
    """Print validation issues"""
    if len(issues) == 0:
        print("✅ No data quality issues found!\n")
        return True
    
    print(f"⚠️  Found {len(issues)} data issue(s):\n")
    for issue in issues:
        print(f"   {issue}\n")
    
    response = input("Continue with report anyway? (y/n): ")
    return response.lower() == 'y'

def analyze_homebox_rows(rows, target_month=11, target_year=2025):
    """Analyze Homebox inventory data from in-memory rows with new categories."""
    
    # Filter sold items (excluding Loss and Other Income)
    # Handle both CSV format ("💵 Sold / November") and API format with soldTime field
    sold_items = []
    for r in rows:
        location = r.get('HB.location', '')
        has_sold_time = r.get('HB.sold_time') and not r.get('HB.sold_time').startswith('0001')
        is_archived = r.get('HB.archived') == 'true'
        
        # Item is sold if: archived AND (location contains "Sold" OR has a valid soldTime)
        if is_archived and ('Sold' in location or has_sold_time):
            # Exclude Other Income and Loss items
            if not location_contains(location, 'Other Income') and not location_contains(location, 'Loss'):
                sold_items.append(r)
    
    # Filter for target month sales
    month_sales = []
    for item in sold_items:
        sold_date = parse_date(item.get('HB.sold_time'))
        if sold_date and sold_date.month == target_month and sold_date.year == target_year:
            month_sales.append(item)
    
    # Calculate revenue
    total_revenue = sum(parse_float(item.get('HB.sold_price', 0)) for item in month_sales)
    
    # Separate items with cost from free items
    items_with_cost = [item for item in month_sales if parse_float(item.get('HB.purchase_price', 0)) > 0]
    free_items = [item for item in month_sales if parse_float(item.get('HB.purchase_price', 0)) == 0]
    
    # Calculate COGS
    cogs = sum(parse_float(item.get('HB.purchase_price', 0)) for item in items_with_cost)
    
    # Calculate net profit
    net_profit = total_revenue - cogs
    
    # Calculate ROI
    roi_values = []
    for item in items_with_cost:
        purchase = parse_float(item.get('HB.purchase_price', 0))
        sold = parse_float(item.get('HB.sold_price', 0))
        if purchase > 0:
            roi = ((sold - purchase) / purchase) * 100
            roi_values.append(roi)
    
    avg_roi = sum(roi_values) / len(roi_values) if roi_values else 0
    
    # Other Income (service revenue)
    other_income = [r for r in rows if location_contains(r.get('HB.location', ''), 'Other Income')]
    other_income_november = []
    for item in other_income:
        sold_date = parse_date(item.get('HB.sold_time'))
        include_item = False
        if sold_date and sold_date.month == target_month and sold_date.year == target_year:
            include_item = True
        else:
            loc_month, loc_year = infer_month_year_from_location(item.get('HB.location', ''))
            if loc_month == target_month and (loc_year is None or loc_year == target_year):
                include_item = True
        if include_item:
            other_income_november.append(item)
    
    service_revenue = sum(parse_float(item.get('HB.sold_price', 0)) for item in other_income_november)
    
    # Business expenses
    business_items = []
    for r in rows:
        location_text = str(r.get('HB.location', ''))
        location_lower = location_text.lower()
        if not any(tag in location_lower for tag in ['nfs', 'other income', 'junkagie']):
            business_items.append(r)
    total_business_expenses = sum(parse_float(item.get('HB.purchase_price', 0)) for item in business_items)
    
    # All expenses
    total_all_expenses = sum(parse_float(item.get('HB.purchase_price', 0)) for item in rows)
    
    # Business Assets
    business_assets = [r for r in rows if 'Business Assets' in r.get('HB.location', '')]
    business_assets_value = sum(parse_float(item.get('HB.purchase_price', 0)) for item in business_assets)
    
    # Loss items
    loss_items = [r for r in rows if 'Loss' in r.get('HB.location', '')]
    loss_value = sum(parse_float(item.get('HB.purchase_price', 0)) for item in loss_items)
    
    # Personal expenses (NFS)
    nfs_items = [r for r in rows if 'NFS' in r.get('HB.location', '')]
    personal_expenses = sum(parse_float(item.get('HB.purchase_price', 0)) for item in nfs_items)
    
    # Junkagie items
    junkagie_items = [r for r in rows if 'Junkagie' in r.get('HB.location', '')]
    junkagie_count = len(junkagie_items)
    junkagie_potential = junkagie_count * 5
    
    # Active inventory (not archived, in storage locations)
    active_inventory = [r for r in rows 
                        if r.get('HB.archived') != 'true' 
                        and r.get('HB.location', '').startswith('📦')]
    active_inventory_value = sum(parse_float(item.get('HB.purchase_price', 0)) for item in active_inventory)
    
    # All non-archived inventory (excluding NFS, Other Income, Junkagie)
    total_active = []
    for r in rows:
        if r.get('HB.archived') == 'true':
            continue
        location_lower = str(r.get('HB.location', '')).lower()
        if any(tag in location_lower for tag in ['nfs', 'other income', 'junkagie', 'business assets']):
            continue
        total_active.append(r)
    total_active_value = sum(parse_float(item.get('HB.purchase_price', 0)) for item in total_active)
    total_active_count = len(total_active)
    
    # Marketplace items (insured = posted online)
    marketplace_items = [r for r in rows if r.get('HB.insured') == 'true' and r.get('HB.archived') != 'true']
    marketplace_value = sum(parse_float(item.get('HB.purchase_price', 0)) for item in marketplace_items)
    marketplace_count = len(marketplace_items)
    
    # Sales velocity
    days_to_sell = []
    for item in month_sales:
        purchase_date = parse_date(item.get('HB.purchase_time'))
        sold_date = parse_date(item.get('HB.sold_time'))
        if purchase_date and sold_date:
            days = (sold_date - purchase_date).days
            days_to_sell.append(days)
    
    avg_days = sum(days_to_sell) / len(days_to_sell) if days_to_sell else 0
    quick_flips = len([d for d in days_to_sell if d <= 14])
    
    # Inventory by location
    inventory_by_location = defaultdict(lambda: {'count': 0, 'value': 0})
    for item in rows:
        if item.get('HB.archived') != 'true':
            location = item.get('HB.location', 'Unknown')
            inventory_by_location[location]['count'] += 1
            inventory_by_location[location]['value'] += parse_float(item.get('HB.purchase_price', 0))
    
    return {
        'target_month': target_month,
        'target_year': target_year,
        'product_revenue': total_revenue,
        'service_revenue': service_revenue,
        'total_revenue': total_revenue + service_revenue,
        'cogs': cogs,
        'net_profit': net_profit,
        'service_profit': service_revenue,  # Service revenue is pure profit
        'total_profit': net_profit + service_revenue,
        'avg_roi': avg_roi,
        'items_sold': len(month_sales),
        'items_with_cost': len(items_with_cost),
        'free_items_count': len(free_items),
        'avg_sale_price': total_revenue / len(month_sales) if month_sales else 0,
        'avg_profit_per_item': net_profit / len(month_sales) if month_sales else 0,
        'business_expenses': total_business_expenses,
        'total_expenses': total_all_expenses,
        'business_assets_value': business_assets_value,
        'business_assets_count': len(business_assets),
        'business_assets': business_assets,
        'loss_value': loss_value,
        'loss_count': len(loss_items),
        'personal_expenses': personal_expenses,
        'personal_count': len(nfs_items),
        'junkagie_count': junkagie_count,
        'junkagie_potential': junkagie_potential,
        'active_inventory_value': active_inventory_value,
        'active_inventory_count': len(active_inventory),
        'total_active_value': total_active_value,
        'total_active_count': total_active_count,
        'marketplace_value': marketplace_value,
        'marketplace_count': marketplace_count,
        'avg_days_to_sell': avg_days,
        'quick_flips': quick_flips,
        'fastest_sale': min(days_to_sell) if days_to_sell else 0,
        'slowest_sale': max(days_to_sell) if days_to_sell else 0,
        'month_sales': month_sales,
        'items_with_cost': items_with_cost,
        'free_items': free_items,
        'other_income_items': other_income_november,
        'inventory_by_location': dict(inventory_by_location)
    }

def fetch_homebox_items_via_api(base_url: str, token: str, page_size: int = 100):
    """Fetch items from Homebox API with full details."""
    if requests is None:
        raise RuntimeError("The 'requests' package is required for API mode. Install: pip install requests")
    
    s = requests.Session()
    s.headers.update({
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    })
    
    # First, get the list of all items
    item_ids = []
    page = 1
    
    while True:
        try:
            url = f"{base_url.rstrip('/')}/api/v1/items"
            resp = s.get(url, params={"page": page, "pageSize": page_size, "includeArchived": "true"}, timeout=30)
            resp.raise_for_status()
            
            data = resp.json()
            page_items = data.get("items", [])
            
            if not page_items:
                break
            
            item_ids.extend([item['id'] for item in page_items])
            
            # Check if there are more pages
            total = data.get("total", 0)
            if len(item_ids) >= total:
                break
            
            page += 1
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                raise RuntimeError("Authentication failed. Check your API token.")
            raise RuntimeError(f"API request failed: {e}")
        except Exception as e:
            raise RuntimeError(f"API request failed: {e}")
    
    print(f"Found {len(item_ids)} items, fetching full details...")
    
    # Now fetch full details for each item
    items = []
    for i, item_id in enumerate(item_ids, 1):
        try:
            url = f"{base_url.rstrip('/')}/api/v1/items/{item_id}"
            resp = s.get(url, timeout=30)
            resp.raise_for_status()
            item_detail = resp.json()
            items.append(item_detail)
            
            if i % 10 == 0:
                print(f"  Progress: {i}/{len(item_ids)}")
                
        except Exception as e:
            print(f"  Warning: Failed to fetch item {item_id}: {e}")
            continue
    
    return items


def map_api_items_to_rows(items, base_url: str):
    """Map API item schema to CSV-like rows."""
    rows = []
    for item in items:
        # Extract location name from nested object
        location = item.get('location', {})
        location_name = location.get('name', '') if isinstance(location, dict) else str(location)
        
        # Extract labels
        labels = item.get('labels', [])
        label_names = ','.join([label.get('name', '') for label in labels]) if isinstance(labels, list) else ''
        
        # Handle date fields (API returns ISO format, convert to YYYY-MM-DD)
        def extract_date(iso_str):
            if not iso_str or iso_str.startswith('0001'):
                return ''
            return iso_str.split('T')[0] if 'T' in iso_str else iso_str
        
        # Map API fields to HB.* CSV column names
        row = {
            'HB.import_ref': '',
            'HB.location': location_name,
            'HB.labels': label_names,
            'HB.asset_id': str(item.get('assetId', '')),
            'HB.archived': 'true' if item.get('archived') else 'false',
            'HB.url': f"{base_url.rstrip('/')}/item/{item.get('id', '')}",
            'HB.name': item.get('name', ''),
            'HB.quantity': str(item.get('quantity', 1)),
            'HB.description': item.get('description', ''),
            'HB.insured': 'true' if item.get('insured') else 'false',
            'HB.notes': item.get('notes', ''),
            'HB.purchase_price': str(item.get('purchasePrice', 0)),
            'HB.purchase_from': item.get('purchaseFrom', ''),
            'HB.purchase_time': extract_date(item.get('purchaseTime', '')),
            'HB.manufacturer': item.get('manufacturer', ''),
            'HB.model_number': item.get('modelNumber', ''),
            'HB.serial_number': item.get('serialNumber', ''),
            'HB.lifetime_warranty': 'true' if item.get('lifetimeWarranty') else 'false',
            'HB.warranty_expires': extract_date(item.get('warrantyExpires', '')),
            'HB.warranty_details': item.get('warrantyDetails', ''),
            'HB.sold_to': item.get('soldTo', ''),
            'HB.sold_price': str(item.get('soldPrice', 0)),
            'HB.sold_time': extract_date(item.get('soldTime', '')),
            'HB.sold_notes': item.get('soldNotes', '')
        }
        rows.append(row)
    return rows

def generate_report(data, target_month=11, target_year=2025):
    """Generate comprehensive financial report"""
    
    print("=" * 70)
    print(f"HOMEBOX BUSINESS TRACKER - {data['target_year']}-{data['target_month']:02d} REPORT")
    print("=" * 70)
    
    # Financial Summary
    print("\n💰 FINANCIAL SUMMARY")
    print("-" * 70)
    print(f"Product Sales Revenue:           ${data['product_revenue']:.2f}")
    print(f"Service Revenue (Other Income):  ${data['service_revenue']:.2f}")
    print(f"Total Revenue:                   ${data['total_revenue']:.2f}")
    print(f"Cost of Goods Sold:              ${data['cogs']:.2f}")
    print(f"Net Profit (Products):           ${data['net_profit']:.2f}")
    print(f"Service Profit:                  ${data['service_profit']:.2f}")
    print(f"Total Profit:                    ${data['total_profit']:.2f}")
    
    print(f"\nTotal Business Expenses:         ${data['business_expenses']:.2f}")
    print(f"  - Inventory (COGS):            ${data['cogs']:.2f}")
    print(f"  - Business Assets:             ${data['business_assets_value']:.2f}")
    print(f"Total Expenses (Including NFS):  ${data['total_expenses']:.2f}")
    
    if data['personal_expenses'] > 0:
        print(f"\n🎁 Personal Expenses (NFS):      ${data['personal_expenses']:.2f} ({data['personal_count']} items)")
    
    if data['loss_value'] > 0:
        print(f"\n💸 Losses (Giveaways):           ${data['loss_value']:.2f} ({data['loss_count']} items)")
    
    # ROI Analysis
    print("\n\n📊 ROI ANALYSIS")
    print("-" * 70)
    print(f"Average ROI:                     {data['avg_roi']:.1f}%")
    print(f"Items Sold:                      {data['items_sold']}")
    if data['free_items_count'] > 0:
        print(f"  └─ Pure Profit Items (free):   {data['free_items_count']}")
    print(f"Average Sale Price:              ${data['avg_sale_price']:.2f}")
    print(f"Average Profit per Item:         ${data['avg_profit_per_item']:.2f}")
    
    # Best/Worst Performers
    if data['items_with_cost']:
        items_with_roi = []
        for item in data['items_with_cost']:
            purchase = parse_float(item.get('HB.purchase_price', 0))
            sold = parse_float(item.get('HB.sold_price', 0))
            roi = ((sold - purchase) / purchase) * 100
            items_with_roi.append((item, roi))
        
        items_with_roi.sort(key=lambda x: x[1], reverse=True)
        best = items_with_roi[0]
        worst = items_with_roi[-1]
        
        print(f"\n🏆 Best Performer:")
        print(f"  {best[0].get('HB.name')}")
        print(f"  ${parse_float(best[0].get('HB.purchase_price', 0)):.2f} → ${parse_float(best[0].get('HB.sold_price', 0)):.2f} ({best[1]:.0f}% ROI)")
        
        print(f"\n📉 Worst Performer:")
        print(f"  {worst[0].get('HB.name')}")
        print(f"  ${parse_float(worst[0].get('HB.purchase_price', 0)):.2f} → ${parse_float(worst[0].get('HB.sold_price', 0)):.2f} ({worst[1]:.0f}% ROI)")
    
    if data['free_items']:
        print(f"\n💎 Pure Profit Items (Cost: $0):")
        for item in data['free_items']:
            print(f"  ${parse_float(item.get('HB.sold_price', 0)):.2f}  {item.get('HB.name')}")
    
    # Sales Velocity
    if data['avg_days_to_sell'] > 0:
        print("\n\n⚡ SALES VELOCITY")
        print("-" * 70)
        print(f"Average Days to Sell:            {data['avg_days_to_sell']:.1f} days")
        print(f"Quick Flips (≤14 days):          {data['quick_flips']} items")
        print(f"Fastest Sale:                    {data['fastest_sale']} days")
        print(f"Slowest Sale:                    {data['slowest_sale']} days")
    
    # Inventory Status
    print("\n\n📦 INVENTORY STATUS")
    print("-" * 70)
    print(f"Total Active Inventory:")
    print(f"  Cost:                          ${data['total_active_value']:.2f}")
    print(f"  Items:                         {data['total_active_count']}")
    
    if data['avg_roi'] > 0:
        projected_revenue = data['total_active_value'] * (1 + data['avg_roi']/100)
        projected_profit = projected_revenue - data['total_active_value']
        print(f"  Projected Revenue (avg ROI):   ${projected_revenue:.2f}")
        print(f"  Projected Profit:              ${projected_profit:.2f}")
    
    print(f"\nMarketplace (Posted Online):")
    print(f"  Items Posted:                  {data['marketplace_count']}")
    print(f"  Cost:                          ${data['marketplace_value']:.2f}")
    
    if data['avg_roi'] > 0 and data['marketplace_value'] > 0:
        market_projected_revenue = data['marketplace_value'] * (1 + data['avg_roi']/100)
        market_projected_profit = market_projected_revenue - data['marketplace_value']
        print(f"  Projected Revenue (avg ROI):   ${market_projected_revenue:.2f}")
        print(f"  Projected Profit:              ${market_projected_profit:.2f}")
    
    # Business Assets
    if data['business_assets_count'] > 0:
        print(f"\nBusiness Assets:                 ${data['business_assets_value']:.2f} ({data['business_assets_count']} items)")
        for asset in data['business_assets']:
            print(f"  - {asset.get('HB.name')}: ${parse_float(asset.get('HB.purchase_price', 0)):.2f}")
    
    # Junkagie
    if data['junkagie_count'] > 0:
        print(f"\nJunkagie/Books for Sale:         {data['junkagie_count']} items")
        print(f"Potential Revenue (@$5 each):    ${data['junkagie_potential']:.2f}")
    
    # Inventory by Location
    print("\n\n📍 INVENTORY BY LOCATION")
    print("-" * 70)
    for location, info in sorted(data['inventory_by_location'].items(), key=lambda x: x[1]['value'], reverse=True):
        print(f"{location:40s} {info['count']:2d} items  ${info['value']:7.2f}")
    
    # Service Income Detail
    if data['other_income_items']:
        print("\n\n💸 OTHER INCOME (SERVICE REVENUE)")
        print("-" * 70)
        for item in data['other_income_items']:
            print(f"${parse_float(item.get('HB.sold_price', 0)):7.2f}  {item.get('HB.name')}")
    
    # Sales Detail
    print(f"\n\n🛍️  {data['target_year']}-{data['target_month']:02d} SALES DETAIL")
    print("-" * 70)
    sorted_sales = sorted(data['month_sales'], key=lambda x: parse_float(x.get('HB.sold_price', 0)), reverse=True)
    for item in sorted_sales:
        print(f"${parse_float(item.get('HB.sold_price', 0)):7.2f}  {item.get('HB.name')}")
    
    print("\n" + "=" * 70)

if __name__ == "__main__":
    # Choose data source
    print("Select data source:")
    print("  1) Homebox API (token)")
    print("  2) Local CSV export (default)")
    choice = input("Enter 1 or 2 [2]: ").strip()
    
    rows = None
    
    if choice == '1':
        base_url = input("Homebox base URL [https://homebox.example.com]: ").strip() or "https://homebox.example.com"
        token = input("API token: ").strip()
        
        if not token:
            print("No token provided, falling back to CSV mode.\n")
        else:
            try:
                api_items = fetch_homebox_items_via_api(base_url, token)
                rows = map_api_items_to_rows(api_items, base_url)
                print(f"✓ Fetched {len(rows)} items from API.\n")
            except Exception as e:
                print(f"API fetch failed: {e}")
                print("Falling back to CSV mode.\n")
    
    if rows is None:
        # Find CSV files
        csv_files = glob.glob("homebox-items_*.csv")
        
        if len(csv_files) == 0:
            print("Error: No homebox CSV files found.")
            sys.exit(1)
        elif len(csv_files) == 1:
            csv_file = csv_files[0]
            print(f"Using CSV file: {csv_file}\n")
        else:
            csv_files.sort(reverse=True)
            print("Multiple CSV files found:")
            for i, f in enumerate(csv_files, 1):
                print(f"  {i}. {f}")
            
            sel = input("\nEnter number (or press Enter for most recent): ").strip()
            if sel == "":
                csv_file = csv_files[0]
            else:
                try:
                    csv_file = csv_files[int(sel) - 1]
                except (ValueError, IndexError):
                    print("Invalid choice. Using most recent.")
                    csv_file = csv_files[0]
            
            print(f"\nUsing: {csv_file}\n")
        
        rows = load_csv_rows(csv_file)
    
    try:
        # Validate
        issues = validate_rows(rows)
        if not print_validation_issues(issues):
            print("\nExiting.")
            sys.exit(0)
        
        # Analyze and report
        data = analyze_homebox_rows(rows)
        generate_report(data)
        
        print("\n✓ Analysis complete!")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()