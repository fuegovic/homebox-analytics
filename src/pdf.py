from io import BytesIO
from typing import Iterable, Optional, Tuple

import plotly.graph_objects as go
from fpdf import FPDF


def _format_currency(value: float) -> str:
    return f"${value:,.2f}"


def _format_percent(value: float) -> str:
    return f"{value:,.1f}%"


def _build_financial_chart(detail_data: dict) -> Optional[BytesIO]:
    """Create a compact revenue/expense bar chart for the PDF."""
    try:
        measures = [
            detail_data.get("product_revenue", 0),
            detail_data.get("service_revenue", 0),
            detail_data.get("cogs", 0),
            detail_data.get("total_profit", 0),
        ]
        labels = ["Product Revenue", "Service Revenue", "COGS", "Total Profit"]
        colors = ["#1f77b4", "#00cc96", "#ef553b", "#636efa"]

        fig = go.Figure(
            go.Bar(
                x=measures,
                y=labels,
                orientation="h",
                marker_color=colors,
                text=[_format_currency(v) for v in measures],
                textposition="outside",
            )
        )
        fig.update_layout(
            height=360,
            width=900,
            margin=dict(l=20, r=20, t=20, b=20),
            template="plotly_white",
            xaxis_title="USD",
        )

        img_bytes = fig.to_image(format="png", width=900, height=360, scale=2)
        stream = BytesIO(img_bytes)
        stream.seek(0)
        return stream
    except Exception:
        return None


def _add_section(pdf: FPDF, title: str, rows: Iterable[Tuple[str, str]]) -> None:
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, title, ln=True)
    pdf.set_font("Helvetica", size=10)
    text_width = pdf.w - pdf.l_margin - pdf.r_margin
    for label, value in rows:
        pdf.set_text_color(60)
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(text_width, 6, f"{label}: {value}")
    pdf.ln(1)


def generate_accountant_pdf(detail_data: dict) -> bytes:
    """Return a single-page PDF summarizing the financials for accountants."""
    pdf = FPDF(unit="mm", format="Letter")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    start_date = detail_data.get('start_date')
    end_date = detail_data.get('end_date')
    if start_date and end_date:
        period = f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}"
    else:
        period = "Unknown Period"

    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "Homebox Financial Summary", ln=True)
    pdf.set_font("Helvetica", size=11)
    pdf.cell(0, 6, f"Accounting Period: {period}", ln=True)
    pdf.ln(2)

    financial_rows = [
        ("Product Revenue", _format_currency(detail_data.get("product_revenue", 0))),
        ("Service Revenue", _format_currency(detail_data.get("service_revenue", 0))),
        ("Total Revenue", _format_currency(detail_data.get("total_revenue", 0))),
        ("Cost of Goods Sold", _format_currency(detail_data.get("cogs", 0))),
        ("Total Profit", _format_currency(detail_data.get("total_profit", 0))),
    ]
    _add_section(pdf, "Revenue & Profit", financial_rows)

    expense_rows = [
        ("Business Operating Expenses", _format_currency(detail_data.get("business_expenses", 0))),
        ("Total Expenses", _format_currency(detail_data.get("total_expenses", 0))),
        ("Loss / Giveaways", _format_currency(detail_data.get("loss_value", 0))),
    ]
    _add_section(pdf, "Expense Overview", expense_rows)

    ratio_rows = [
        ("Average ROI", _format_percent(detail_data.get("avg_roi", 0))),
        ("Avg Profit per Item", _format_currency(detail_data.get("avg_profit_per_item", 0))),
        ("Avg Sale Price", _format_currency(detail_data.get("avg_sale_price", 0))),
        ("Items Sold", str(detail_data.get("items_sold", 0))),
        ("Service Revenue Items", str(len(detail_data.get("other_income_items", [])))),
        ("Quick Flips (<=14 days)", str(detail_data.get("quick_flips", 0))),
    ]
    _add_section(pdf, "Key Ratios & Velocity", ratio_rows)

    inventory_rows = [
        ("Active Inventory Cost", _format_currency(detail_data.get("active_inventory_value", 0))),
        ("Total Active Inventory", _format_currency(detail_data.get("total_active_value", 0))),
        (
            "Projected Revenue (Avg ROI)",
            _format_currency(
                detail_data.get("total_active_value", 0)
                * (1 + max(detail_data.get("avg_roi", 0), 0) / 100)
            ),
        ),
        ("Business Assets", _format_currency(detail_data.get("business_assets_value", 0))),
        ("Marketplace Cost Basis", _format_currency(detail_data.get("marketplace_value", 0))),
    ]
    _add_section(pdf, "Inventory & Assets", inventory_rows)

    chart_stream = _build_financial_chart(detail_data)
    if chart_stream:
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, "Financial Mix Snapshot", ln=True)
        usable_width = getattr(pdf, "epw", pdf.w - pdf.l_margin - pdf.r_margin)
        usable_width = min(usable_width, 170)
        try:
            pdf.image(chart_stream, x=pdf.l_margin, w=usable_width)
            pdf.ln(2)
        except Exception:
            pdf.set_font("Helvetica", size=9)
            pdf.multi_cell(0, 4, "Chart unavailable in PDF rendering context.")

    pdf.set_font("Helvetica", size=9)
    pdf.set_text_color(100)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(
        pdf.w - pdf.l_margin - pdf.r_margin,
        4,
        "Notes: Service revenue counts as pure profit."
    )

    output = pdf.output(dest="S")
    if isinstance(output, (bytes, bytearray)):
        return bytes(output)
    return output.encode("latin1")
