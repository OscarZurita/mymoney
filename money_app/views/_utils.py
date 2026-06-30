from decimal import Decimal, InvalidOperation
import math

CHART_COLORS = [
    "#0b57d0",
    "#14b8a6",
    "#f59e0b",
    "#ec4899",
    "#8b5cf6",
    "#22c55e",
    "#ef4444",
    "#64748b",
]

def clamp(value, lower_bound, upper_bound):
    return max(lower_bound, min(value, upper_bound))


def format_decimal(value):
    decimal_value = value if isinstance(value, Decimal) else Decimal(str(value))
    quantized_value = decimal_value.quantize(Decimal("0.01"))
    if quantized_value == quantized_value.to_integral_value():
        return str(int(quantized_value))
    return format(quantized_value.normalize(), "f")


def format_percent(value):
    return format_decimal(value)


def polar_to_cartesian(center_x, center_y, radius, angle_degrees):
    angle_radians = math.radians(angle_degrees - 90)
    return (
        center_x + (radius * math.cos(angle_radians)),
        center_y + (radius * math.sin(angle_radians)),
    )


def format_point(x, y):
    return f"{format_decimal(x)},{format_decimal(y)}"


def donut_slice_path(start_percent, end_percent):
    center_x = 120
    center_y = 120
    outer_radius = 100
    inner_radius = 52
    start_angle = float((start_percent / Decimal("100")) * Decimal("360"))
    end_angle = float((end_percent / Decimal("100")) * Decimal("360"))

    if end_angle - start_angle >= 359.99:
        outer_start = polar_to_cartesian(center_x, center_y, outer_radius, 0)
        outer_mid = polar_to_cartesian(center_x, center_y, outer_radius, 180)
        inner_start = polar_to_cartesian(center_x, center_y, inner_radius, 0)
        inner_mid = polar_to_cartesian(center_x, center_y, inner_radius, 180)
        return (
            f"M {format_point(*outer_start)} "
            f"A {outer_radius} {outer_radius} 0 1 1 {format_point(*outer_mid)} "
            f"A {outer_radius} {outer_radius} 0 1 1 {format_point(*outer_start)} "
            f"M {format_point(*inner_start)} "
            f"A {inner_radius} {inner_radius} 0 1 0 {format_point(*inner_mid)} "
            f"A {inner_radius} {inner_radius} 0 1 0 {format_point(*inner_start)}"
        )

    outer_start = polar_to_cartesian(center_x, center_y, outer_radius, start_angle)
    outer_end = polar_to_cartesian(center_x, center_y, outer_radius, end_angle)
    inner_start = polar_to_cartesian(center_x, center_y, inner_radius, start_angle)
    inner_end = polar_to_cartesian(center_x, center_y, inner_radius, end_angle)
    large_arc = 1 if end_angle - start_angle > 180 else 0

    return (
        f"M {format_point(*outer_start)} "
        f"A {outer_radius} {outer_radius} 0 {large_arc} 1 {format_point(*outer_end)} "
        f"L {format_point(*inner_end)} "
        f"A {inner_radius} {inner_radius} 0 {large_arc} 0 {format_point(*inner_start)} "
        "Z"
    )


def parse_decimal(value):
    if not value:
        return None
    try:
        return Decimal(value)
    except (InvalidOperation, TypeError):
        return None


def sort_querystring(get_params, sort_value):
    params = get_params.copy()
    params["sort"] = sort_value
    return params.urlencode()


def parse_month_year(value):
    if not value or len(value) != 7 or value[4] != "-":
        return None, None
    year_part, month_part = value.split("-", 1)
    if not (year_part.isdigit() and month_part.isdigit()):
        return None, None
    month_int = int(month_part)
    if month_int < 1 or month_int > 12:
        return None, None
    return int(year_part), month_int




def build_monthly_chart(monthly_totals):
    if not monthly_totals:
        return None

    chart_width = Decimal("640")
    chart_height = Decimal("260")
    chart_left = Decimal("44")
    chart_right = Decimal("18")
    chart_top = Decimal("18")
    chart_bottom = Decimal("36")
    plot_width = chart_width - chart_left - chart_right
    plot_height = chart_height - chart_top - chart_bottom
    baseline_y = chart_top + plot_height

    max_total = max(row["total"] or Decimal("0") for row in monthly_totals)
    chart_max = max_total if max_total > 0 else Decimal("1")
    point_count = len(monthly_totals)
    chart_rows = []

    for index, row in enumerate(monthly_totals):
        total = row["total"] or Decimal("0")
        x_ratio = (
            Decimal("0.5")
            if point_count == 1
            else Decimal(index) / Decimal(point_count - 1)
        )
        y_ratio = total / chart_max
        x = chart_left + (plot_width * x_ratio)
        y = chart_top + (plot_height * (Decimal("1") - y_ratio))
        tooltip_width = Decimal("150")
        tooltip_height = Decimal("42")
        tooltip_x = clamp(
            x - (tooltip_width / Decimal("2")),
            Decimal("4"),
            chart_width - tooltip_width - Decimal("4"),
        )
        tooltip_y = y + Decimal("14") if y < Decimal("78") else y - tooltip_height - Decimal("12")

        chart_rows.append(
            {
                "month": row["month"],
                "total": total,
                "count": row["count"],
                "x": format_decimal(x),
                "y": format_decimal(y),
                "tooltip_x": format_decimal(tooltip_x),
                "tooltip_y": format_decimal(tooltip_y),
                "tooltip_text_x": format_decimal(tooltip_x + (tooltip_width / Decimal("2"))),
                "tooltip_title_y": format_decimal(tooltip_y + Decimal("16")),
                "tooltip_detail_y": format_decimal(tooltip_y + Decimal("31")),
            }
        )

    line_points = " ".join(f"{row['x']},{row['y']}" for row in chart_rows)
    area_points = (
        f"{chart_rows[0]['x']},{format_decimal(baseline_y)} "
        f"{line_points} "
        f"{chart_rows[-1]['x']},{format_decimal(baseline_y)}"
    )

    return {
        "rows": chart_rows,
        "line_points": line_points,
        "area_points": area_points,
        "max_total": max_total,
        "baseline_y": format_decimal(baseline_y),
    }

def build_category_chart(category_breakdown):
    if not category_breakdown:
        return None

    category_total = sum(
        (row["total"] or Decimal("0") for row in category_breakdown),
        Decimal("0"),
    )
    if category_total <= 0:
        return None

    chart_rows = []
    running_percent = Decimal("0")

    for index, row in enumerate(category_breakdown):
        total = row["total"] or Decimal("0")
        percent = (total / category_total) * Decimal("100")
        start_percent = running_percent
        running_percent += percent
        end_percent = (
            Decimal("100")
            if index == len(category_breakdown) - 1
            else running_percent
        )
        color = CHART_COLORS[index % len(CHART_COLORS)]
        name = row["category__name"] or "Uncategorized"
        midpoint_percent = (start_percent + end_percent) / Decimal("2")
        midpoint_angle = float((midpoint_percent / Decimal("100")) * Decimal("360"))
        tooltip_anchor = polar_to_cartesian(120, 120, 76, midpoint_angle)
        tooltip_width = 124
        tooltip_height = 48
        tooltip_x = clamp(tooltip_anchor[0] - (tooltip_width / 2), 4, 240 - tooltip_width - 4)
        tooltip_y = clamp(tooltip_anchor[1] - (tooltip_height / 2), 4, 240 - tooltip_height - 4)

        chart_rows.append(
            {
                "name": name,
                "total": total,
                "count": row["count"],
                "percent": format_percent(percent),
                "color": color,
                "path": donut_slice_path(start_percent, end_percent),
                "tooltip_x": format_decimal(tooltip_x),
                "tooltip_y": format_decimal(tooltip_y),
                "tooltip_text_x": format_decimal(tooltip_x + (tooltip_width / 2)),
                "tooltip_title_y": format_decimal(tooltip_y + 16),
                "tooltip_detail_y": format_decimal(tooltip_y + 32),
            }
        )

    return {
        "rows": chart_rows,
        "total": category_total,
    }
