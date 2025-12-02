import requests
import streamlit as st

def map_api_items_to_rows(items, base_url: str):
    """Map API item schema to CSV-like rows."""
    rows = []
    for item in items:
        location = item.get('location', {})
        location_name = location.get('name', '') if isinstance(location, dict) else str(location)
        
        labels = item.get('labels', [])
        label_names = ','.join([label.get('name', '') for label in labels]) if isinstance(labels, list) else ''
        
        def extract_date(iso_str):
            if not iso_str or iso_str.startswith('0001'):
                return ''
            return iso_str.split('T')[0] if 'T' in iso_str else iso_str
        
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

def fetch_api_data(url, token):
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    
    # 1. Get the list of ALL item IDs first
    item_ids = []
    page = 1
    
    status_text = st.empty()
    progress_bar = st.progress(0)
    
    with st.spinner("Fetching item list..."):
        while True:
            try:
                resp = requests.get(
                    f"{url.rstrip('/')}/api/v1/items",
                    params={"page": page, "pageSize": 100, "includeArchived": "true"},
                    headers=headers, timeout=10
                )
                resp.raise_for_status()
                data = resp.json()
                current_items = data.get("items", [])
                
                if not current_items:
                    break
                
                # Collect IDs
                item_ids.extend([item['id'] for item in current_items])
                
                if len(item_ids) >= data.get("total", 0):
                    break
                page += 1
            except Exception as e:
                st.error(f"List Fetch Error: {e}")
                return []

    # 2. Fetch DETAILS for every item (Required for Sold Price/Time)
    full_items = []
    total_items = len(item_ids)
    
    status_text.text(f"Downloading details for {total_items} items...")
    
    # Create a persistent session for speed
    s = requests.Session()
    s.headers.update(headers)
    
    for i, item_id in enumerate(item_ids):
        try:
            # Update progress bar every 5 items to save UI redraws
            if i % 5 == 0:
                progress = (i / total_items)
                progress_bar.progress(progress)
                status_text.text(f"Fetching item {i+1}/{total_items}...")

            r = s.get(f"{url.rstrip('/')}/api/v1/items/{item_id}", timeout=5)
            if r.status_code == 200:
                full_items.append(r.json())
        except Exception as e:
            # Skip failed items but continue
            print(f"Failed to fetch {item_id}: {e}")
            continue

    progress_bar.progress(1.0)
    status_text.text("Processing data...")

    # 3. Flatten API data to match CSV structure
    rows = map_api_items_to_rows(full_items, url)
        
    status_text.empty()
    progress_bar.empty()
    return rows
