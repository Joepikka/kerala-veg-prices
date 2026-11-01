"""Build the Excel workbook (reports/kerala_veg_prices.xlsx) from the BI tables in reports/bi/.

Every number on the Dashboard, Premium and Markets sheets is a live formula over Excel Tables
(AGGREGATE as a conditional median, AVERAGEIFS, COUNTIFS, XLOOKUP, INDEX/MATCH). The crop picker on
the Dashboard drives the KPIs and the line chart. The Checks sheet compares the formulas with the
values Python computed for the site.

On Windows with Excel installed, a second pass drives Excel itself (COM) to add a PivotTable with
slicers, recalculate, and confirm every check matches. Elsewhere that pass is skipped.
"""
import sys
from datetime import date

import pandas as pd
from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.formatting.rule import ColorScaleRule, DataBarRule, FormulaRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.table import Table, TableStyleInfo

from common import CROPS, OUT

BI = OUT / "bi"
XLSX = OUT / "kerala_veg_prices.xlsx"
FONT = "Arial"
START, END = date(2025, 6, 1), date(2026, 5, 31)  # the site's "last year" window
INK, ACCENT = "1B1F24", "8F1B5C"
INPUT_FILL = PatternFill("solid", fgColor="FFF2CC")


def font(**kw):
    return Font(name=FONT, **kw)


def style_sheet(ws):
    for row in ws.iter_rows():
        for c in row:
            if c.value is not None and c.font.name != FONT:
                c.font = Font(name=FONT, bold=c.font.bold, italic=c.font.italic, size=c.font.size,
                              color=c.font.color)


def add_table(wb, title, name, df, formats=None, widths=None):
    ws = wb.create_sheet(title)
    ws.append(list(df.columns))
    for rec in df.itertuples(index=False):
        ws.append([None if pd.isna(v) else v for v in rec])
    ref = f"A1:{get_column_letter(len(df.columns))}{len(df) + 1}"
    t = Table(displayName=name, ref=ref)
    t.tableStyleInfo = TableStyleInfo(name="TableStyleLight9", showRowStripes=True)
    ws.add_table(t)
    for col, fmt in (formats or {}).items():
        j = df.columns.get_loc(col) + 1
        for r in range(2, len(df) + 2):
            ws.cell(row=r, column=j).number_format = fmt
    for j, col in enumerate(df.columns, start=1):
        ws.column_dimensions[get_column_letter(j)].width = (widths or {}).get(col, max(12, len(col) + 2))
    ws.freeze_panes = "A2"
    return ws


def median_if(crop, region, start, end):
    """Conditional median of daily prices: AGGREGATE(16 = PERCENTILE.INC, 6 = ignore errors)."""
    return (f"_xlfn.AGGREGATE(16,6,Daily[rs_per_kg]/((Daily[commodity]={crop})*(Daily[region]=\"{region}\")"
            f"*(Daily[date]>={start})*(Daily[date]<={end})),0.5)")


def load():
    d = {n: pd.read_csv(BI / f"{n}.csv") for n in
         ("daily_price", "market_month", "markets", "spike_events", "model_scores", "test_predictions")}
    for n, cols in {"daily_price": ["date"], "market_month": ["month"], "spike_events": ["start", "peak", "hub_start"],
                    "test_predictions": ["date"]}.items():
        for c in cols:
            d[n][c] = pd.to_datetime(d[n][c]).dt.date
    mm = d["market_month"].merge(d["markets"][["market_key", "market", "district", "band"]], on="market_key")
    mm.insert(1, "year", pd.to_datetime(mm.month).dt.year)
    d["market_month"] = mm[["month", "year", "commodity", "market", "district", "band", "rs_per_kg", "days_reported",
                            "arrival_t", "market_key"]]
    return d


def expected(d):
    """The values the site reports, computed in pandas, for the Checks sheet."""
    p = d["daily_price"]
    w = p[(p.date >= START) & (p.date <= END)]
    med = w.groupby(["commodity", "region"]).rs_per_kg.median()
    s, t, m = d["spike_events"], d["test_predictions"], d["model_scores"]
    out = []
    for crop in CROPS:
        out.append((f"{crop}: Kerala median, Rs/kg", median_if(f'"{crop}"', "Kerala", "Dashboard!$B$6", "Dashboard!$B$7"),
                    med[crop, "Kerala"], "0.00"))
        out.append((f"{crop}: all-India median, Rs/kg", median_if(f'"{crop}"', "All-India", "Dashboard!$B$6", "Dashboard!$B$7"),
                    med[crop, "All-India"], "0.00"))
    out += [
        ("Spike events since 2021", "COUNTA(Spikes[event_id])", len(s), "0"),
        ("Hub spiked first", "COUNTIF(Spikes[hub_first],TRUE)", int(s.hub_first.sum()), "0"),
        ("Median hub lead, days", "_xlfn.AGGREGATE(16,6,Spikes[hub_lead_days]/Spikes[hub_first],0.5)",
         s[s.hub_first].hub_lead_days.median(), "0.0"),
        ("Warning precision (test)", "COUNTIFS(Predictions[alert],TRUE,Predictions[spike_ahead],1)/COUNTIF(Predictions[alert],TRUE)",
         t[t.alert].spike_ahead.mean(), "0.000"),
        ("Warning recall (test)", "COUNTIFS(Predictions[alert],TRUE,Predictions[spike_ahead],1)/SUM(Predictions[spike_ahead])",
         (t.alert & (t.spike_ahead == 1)).sum() / t.spike_ahead.sum(), "0.000"),
        ("Selected model test PR-AUC (XLOOKUP)", '_xlfn.XLOOKUP(TRUE,Models[selected],Models[test_pr_auc])',
         float(m[m.selected].test_pr_auc.iloc[0]), "0.000"),
    ]
    return out


def build(d):
    wb = Workbook()
    readme = wb.active
    readme.title = "Read me"
    dash = wb.create_sheet("Dashboard")
    prem = wb.create_sheet("Premium by year")
    mk = wb.create_sheet("Markets")
    wb.create_sheet("Market pivot")
    chk = wb.create_sheet("Checks")

    add_table(wb, "Daily prices", "Daily", d["daily_price"], {"date": "yyyy-mm-dd", "rs_per_kg": "0.00"})
    add_table(wb, "Market months", "MarketMonth", d["market_month"], {"month": "mmm yyyy", "rs_per_kg": "0.00"},
              {"market": 22, "district": 18, "band": 20, "market_key": 28})
    add_table(wb, "Spikes", "Spikes", d["spike_events"],
              {"start": "yyyy-mm-dd", "peak": "yyyy-mm-dd", "hub_start": "yyyy-mm-dd", "price_start": "0.00", "price_peak": "0.00"})
    ms = add_table(wb, "Model scores", "Models", d["model_scores"], {c: "0.000" for c in d["model_scores"].columns if c.startswith(("test_p", "test_r", "test_f", "valid"))},
                   {"approach": 44})
    n = len(d["model_scores"]) + 1
    ms.conditional_formatting.add(f"E2:E{n}", DataBarRule(start_type="num", start_value=0, end_type="num", end_value=0.5, color="8F1B5C"))
    ms.conditional_formatting.add(f"A2:K{n}", FormulaRule(formula=["$C2=TRUE"], font=Font(name=FONT, bold=True, color=ACCENT)))
    add_table(wb, "Predictions", "Predictions", d["test_predictions"], {"date": "yyyy-mm-dd", "rs_per_kg": "0.00", "score": "0.0000"})

    # Read me
    readme.column_dimensions["A"].width = 110
    lines = [
        ("Kerala vegetable prices: Excel workbook", font(bold=True, size=16, color=INK)),
        ("How much more Kerala pays for tomato, onion and potato, where its markets disagree, and how early a price spike can be seen.", font(size=11)),
        ("", None),
        ("Sheets", font(bold=True, size=12)),
        ("Dashboard: pick a crop in the yellow cell; the KPIs and the monthly chart follow it. Dates are editable too.", font()),
        ("Premium by year: Kerala median price divided by the all-India median, per calendar year, with a colour scale.", font()),
        ("Markets: each Kerala market's average monthly price per crop and its gap to the Kerala median (formula columns).", font()),
        ("Market pivot: a PivotTable of average price by district and crop, with slicers for region band and year.", font()),
        ("Checks: the site's headline numbers recomputed with Excel formulas, each compared with the Python value.", font()),
        ("Data sheets (Daily prices, Market months, Spikes, Model scores, Predictions) are Excel Tables: Insert > PivotTable on any of them.", font()),
        ("", None),
        ("Source", font(bold=True, size=12)),
        ("Agmarknet wholesale records via the India Data Portal (ISB), ODC-By licence, Jan 2021 to May 2026, cleaned in DuckDB. Prices are wholesale, in Rs/kg.", font()),
        ("Built by pipeline/60_excel.py from reports/bi/*.csv. Code: https://github.com/Joepikka/kerala-veg-prices", font()),
    ]
    for i, (text, f) in enumerate(lines, start=1):
        readme.cell(row=i, column=1, value=text)
        if f:
            readme.cell(row=i, column=1).font = f
        readme.cell(row=i, column=1).alignment = Alignment(wrap_text=True, vertical="top")

    # Dashboard: inputs
    dash["A1"] = "Kerala vs all-India wholesale price"
    dash["A1"].font = font(bold=True, size=16, color=INK)
    dash["A2"] = "Change the yellow cells. Everything else is a formula."
    dash["A2"].font = font(italic=True, color="5B6470")
    for r, (label, value, fmt) in enumerate([("Crop", "Tomato", None), ("", None, None), ("From", START, "yyyy-mm-dd"),
                                              ("To", END, "yyyy-mm-dd")], start=4):
        if not label:
            continue
        dash.cell(row=r, column=1, value=label).font = font(bold=True)
        c = dash.cell(row=r, column=2, value=value)
        c.fill, c.font = INPUT_FILL, font(color="0000FF")
        if fmt:
            c.number_format = fmt
    dv = DataValidation(type="list", formula1='"Tomato,Onion,Potato"', allow_blank=False)
    dash.add_data_validation(dv)
    dv.add("B4")  # B6:B7 hold From/To; the formulas and checks below reference them

    kpis = [
        ("Kerala median, Rs/kg", "=" + median_if("$B$4", "Kerala", "$B$6", "$B$7"), "0.0"),
        ("All-India median, Rs/kg", "=" + median_if("$B$4", "All-India", "$B$6", "$B$7"), "0.0"),
        ("Kerala pays", "=B10/B11", '0.0"x"'),
        ("Spike events since 2021", "=COUNTIFS(Spikes[commodity],$B$4)", "0"),
        ("Hub spiked first", "=COUNTIFS(Spikes[commodity],$B$4,Spikes[hub_first],TRUE)", "0"),
        ("Median hub lead, days", "=IFERROR(_xlfn.AGGREGATE(16,6,Spikes[hub_lead_days]/(Spikes[hub_first]*(Spikes[commodity]=$B$4)),0.5),\"-\")", "0.0"),
    ]
    dash["A9"] = "Selected crop, selected dates"
    dash["A9"].font = font(bold=True, size=12)
    for r, (label, f, fmt) in enumerate(kpis, start=10):
        dash.cell(row=r, column=1, value=label).font = font()
        c = dash.cell(row=r, column=2, value=f)
        c.number_format, c.font = fmt, font(bold=True, size=12, color=ACCENT if r == 12 else INK)
    dash.column_dimensions["A"].width = 28
    dash.column_dimensions["B"].width = 14

    # All three crops side by side, for the bar chart
    dash["A18"] = "All crops, selected dates"
    dash["A18"].font = font(bold=True, size=12)
    for j, h in enumerate(["Crop", "Kerala", "All-India", "Kerala pays"], start=1):
        dash.cell(row=19, column=j, value=h).font = font(bold=True)
    for i, crop in enumerate(CROPS, start=20):
        dash.cell(row=i, column=1, value=crop).font = font()
        dash.cell(row=i, column=2, value="=" + median_if(f"$A{i}", "Kerala", "$B$6", "$B$7")).number_format = "0.0"
        dash.cell(row=i, column=3, value="=" + median_if(f"$A{i}", "All-India", "$B$6", "$B$7")).number_format = "0.0"
        dash.cell(row=i, column=4, value=f"=B{i}/C{i}").number_format = '0.0"x"'
    dash.column_dimensions["C"].width = dash.column_dimensions["D"].width = 12

    months = sorted({m.replace(day=1) for m in d["daily_price"].date})
    # Chart data: monthly averages for the selected crop, kept to the right of the dashboard (columns X:Z)
    T = 24  # column X
    dash.cell(row=1, column=T, value="Chart data: monthly average, selected crop").font = font(bold=True)
    for j, h in enumerate(["Month", "Kerala", "All-India"], start=T):
        dash.cell(row=2, column=j, value=h).font = font(bold=True)
    for i, m in enumerate(months, start=3):
        dash.cell(row=i, column=T, value=m).number_format = "mmm yy"
        for j, reg in ((T + 1, "Kerala"), (T + 2, "All-India")):
            dash.cell(row=i, column=j, value=(f'=AVERAGEIFS(Daily[rs_per_kg],Daily[commodity],$B$4,Daily[region],"{reg}",'
                                              f'Daily[date],">="&$X{i},Daily[date],"<="&EOMONTH($X{i},0))')).number_format = "0.0"
    last = 2 + len(months)

    line = LineChart()
    line.title, line.height, line.width = "Monthly wholesale price, Rs/kg (selected crop)", 9.5, 24
    line.y_axis.majorGridlines = None
    line.add_data(Reference(dash, min_col=T + 1, max_col=T + 2, min_row=2, max_row=last), titles_from_data=True)
    line.set_categories(Reference(dash, min_col=T, min_row=3, max_row=last))
    line.x_axis.number_format, line.x_axis.tickLblSkip = "mmm yy", 6
    line.x_axis.delete = line.y_axis.delete = False
    line.legend.position, line.legend.overlay = "b", False
    for s, color in zip(line.series, (ACCENT, "8A94A0")):
        s.graphicalProperties.line.solidFill, s.graphicalProperties.line.width, s.smooth = color, 22000, False
    dash.add_chart(line, "F3")

    bar = BarChart()
    bar.type, bar.title, bar.height, bar.width = "col", "Kerala pays, multiple of all-India median (selected dates)", 7.5, 12
    bar.add_data(Reference(dash, min_col=4, min_row=19, max_row=22), titles_from_data=True)
    bar.set_categories(Reference(dash, min_col=1, min_row=20, max_row=22))
    bar.legend, bar.y_axis.majorGridlines = None, None
    bar.x_axis.delete = bar.y_axis.delete = False
    bar.series[0].graphicalProperties.solidFill = ACCENT
    dash.add_chart(bar, "F23")

    # Premium by year crosstab
    prem["A1"] = "Kerala pays, multiple of the all-India median, by year"
    prem["A1"].font = font(bold=True, size=14, color=INK)
    prem["A2"] = "Kerala median daily price / all-India median daily price, each calendar year (2026 is Jan to May)."
    prem["A2"].font = font(italic=True, color="5B6470")
    prem.cell(row=4, column=1, value="Year").font = font(bold=True)
    for j, crop in enumerate(CROPS, start=2):
        prem.cell(row=4, column=j, value=crop).font = font(bold=True)
    for i, y in enumerate(range(2021, 2027), start=5):
        prem.cell(row=i, column=1, value=y).font = font()
        for j in range(2, 2 + len(CROPS)):
            col = get_column_letter(j)
            k = median_if(f"{col}$4", "Kerala", f"DATE($A{i},1,1)", f"DATE($A{i},12,31)")
            a = median_if(f"{col}$4", "All-India", f"DATE($A{i},1,1)", f"DATE($A{i},12,31)")
            prem.cell(row=i, column=j, value=f"={k}/{a}").number_format = '0.00"x"'
    prem.conditional_formatting.add("B5:D10", ColorScaleRule(start_type="min", start_color="F3F4F6", end_type="max", end_color="C2669B"))
    prem.column_dimensions["A"].width = 10
    for col in "BCD":
        prem.column_dimensions[col].width = 12

    # Markets: formula columns over MarketMonth
    mk["A1"] = "Kerala markets: average monthly price per crop, selected dates"
    mk["A1"].font = font(bold=True, size=14, color=INK)
    mk["A2"] = "Average of each market's monthly median between Dashboard!B6 and B7. Gap = market vs the median of all markets. Blank = fewer than 3 months reported."
    mk["A2"].font = font(italic=True, color="5B6470")
    heads = ["Market", "District", "Band", "Latitude", "Tomato", "Onion", "Potato", "Tomato gap", "Onion gap", "Potato gap"]
    for j, h in enumerate(heads, start=1):
        mk.cell(row=4, column=j, value=h).font = font(bold=True)
    mkts = d["markets"].sort_values("lat", ascending=False)
    first = 5
    lastm = first + len(mkts) - 1
    for i, rec in enumerate(mkts.itertuples(), start=first):
        mk.cell(row=i, column=1, value=rec.market)
        mk.cell(row=i, column=2, value=rec.district)
        mk.cell(row=i, column=3, value=rec.band)
        mk.cell(row=i, column=4, value=rec.lat).number_format = "0.00"
        for j, crop in enumerate(CROPS, start=5):
            cond = (f'MarketMonth[market],$A{i},MarketMonth[commodity],"{crop}",'
                    f'MarketMonth[month],">="&Dashboard!$B$6,MarketMonth[month],"<="&Dashboard!$B$7')
            mk.cell(row=i, column=j, value=f'=IF(COUNTIFS({cond})>=3,AVERAGEIFS(MarketMonth[rs_per_kg],{cond}),"")').number_format = "0.0"
            col = get_column_letter(j)
            mk.cell(row=i, column=j + 3, value=f'=IF({col}{i}="","",{col}{i}/MEDIAN({col}${first}:{col}${lastm})-1)').number_format = "+0%;-0%;0%"
    mk.conditional_formatting.add(f"H{first}:J{lastm}", ColorScaleRule(start_type="num", start_value=-0.3, start_color="2C3A4A",
                                                                       mid_type="num", mid_value=0, mid_color="FFFFFF",
                                                                       end_type="num", end_value=0.3, end_color="8F1B5C"))
    # Band summary: the north-south finding as AVERAGEIFS over the gap column
    mk["L4"], mk["M4"] = "Band", "Avg tomato gap"
    mk["L4"].font = mk["M4"].font = font(bold=True)
    for i, b in enumerate(["North (above 11°N)", "Central", "South (below 9.5°N)"], start=5):
        mk.cell(row=i, column=12, value=b)
        mk.cell(row=i, column=13, value=f'=AVERAGEIFS($H${first}:$H${lastm},$C${first}:$C${lastm},L{i})').number_format = "+0%;-0%;0%"
    widths = {"A": 24, "B": 18, "C": 20, "D": 10, "L": 22, "M": 16}
    for col, w in widths.items():
        mk.column_dimensions[col].width = w
    mk.freeze_panes = "B5"

    # Pivot sheet header (the PivotTable itself is added through Excel in finish_in_excel)
    pv = wb["Market pivot"]
    pv["A1"] = "Average wholesale price by district and crop, Rs/kg"
    pv["A1"].font = font(bold=True, size=14, color=INK)
    pv["A2"] = "PivotTable over the Market months table. Use the slicers to filter by region band and year."
    pv["A2"].font = font(italic=True, color="5B6470")

    # Checks
    chk["A1"] = "Checks: Excel formulas vs the values on the site (Python)"
    chk["A1"].font = font(bold=True, size=14, color=INK)
    for j, h in enumerate(["Metric", "Excel formula", "Python value", "Match?"], start=1):
        chk.cell(row=3, column=j, value=h).font = font(bold=True)
    rows = expected(d)
    for i, (label, f, value, fmt) in enumerate(rows, start=4):
        chk.cell(row=i, column=1, value=label)
        chk.cell(row=i, column=2, value="=" + f).number_format = fmt
        chk.cell(row=i, column=3, value=float(value)).number_format = fmt
        chk.cell(row=i, column=4, value=f'=IF(ABS(B{i}-C{i})<0.0005,"yes","NO")')
    chk.conditional_formatting.add(f"D4:D{3 + len(rows)}", FormulaRule(formula=['D4="NO"'], font=Font(name=FONT, bold=True, color="C00000")))
    chk.column_dimensions["A"].width = 40
    chk.column_dimensions["B"].width = chk.column_dimensions["C"].width = 16

    for ws in wb.worksheets:
        style_sheet(ws)
        ws.sheet_view.showGridLines = ws.title in ("Daily prices", "Market months", "Spikes", "Model scores", "Predictions")
    wb.active = 1
    wb.save(XLSX)
    return len(rows)


def finish_in_excel(n_checks):
    try:
        import win32com.client as win32
    except ImportError:
        print("pywin32 not installed: skipped the PivotTable and the Excel recalculation check")
        return
    xl = win32.DispatchEx("Excel.Application")
    xl.Visible, xl.DisplayAlerts = False, False
    try:
        wb = xl.Workbooks.Open(str(XLSX.resolve()))
        ws = wb.Worksheets("Market pivot")
        cache = wb.PivotCaches().Create(SourceType=1, SourceData="MarketMonth")  # 1 = xlDatabase
        pt = cache.CreatePivotTable(TableDestination=ws.Range("A5"), TableName="DistrictPrices")
        pt.PivotFields("district").Orientation = 1  # row
        pt.PivotFields("commodity").Orientation = 2  # column
        field = pt.AddDataField(pt.PivotFields("rs_per_kg"), "Average Rs/kg ", -4106)  # -4106 = xlAverage
        field.NumberFormat = "0.0"
        pt.TableStyle2 = "PivotStyleLight16"
        pt.CompactLayoutRowHeader, pt.CompactLayoutColumnHeader = "District", "Crop"
        ws.Columns("A").ColumnWidth = 24
        left = ws.Range("G1").Left
        for k, (name, caption, height) in enumerate((("band", "Region band", 110), ("year", "Year", 175))):
            sc = wb.SlicerCaches.Add2(pt, name)
            slicer = sc.Slicers.Add(SlicerDestination=ws, Name=f"{name}_slicer", Caption=caption)
            # Add() ignores its position arguments here, so place each slicer afterwards.
            slicer.Caption, slicer.Top, slicer.Left = caption, ws.Range("A5").Top + k * 125, left
            slicer.Width, slicer.Height = 160, height
        xl.CalculateFull()
        chk = wb.Worksheets("Checks")
        bad = [chk.Cells(r, 1).Value for r in range(4, 4 + n_checks) if chk.Cells(r, 4).Value != "yes"]
        wb.Worksheets("Dashboard").Activate()
        wb.Save()
        wb.Close()
    finally:
        xl.Quit()
    print(f"Excel recalculated: {n_checks - len(bad)}/{n_checks} checks match")
    if bad:
        sys.exit(f"checks failed: {bad}")


def main():
    n = build(load())
    finish_in_excel(n)
    print(f"wrote {XLSX.relative_to(OUT.parent)}")


if __name__ == "__main__":
    main()
