import json
import os
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
from datetime import datetime, date, timedelta
from collections import defaultdict
from dotenv import load_dotenv

from src.analysis import analyze_homebox_rows
from src.api import fetch_api_data
from src.pdf import generate_accountant_pdf
from src.utils import parse_date, parse_float, sanitize_rows

# --- CONFIGURATION ---
load_dotenv()

# Load Config from Env
PAGE_TITLE = os.getenv("PAGE_TITLE", "Homebox Analytics")
APP_TITLE = os.getenv("APP_TITLE", "Homebox Business Tracker")
cache_ttl_env = os.getenv("CACHE_TTL")
CACHE_TTL = int(cache_ttl_env) if cache_ttl_env else None

st.set_page_config(
    page_title=PAGE_TITLE,
    page_icon="📦",
    layout="wide"
)

def analyze_data(rows, start_date, end_date):
    """Reuse the detailed analyzer so summary & detail stay in sync."""
    detail_data = run_detailed_analysis(rows, start_date, end_date)
    summary = {
        'revenue': detail_data['product_revenue'],
        'cogs': detail_data['cogs'],
        'profit': detail_data['net_profit'],
        'service': detail_data['service_revenue'],
        'roi': detail_data['avg_roi'],
        'count': detail_data['items_sold'],
        'sales_data': detail_data['month_sales'],
        'active_val': detail_data['total_active_value'],
        'active_count': detail_data['total_active_count'],
    }
    return summary, detail_data


@st.cache_data(show_spinner=False, ttl=CACHE_TTL)
def run_detailed_analysis(raw_rows, start_date, end_date):
    """Run the heavy detailed analysis with caching."""
    safe_rows = sanitize_rows(raw_rows)
    # Ensure dates are datetime objects for the analyzer if they are date objects
    if isinstance(start_date, date):
        start_date = datetime.combine(start_date, datetime.min.time())
    if isinstance(end_date, date):
        end_date = datetime.combine(end_date, datetime.max.time())
        
    return analyze_homebox_rows(safe_rows, start_date, end_date)


def render_detailed_tab(detail_data):
    items_with_cost = detail_data.get('items_with_cost', [])
    free_items = detail_data.get('free_items', [])
    other_income_items = detail_data.get('other_income_items', [])
    business_assets = detail_data.get('business_assets', [])

    # --- ROI Gauge (Moved to Top) ---
    roi_gauge_max = max(100, detail_data['avg_roi'] * 1.3 + 10)
    roi_gauge = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=detail_data['avg_roi'],
            number={"suffix": "%"},
            title={"text": "Average ROI"},
            gauge={
                "axis": {"range": [0, roi_gauge_max]},
                "bar": {"color": "#00CC96"},
                "steps": [
                    {"range": [0, roi_gauge_max * 0.4], "color": "#FFC8C8"},
                    {"range": [roi_gauge_max * 0.4, roi_gauge_max * 0.7], "color": "#FFE8A6"},
                    {"range": [roi_gauge_max * 0.7, roi_gauge_max], "color": "#C8F7C5"},
                ],
            },
        )
    )
    roi_gauge.update_layout(
        height=320,
        margin=dict(l=20, r=20, t=80, b=10),
        title={'text': 'Average ROI', 'y': 0.92}
    )
    st.plotly_chart(roi_gauge, use_container_width=True)

    # --- Financial Summary ---
    st.subheader("Financial Summary")
    fin_cols = st.columns(3)
    fin_cols[0].metric("Product Revenue", f"${detail_data['product_revenue']:,.2f}")
    fin_cols[1].metric("Service Revenue", f"${detail_data['service_revenue']:,.2f}")
    fin_cols[2].metric("Total Revenue", f"${detail_data['total_revenue']:,.2f}")

    fin_cols = st.columns(3)
    fin_cols[0].metric("COGS", f"${detail_data['cogs']:,.2f}")
    fin_cols[1].metric("Net Profit (Products)", f"${detail_data['net_profit']:,.2f}")
    fin_cols[2].metric("Total Profit", f"${detail_data['total_profit']:,.2f}")

    st.markdown("### Expense Breakdown")
    exp_cols = st.columns(3)
    exp_cols[0].metric("Business Expenses", f"${detail_data['business_expenses']:,.2f}")
    exp_cols[1].metric("Total Expenses", f"${detail_data['total_expenses']:,.2f}")
    exp_cols[2].metric("Losses", f"${detail_data['loss_value']:,.2f}", f"{detail_data['loss_count']} items")

    # --- ROI Leaderboard ---
    roi_df_rows = []
    for item in items_with_cost:
        purchase = parse_float(item.get('HB.purchase_price', 0))
        sold = parse_float(item.get('HB.sold_price', 0))
        roi = ((sold - purchase) / purchase) * 100 if purchase else 0
        roi_df_rows.append({
            'Item': item.get('HB.name', ''),
            'Cost': purchase,
            'Sold': sold,
            'Profit': sold - purchase,
            'ROI %': roi,
            'Location': item.get('HB.location', ''),
            'URL': item.get('HB.url', '')
        })

    if roi_df_rows:
        roi_df = pd.DataFrame(roi_df_rows).sort_values('ROI %', ascending=False)
        st.markdown("#### ROI Leaderboard")
        top_bottom = pd.concat([roi_df.head(5), roi_df.tail(5)]) if len(roi_df) > 10 else roi_df
        st.dataframe(
            top_bottom.style.format({
                'Cost': "${:,.2f}",
                'Sold': "${:,.2f}",
                'Profit': "${:,.2f}",
                'ROI %': "{:,.1f}"
            }),
            use_container_width=True
        )

        roi_fig = px.bar(
            roi_df.head(15),
            x='Item',
            y='ROI %',
            color='Profit',
            title='Top 15 ROI Performers',
            color_continuous_scale='Greens'
        )
        st.plotly_chart(roi_fig, use_container_width=True)

        best_row = roi_df.iloc[0]
        worst_row = roi_df.iloc[-1]
        st.success(
            f"🏆 Best: {best_row['Item']} — ${best_row['Cost']:,.2f} → ${best_row['Sold']:,.2f} ({best_row['ROI %']:.0f}% ROI)"
        )
        st.warning(
            f"📉 Worst: {worst_row['Item']} — ${worst_row['Cost']:,.2f} → ${worst_row['Sold']:,.2f} ({worst_row['ROI %']:.0f}% ROI)"
        )

    if free_items:
        st.markdown("#### Pure Profit Items ($0 cost)")
        free_df = pd.DataFrame([
            {
                'Item': item.get('HB.name', ''),
                'Sold Price': parse_float(item.get('HB.sold_price', 0)),
                'Location': item.get('HB.location', '')
            }
            for item in free_items
        ]).sort_values('Sold Price', ascending=False)
        st.dataframe(
            free_df.style.format({'Sold Price': "${:,.2f}"}),
            use_container_width=True
        )

    st.markdown("### Sales Velocity")
    vel_cols = st.columns(4)
    vel_cols[0].metric("Avg Days to Sell", f"{detail_data['avg_days_to_sell']:.1f}")
    vel_cols[1].metric("Fastest Sale", f"{detail_data['fastest_sale']} days")
    vel_cols[2].metric("Slowest Sale", f"{detail_data['slowest_sale']} days")
    vel_cols[3].metric("Quick Flips", detail_data['quick_flips'])

    st.markdown("### Inventory Outlook")
    inv_cols = st.columns(4)
    inv_cols[0].metric("Active Inventory Cost", f"${detail_data['active_inventory_value']:,.2f}", f"{detail_data['active_inventory_count']} items")
    inv_cols[1].metric("Total Active Cost", f"${detail_data['total_active_value']:,.2f}", f"{detail_data['total_active_count']} items")

    projected_revenue = detail_data['total_active_value'] * (1 + detail_data['avg_roi']/100) if detail_data['avg_roi'] > 0 else 0
    projected_profit = projected_revenue - detail_data['total_active_value'] if projected_revenue else 0
    inv_cols[2].metric("Projected Revenue", f"${projected_revenue:,.2f}")
    inv_cols[3].metric("Projected Profit", f"${projected_profit:,.2f}")

    market_cols = st.columns(3)
    market_cols[0].metric("Marketplace Items", detail_data['marketplace_count'])
    market_cols[1].metric("Marketplace Cost", f"${detail_data['marketplace_value']:,.2f}")
    market_proj = detail_data['marketplace_value'] * (1 + detail_data['avg_roi']/100) if detail_data['avg_roi'] > 0 else 0
    market_cols[2].metric("Marketplace Projection", f"${market_proj:,.2f}")

    st.markdown("### Business Assets & Special Buckets")
    special_cols = st.columns(3)
    special_cols[0].metric("Business Assets", f"${detail_data['business_assets_value']:,.2f}", f"{detail_data['business_assets_count']} items")
    special_cols[1].metric("Junkagie Count", detail_data['junkagie_count'], f"${detail_data['junkagie_potential']:,.2f} potential")
    special_cols[2].metric("Service Revenue Items", len(other_income_items))

    if business_assets:
        assets_df = pd.DataFrame([
            {
                'Asset': asset.get('HB.name', ''),
                'Cost': parse_float(asset.get('HB.purchase_price', 0)),
                'Location': asset.get('HB.location', '')
            }
            for asset in business_assets
        ])
        st.markdown("#### Business Assets Detail")
        st.dataframe(
            assets_df.sort_values('Cost', ascending=False).style.format({'Cost': "${:,.2f}"}),
            use_container_width=True
        )

    if other_income_items:
        oi_df = pd.DataFrame([
            {
                'Item': item.get('HB.name', ''),
                'Revenue': parse_float(item.get('HB.sold_price', 0)),
                'Sold Date': item.get('HB.sold_time', '')
            }
            for item in other_income_items
        ])
        st.markdown("#### Other Income Detail")
        st.dataframe(
            oi_df.sort_values('Revenue', ascending=False).style.format({'Revenue': "${:,.2f}"}),
            use_container_width=True
        )

    if detail_data['inventory_by_location']:
        loc_df = pd.DataFrame([
            {
                'Location': location,
                'Items': info['count'],
                'Value': info['value']
            }
            for location, info in detail_data['inventory_by_location'].items()
        ]).sort_values('Value', ascending=False)
        st.markdown("### Inventory by Location")
        loc_fig = px.treemap(loc_df, path=['Location'], values='Value', color='Items',
                             title='Value Concentration by Location', color_continuous_scale='Blues')
        st.plotly_chart(loc_fig, use_container_width=True)
        st.dataframe(
            loc_df.style.format({'Value': "${:,.2f}"}),
            use_container_width=True
        )

    if detail_data['month_sales']:
        sales_df = pd.DataFrame([
            {
                'Item': item.get('HB.name', ''),
                'Sold Price': parse_float(item.get('HB.sold_price', 0)),
                'Cost': parse_float(item.get('HB.purchase_price', 0)),
                'Profit': parse_float(item.get('HB.sold_price', 0)) - parse_float(item.get('HB.purchase_price', 0)),
                'Sold Date': item.get('HB.sold_time', ''),
                'Location': item.get('HB.location', '')
            }
            for item in detail_data['month_sales']
        ]).sort_values('Sold Price', ascending=False)
        st.markdown("### Sales Detail")
        st.dataframe(
            sales_df.style.format({
                'Sold Price': "${:,.2f}",
                'Cost': "${:,.2f}",
                'Profit': "${:,.2f}"
            }).background_gradient(subset=['Profit'], cmap='RdYlGn'),
            use_container_width=True
        )


# --- UI LAYOUT ---

st.title(f"📦 {APP_TITLE}")

# Sidebar
with st.sidebar:
    st.header("Data Source")
    source_type = st.radio(
        "Select Source",
        ["CSV Upload", "API Connection"],
        index=1,
        help="API is the default; switch to CSV if you prefer manual uploads."
    )
    
    rows = []
    
    if source_type == "CSV Upload":
        uploaded_file = st.file_uploader("Upload Homebox CSV", type=['csv'])
        if uploaded_file:
            df = pd.read_csv(uploaded_file)
            rows = df.to_dict('records')
            st.success(f"Loaded {len(rows)} items")
            
    else:
        default_url = os.getenv("HOMEBOX_URL", "https://homebox.example.com")
        default_token = os.getenv("HOMEBOX_TOKEN", "")
        auto_load = os.getenv("AUTO_LOAD_DATA", "false").lower() == "true"

        url = st.text_input("Homebox URL", default_url)
        token = st.text_input("API Token", value=default_token, type="password")
        
        # Auto-load logic
        if auto_load and url and token and 'rows' not in st.session_state:
            with st.spinner("Auto-loading data..."):
                try:
                    rows = fetch_api_data(url, token)
                    st.session_state['rows'] = rows
                    st.rerun()
                except Exception as e:
                    st.error(f"Auto-load failed: {e}")

        if st.button("Fetch Data"):
            if url and token:
                rows = fetch_api_data(url, token)
                st.session_state['rows'] = rows
            else:
                st.warning("Please provide URL and Token")
        
        # Persist data across reruns
        if 'rows' in st.session_state:
            rows = st.session_state['rows']
            st.success(f"Loaded {len(rows)} items from API")

    st.markdown("---")
    st.header("Report Period")
    
    # Date Selection Mode
    use_advanced_date = st.checkbox("Use Advanced Date Range", value=False, help="Switch to custom date range selection")
    
    today = date.today()
    
    if use_advanced_date:
        # Advanced: Quick Select Options
        date_option = st.radio(
            "Quick Select",
            ["Past 7 Days", "Past 30 Days", "Past 90 Days", "Past 365 Days", "Specific Year", "Custom Range"],
            index=1,
            horizontal=True
        )

        if date_option == "Past 7 Days":
            start_date = today - timedelta(days=7)
            end_date = today
        elif date_option == "Past 30 Days":
            start_date = today - timedelta(days=30)
            end_date = today
        elif date_option == "Past 90 Days":
            start_date = today - timedelta(days=90)
            end_date = today
        elif date_option == "Past 365 Days":
            start_date = today - timedelta(days=365)
            end_date = today
        elif date_option == "Specific Year":
            sel_year_adv = st.number_input("Select Year", value=today.year, min_value=2020, max_value=2030)
            start_date = date(sel_year_adv, 1, 1)
            end_date = date(sel_year_adv, 12, 31)
        else: # Custom Range
            first_day = today.replace(day=1)
            date_range = st.date_input(
                "Select Date Range",
                value=(first_day, today),
                max_value=today,
                format="YYYY-MM-DD"
            )
            
            # Handle single date selection
            if isinstance(date_range, tuple):
                if len(date_range) == 2:
                    start_date, end_date = date_range
                elif len(date_range) == 1:
                    start_date = date_range[0]
                    end_date = start_date
                else:
                    start_date = first_day
                    end_date = today
            else:
                start_date = first_day
                end_date = today
            
    else:
        # Standard: Month/Year Selector
        col1, col2 = st.columns([2, 1])
        with col1:
            sel_month = st.selectbox("Month", range(1, 13), index=today.month-1, format_func=lambda x: date(2000, x, 1).strftime('%B'))
        with col2:
            sel_year = st.number_input("Year", value=today.year, min_value=2020, max_value=2030)
            
        # Calculate start/end for the selected month
        import calendar
        last_day = calendar.monthrange(sel_year, sel_month)[1]
        start_date = date(sel_year, sel_month, 1)
        end_date = date(sel_year, sel_month, last_day)

# Main Content
if not rows:
    st.info("👈 Please upload a CSV or connect to the API to begin analysis.")
else:
    # Run Analysis
    with st.spinner("Analyzing dataset..."):
        data, detail_data = analyze_data(rows, start_date, end_date)
    
    # --- HEADER: Top Level Stats ---
    st.markdown(f"### 📊 Report for {start_date} to {end_date}")

    # Row 1: Volume & Revenue Types
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        # 1. Items Sold (The Volume)
        st.metric(
            "📦 Items Sold", 
            data['count'], 
            help="Number of physical items sold this month"
        )
        
    with col2:
        # 2. Product Revenue (Selling Stuff)
        product_rev = data['revenue']
        st.metric(
            "🏷️ Product Revenue", 
            f"${product_rev:,.2f}",
            help="Revenue strictly from selling inventory"
        )
        
    with col3:
        # 3. Service Revenue (Other Income/Labor)
        # This was hidden before!
        st.metric(
            "🛠️ Service Revenue", 
            f"${data['service']:,.2f}",
            help="Income from labor, services, or non-inventory items"
        )
        
    with col4:
        # 4. Total Revenue (The big number)
        total_rev = data['revenue'] + data['service']
        st.metric(
            "💰 Total Revenue", 
            f"${total_rev:,.2f}",
            delta="Combined",
            delta_color="off"
        )

    st.markdown("---")

    # Row 2: Profitability & Health
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)

    total_profit = data['profit'] + data['service']
    
    kpi1.metric(
        "📉 COGS", 
        f"${data['cogs']:,.2f}", 
        help="Cost of Goods Sold (What you paid for the items you sold)"
    )
    
    kpi2.metric(
        "💵 Net Profit", 
        f"${total_profit:,.2f}", 
        delta=f"{data['roi']:.1f}% ROI",
        help="Total Revenue - COGS. Includes service income."
    )
    
    # Calculated Margin
    margin = (total_profit / total_rev * 100) if total_rev > 0 else 0
    kpi3.metric(
        "📈 Net Margin", 
        f"{margin:.1f}%",
        help="Percentage of revenue you actually keep"
    )

    kpi4.metric(
        "🏦 Active Inventory", 
        f"${data['active_val']:,.2f}", 
        f"{data['active_count']} items",
        help="Total purchase price of items currently in stock"
    )

    st.markdown("---")
    
    # Custom CSS to make the download button compact
    st.markdown("""
        <style>
        div[data-testid="stDownloadButton"] button {
            width: 42px !important;
            padding: 0 !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
        }
        </style>
    """, unsafe_allow_html=True)

    # Compact Export UI
    # Note: "auto" is not supported in st.columns weights, using tight ratio instead
    ex_col1, ex_col2, ex_col3 = st.columns([1.5, 0.15, 6], gap="small", vertical_alignment="bottom")
    
    with ex_col1:
        export_format = st.selectbox(
            "Export Report",
            ["Select format...", "JSON (Full Data)", "PDF (Summary)"],
            index=0,
            help="Select a format to enable the download button."
        )

    with ex_col2:
        # Pre-calculate data for the button
        file_data = ""
        file_name = ""
        mime_type = ""
        is_disabled = True
        
        date_str = f"{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}"
        
        if export_format == "JSON (Full Data)":
            file_data = json.dumps(detail_data, indent=2, default=str)
            file_name = f"homebox_detailed_{date_str}.json"
            mime_type = "application/json"
            is_disabled = False
            
        elif export_format == "PDF (Summary)":
            try:
                file_data = generate_accountant_pdf(detail_data)
                file_name = f"homebox_accountant_{date_str}.pdf"
                mime_type = "application/pdf"
                is_disabled = False
            except Exception as e:
                st.error(f"PDF Error: {e}")
        
        st.download_button(
            label="",
            icon=":material/download:",
            data=file_data,
            file_name=file_name,
            mime=mime_type,
            disabled=is_disabled,
            use_container_width=False
        )

    # --- TABS: Charts & Data ---
    tabs = st.tabs(["💰 Sales Performance", "🧾 Detailed Insights", "📦 Inventory Details", "⚠️ Stale Inventory", "📄 Raw Data"])

    tab1, detailed_tab, tab2, tab_stale, tab3 = tabs
    
    with tab1:
        # [Keep the existing chart code from previous version]
        if data['sales_data']:
            sales_df = pd.DataFrame(data['sales_data'])
            
            display_df = pd.DataFrame()
            display_df['Item'] = sales_df['HB.name']
            display_df['Sold Price'] = sales_df['HB.sold_price'].apply(parse_float)
            display_df['Cost'] = sales_df['HB.purchase_price'].apply(parse_float)
            display_df['Profit'] = display_df['Sold Price'] - display_df['Cost']
            display_df['Date'] = sales_df['HB.sold_time'].apply(lambda x: str(x).split('T')[0])
            
            fig = px.bar(
                display_df, 
                x='Item', 
                y=['Cost', 'Profit'], 
                title="Revenue Breakdown (Cost vs Profit)",
                color_discrete_map={'Cost': '#EF553B', 'Profit': '#00CC96'}
            )
            st.plotly_chart(fig, use_container_width=True)
            st.markdown("### Sales Ledger")
            st.dataframe(
                display_df.style.format({
                    "Sold Price": "${:.2f}", 
                    "Cost": "${:.2f}", 
                    "Profit": "${:.2f}"
                }).background_gradient(subset=['Profit'], cmap='RdYlGn'),
                use_container_width=True
            )
        else:
            st.warning("No sales found for this period.")

    with tab2:
        # [Keep the existing inventory chart code]
        st.markdown("### Active Inventory Value")
        locations = defaultdict(float)
        for r in rows:
            if r.get('HB.archived') != 'true':
                val = parse_float(r.get('HB.purchase_price', 0))
                loc = r.get('HB.location', 'Unknown')
                locations[loc] += val
        
        loc_df = pd.DataFrame(list(locations.items()), columns=['Location', 'Value'])
        if not loc_df.empty:
            fig_pie = px.pie(loc_df, values='Value', names='Location', title='Inventory Value by Location')
            st.plotly_chart(fig_pie, use_container_width=True)
            
    with tab_stale:
        st.markdown("### ⚠️ Stale Inventory (> 90 Days)")
        st.info("These items have been in inventory for more than 90 days. Consider discounting or promoting them.")
        
        stale_items = detail_data.get('stale_inventory', [])
        if stale_items:
            stale_df = pd.DataFrame([
                {
                    'Item': item.get('HB.name', ''),
                    'Cost': parse_float(item.get('HB.purchase_price', 0)),
                    'Days Held': item.get('days_held', 0),
                    'Location': item.get('HB.location', ''),
                    'Purchase Date': item.get('HB.purchase_time', '').split('T')[0] if item.get('HB.purchase_time') else ''
                }
                for item in stale_items
            ])
            
            st.metric("Stale Items Count", len(stale_items))
            st.metric("Stale Inventory Value", f"${sum(stale_df['Cost']):,.2f}")
            
            st.dataframe(
                stale_df.style.format({'Cost': "${:,.2f}"}).background_gradient(subset=['Days Held'], cmap='Reds'),
                use_container_width=True
            )
        else:
            st.success("No stale inventory found! Great job moving items quickly.")

    with tab3:
        st.markdown("### All Data")
        st.dataframe(pd.DataFrame(rows))

    with detailed_tab:
        render_detailed_tab(detail_data)