"""Generate the Power BI project (powerbi/KeralaVegPrices.pbip) from code.

Semantic model (TMDL): the reports/bi/*.csv tables loaded through Power Query, a DAX date table and
crop table, relationships in a star schema, and the DAX measures the report uses.
Report (PBIR): three pages, Overview, Markets, and Shocks & warning.

Run:  python powerbi/build_pbip.py      then open powerbi/KeralaVegPrices.pbip in Power BI Desktop.
The DataFolder parameter points at this checkout's reports/bi/ folder; rerun the script after moving
the repo (or edit the parameter in Power BI: Transform data > Manage parameters).
"""
import json
import shutil
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
NAME = "KeralaVegPrices"
MODEL, REPORT = HERE / f"{NAME}.SemanticModel", HERE / f"{NAME}.Report"
DATA_FOLDER = str(ROOT / "reports" / "bi") + "\\"
BASE_THEME = "CY24SU10"
DESKTOP_THEMES = Path(r"C:\Program Files\Microsoft Power BI Desktop\bin\WebView2Resources\minerva\sharedresources\BaseThemes")
SCHEMA = "https://developer.microsoft.com/json-schemas/fabric"
ACCENT, GREY, INK = "#8F1B5C", "#8A94A0", "#1B1F24"


def tag(*parts):
    """Stable lineage tags, so regenerating the project produces no spurious diffs."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "kerala-veg-prices/" + "/".join(parts)))


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def write_json(path, obj):
    write(path, json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


# ---------------- semantic model ----------------
M_TYPES = {"string": "type text", "int64": "Int64.Type", "double": "type number", "dateTime": "type date", "boolean": "type logical"}
FORMATS = {"dateTime": "yyyy-mm-dd", "double": "0.00", "int64": "0"}
COLUMN_FORMATS = {"hub_lead_days": "0", "rise_pct": "0.0"}

# table name -> (csv file, [(column, dataType)], [(measure, DAX, format)])
TABLES = {
    "Daily Price": ("daily_price.csv", [("date", "dateTime"), ("commodity", "string"), ("region", "string"),
                                        ("rs_per_kg", "double"), ("arrival_t", "double"), ("n_markets", "int64")], [
        ("Kerala Price", "CALCULATE(MEDIAN('Daily Price'[rs_per_kg]), 'Daily Price'[region] = \"Kerala\")", "0.0"),
        ("India Price", "CALCULATE(MEDIAN('Daily Price'[rs_per_kg]), 'Daily Price'[region] = \"All-India\")", "0.0"),
        ("Kerala Premium", "DIVIDE([Kerala Price], [India Price])", "0.0\"x\""),
    ]),
    "Market Month": ("market_month.csv", [("month", "dateTime"), ("commodity", "string"), ("market_key", "string"),
                                          ("rs_per_kg", "double"), ("days_reported", "int64"), ("arrival_t", "double")], [
        ("Market Price", "AVERAGE('Market Month'[rs_per_kg])", "0.0"),
        ("Kerala Market Median", "CALCULATE(MEDIANX(VALUES(Markets[market_key]), [Market Price]), ALL(Markets))", "0.0"),
        ("Gap vs Kerala Median", "IF(NOT ISBLANK([Market Price]), DIVIDE([Market Price], [Kerala Market Median]) - 1)", "+0%;-0%;0%"),
        ("Average Gap", "AVERAGEX(VALUES(Markets[market_key]), [Gap vs Kerala Median])", "+0%;-0%;0%"),
    ]),
    "Markets": ("markets.csv", [("market_key", "string"), ("market", "string"), ("district", "string"),
                                ("lat", "double"), ("lon", "double"), ("band", "string")], [
        ("Latitude", "AVERAGE(Markets[lat])", "0.00"),
    ]),
    "Hub Week": ("hub_week.csv", [("week", "dateTime"), ("kerala_rs_per_kg", "double"), ("hub_rs_per_kg", "double"),
                                  ("hub_arrivals", "double"), ("commodity", "string")], [
        ("Kerala Weekly", "AVERAGE('Hub Week'[kerala_rs_per_kg])", "0.0"),
        ("Hub Weekly", "AVERAGE('Hub Week'[hub_rs_per_kg])", "0.0"),
    ]),
    "Spike Events": ("spike_events.csv", [("event_id", "int64"), ("commodity", "string"), ("start", "dateTime"),
                                          ("peak", "dateTime"), ("price_start", "double"), ("price_peak", "double"),
                                          ("rise_pct", "double"), ("hub_start", "dateTime"), ("hub_lead_days", "double"),
                                          ("hub_first", "boolean")], [
        ("Spikes", "COUNTROWS('Spike Events')", "0"),
        ("Hub Spiked First", "CALCULATE([Spikes], 'Spike Events'[hub_first] = TRUE())", "0"),
        ("Median Hub Lead Days", "CALCULATE(MEDIAN('Spike Events'[hub_lead_days]), 'Spike Events'[hub_first] = TRUE())", "0.0"),
    ]),
    "Predictions": ("test_predictions.csv", [("date", "dateTime"), ("commodity", "string"), ("rs_per_kg", "double"),
                                             ("spike_ahead", "int64"), ("score", "double"), ("alert", "boolean")], [
        ("Warning Score", "MAX(Predictions[score])", "0.00"),
        ("Alert Threshold", "IF(NOT ISBLANK([Warning Score]), CALCULATE(MAX('Model Scores'[threshold]), 'Model Scores'[selected] = TRUE()))", "0.00"),
        ("Alert Days", "CALCULATE(COUNTROWS(Predictions), Predictions[alert] = TRUE())", "0"),
        ("Precision", "DIVIDE(CALCULATE(COUNTROWS(Predictions), Predictions[alert] = TRUE(), Predictions[spike_ahead] = 1), [Alert Days])", "0%"),
        ("Recall", "DIVIDE(CALCULATE(COUNTROWS(Predictions), Predictions[alert] = TRUE(), Predictions[spike_ahead] = 1), CALCULATE(COUNTROWS(Predictions), Predictions[spike_ahead] = 1))", "0%"),
    ]),
    "Model Scores": ("model_scores.csv", [("approach", "string"), ("kind", "string"), ("selected", "boolean"),
                                          ("threshold", "double"), ("test_pr_auc", "double"), ("test_precision", "double"),
                                          ("test_recall", "double"), ("test_f1", "double"), ("test_alerts", "int64"),
                                          ("test_base_rate", "double"), ("valid_pr_auc", "double")], []),
}
# (from table, from column, to table, to column)
RELATIONSHIPS = [
    ("Daily Price", "date", "Date", "Date"), ("Daily Price", "commodity", "Crop", "Crop"),
    ("Market Month", "month", "Date", "Date"), ("Market Month", "commodity", "Crop", "Crop"),
    ("Market Month", "market_key", "Markets", "market_key"),
    ("Hub Week", "week", "Date", "Date"), ("Hub Week", "commodity", "Crop", "Crop"),
    ("Spike Events", "start", "Date", "Date"), ("Spike Events", "commodity", "Crop", "Crop"),
    ("Predictions", "date", "Date", "Date"), ("Predictions", "commodity", "Crop", "Crop"),
]


def q(name):
    return f"'{name}'" if " " in name else name


def import_table(name, csv, cols, measures):
    out = [f"table {q(name)}", f"\tlineageTag: {tag(name)}", ""]
    for m, dax, fmt in measures:
        out += [f"\tmeasure {q(m)} = {dax}", f"\t\tformatString: {fmt}", f"\t\tlineageTag: {tag(name, m)}", ""]
    for c, t in cols:
        out += [f"\tcolumn {c}", f"\t\tdataType: {t}"]
        if t in FORMATS:
            out.append(f"\t\tformatString: {COLUMN_FORMATS.get(c, FORMATS[t])}")
        out += [f"\t\tlineageTag: {tag(name, c)}", f"\t\tsummarizeBy: none", f"\t\tsourceColumn: {c}", ""]
    types = ", ".join(f'{{"{c}", {M_TYPES[t]}}}' for c, t in cols)
    out += [
        f"\tpartition {q(name)} = m",
        "\t\tmode: import",
        "\t\tsource =",
        "\t\t\t\tlet",
        f'\t\t\t\t    Source = Csv.Document(File.Contents(DataFolder & "{csv}"), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),',
        "\t\t\t\t    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),",
        f'\t\t\t\t    Typed = Table.TransformColumnTypes(Promoted, {{{types}}}, "en-US")',
        "\t\t\t\tin",
        "\t\t\t\t    Typed",
        "",
    ]
    return "\n".join(out)


DATE_TABLE = f"""table Date
\tdataCategory: Time
\tlineageTag: {tag('Date')}

\tcolumn Date
\t\tdataType: dateTime
\t\tisKey
\t\tformatString: yyyy-mm-dd
\t\tlineageTag: {tag('Date', 'Date')}
\t\tsummarizeBy: none
\t\tisNameInferred
\t\tsourceColumn: [Date]

\tcolumn Year = YEAR('Date'[Date])
\t\tdataType: int64
\t\tformatString: 0
\t\tlineageTag: {tag('Date', 'Year')}
\t\tsummarizeBy: none

\tcolumn Month = DATE(YEAR('Date'[Date]), MONTH('Date'[Date]), 1)
\t\tdataType: dateTime
\t\tformatString: mmm yyyy
\t\tlineageTag: {tag('Date', 'Month')}
\t\tsummarizeBy: none

\tpartition Date = calculated
\t\tmode: import
\t\tsource = CALENDAR(DATE(2020, 12, 1), DATE(2026, 5, 31))
"""

CROP_TABLE = f"""table Crop
\tlineageTag: {tag('Crop')}

\tcolumn Crop
\t\tdataType: string
\t\tlineageTag: {tag('Crop', 'Crop')}
\t\tsummarizeBy: none
\t\tisNameInferred
\t\tsourceColumn: [Crop]

\tpartition Crop = calculated
\t\tmode: import
\t\tsource = DATATABLE("Crop", STRING, {{{{"Tomato"}}, {{"Onion"}}, {{"Potato"}}}})
"""


def build_model():
    d = MODEL / "definition"
    write_json(MODEL / ".platform", {"$schema": f"{SCHEMA}/gitIntegration/platformProperties/2.0.0/schema.json",
                                     "metadata": {"type": "SemanticModel", "displayName": NAME},
                                     "config": {"version": "2.0", "logicalId": tag("model")}})
    write_json(MODEL / "definition.pbism", {"$schema": f"{SCHEMA}/item/semanticModel/definitionProperties/1.0.0/schema.json",
                                            "version": "4.2", "settings": {}})
    write(d / "database.tmdl", "database\n\tcompatibilityLevel: 1600\n")
    names = ["Date", "Crop", *TABLES]
    write(d / "model.tmdl", "model Model\n\tculture: en-US\n\tdefaultPowerBIDataSourceVersion: powerBI_V3\n"
                            "\tsourceQueryCulture: en-US\n\tdataAccessOptions\n\t\tlegacyRedirects\n\t\treturnErrorValuesAsNull\n\n"
          + "".join(f"ref table {q(n)}\n" for n in names))
    write(d / "expressions.tmdl",
          f'expression DataFolder = "{DATA_FOLDER}" meta [IsParameterQuery = true, Type = "Text", IsParameterQueryRequired = true]\n'
          f"\tlineageTag: {tag('DataFolder')}\n")
    write(d / "tables" / "Date.tmdl", DATE_TABLE)
    write(d / "tables" / "Crop.tmdl", CROP_TABLE)
    for name, (csv, cols, measures) in TABLES.items():
        write(d / "tables" / f"{name}.tmdl", import_table(name, csv, cols, measures))
    write(d / "relationships.tmdl", "\n".join(
        f"relationship {tag('rel', a, b, c, e)}\n\tfromColumn: {q(a)}.{b}\n\ttoColumn: {q(c)}.{e}\n" for a, b, c, e in RELATIONSHIPS))


# ---------------- report ----------------
def lit(v):
    return {"expr": {"Literal": {"Value": v}}}


def field(entity, prop, measure=False):
    kind = "Measure" if measure else "Column"
    return {kind: {"Expression": {"SourceRef": {"Entity": entity}}, "Property": prop}}


def proj(entity, prop, measure=False, label=None):
    p = {"field": field(entity, prop, measure), "queryRef": f"{entity}.{prop}", "nativeQueryRef": prop}
    if label:
        p["displayName"] = label
    return p


def M(entity, prop, label=None):
    return proj(entity, prop, measure=True, label=label)


def C(entity, prop, label=None):
    return proj(entity, prop, label=label)


def title(text):
    return {"title": [{"properties": {"show": lit("true"), "text": lit(f"'{text}'"), "fontSize": lit("12D")}}]}


def visual(name, vtype, x, y, w, h, roles=None, heading=None, objects=None, sort=None):
    v = {"visualType": vtype, "drillFilterOtherVisuals": True}
    if roles:
        v["query"] = {"queryState": {role: {"projections": items} for role, items in roles.items()}}
    if sort:  # (projection, "Ascending" | "Descending")
        v["query"]["sortDefinition"] = {"sort": [{"field": sort[0]["field"], "direction": sort[1]}]}
    if objects:
        v["objects"] = objects
    if heading:
        v["visualContainerObjects"] = title(heading)
    return name, {"$schema": f"{SCHEMA}/item/report/definition/visualContainer/2.1.0/schema.json", "name": name,
                  "position": {"x": x, "y": y, "z": 0, "width": w, "height": h, "tabOrder": 0}, "visual": v}


def textbox(name, x, y, w, h, text, size="20pt", bold=True, color=INK):
    style = {"fontSize": size, "fontWeight": "bold" if bold else "normal", "color": color}
    return visual(name, "textbox", x, y, w, h, objects={"general": [{"properties": {"paragraphs": [
        {"textRuns": [{"value": text, "textStyle": style}]}]}}]})


def slicer(name, x, y, w, h, entity, column, heading):
    # The container title names the slicer, so hide the slicer's own header.
    return visual(name, "slicer", x, y, w, h, {"Values": [C(entity, column)]}, heading,
                  objects={"header": [{"properties": {"show": lit("false")}}]})


def card(name, x, y, w, entity, measure):
    return visual(name, "card", x, y, w, 110, {"Values": [M(entity, measure)]})


PAGES = [
    ("overview", "Overview", [
        textbox("title", 24, 12, 1100, 52, "Kerala pays more for vegetables, and pays later"),
        textbox("subtitle", 24, 58, 1000, 30, "Wholesale tomato, onion and potato prices, Jan 2021 to May 2026. Agmarknet via India Data Portal.", "11pt", False, "#5B6470"),
        slicer("crop", 24, 100, 180, 150, "Crop", "Crop", "Crop"),
        slicer("year", 24, 262, 180, 250, "Date", "Year", "Year"),
        card("keralaPrice", 224, 100, 250, "Daily Price", "Kerala Price"),
        card("indiaPrice", 490, 100, 250, "Daily Price", "India Price"),
        card("premium", 756, 100, 250, "Daily Price", "Kerala Premium"),
        card("spikes", 1022, 100, 234, "Spike Events", "Spikes"),
        visual("trend", "lineChart", 224, 226, 1032, 300, {"Category": [C("Date", "Month")],
               "Y": [M("Daily Price", "Kerala Price"), M("Daily Price", "India Price")]}, "Median wholesale price by month, Rs/kg"),
        visual("premiumByYear", "clusteredColumnChart", 224, 540, 1032, 164, {"Category": [C("Date", "Year")],
               "Y": [M("Daily Price", "Kerala Premium")]}, "Kerala pays, multiple of the all-India median, by year"),
    ]),
    ("markets", "Markets", [
        textbox("title", 24, 12, 1100, 52, "Nearby Kerala markets price the same crop very differently"),
        textbox("subtitle", 24, 58, 1000, 30, "Each market's average monthly median price, and its gap to the median Kerala market.", "11pt", False, "#5B6470"),
        slicer("crop", 24, 100, 180, 150, "Crop", "Crop", "Crop"),
        slicer("band", 24, 262, 180, 150, "Markets", "band", "Region band"),
        slicer("year", 24, 424, 180, 280, "Date", "Year", "Year"),
        visual("byBand", "clusteredColumnChart", 224, 100, 400, 260, {"Category": [C("Markets", "band")],
               "Y": [M("Market Month", "Average Gap")]}, "Average gap to the Kerala median, by region"),
        visual("latitude", "scatterChart", 640, 100, 616, 260, {"Category": [C("Markets", "market")],
               "X": [M("Markets", "Latitude")], "Y": [M("Market Month", "Gap vs Kerala Median")]}, "Gap vs latitude: the north is cheaper"),
        visual("marketTable", "tableEx", 224, 376, 1032, 328, {"Values": [C("Markets", "market", "Market"), C("Markets", "district", "District"),
               C("Markets", "band", "Region band"), M("Market Month", "Market Price", "Price, Rs/kg"), M("Market Month", "Gap vs Kerala Median", "Gap vs Kerala median")]},
               "Markets", sort=(M("Market Month", "Gap vs Kerala Median"), "Descending")),
    ]),
    ("warning", "Shocks & warning", [
        textbox("title", 24, 12, 1100, 52, "Spikes start at the hubs, about two weeks earlier"),
        textbox("subtitle", 24, 58, 1100, 30, "A spike: Kerala's price 30%+ higher 14 days later. The warning model was scored on Apr 2025 to May 2026, data it never saw.", "11pt", False, "#5B6470"),
        slicer("crop", 24, 100, 180, 150, "Crop", "Crop", "Crop"),
        card("spikes", 224, 100, 200, "Spike Events", "Spikes"),
        card("hubFirst", 434, 100, 200, "Spike Events", "Hub Spiked First"),
        card("lead", 644, 100, 200, "Spike Events", "Median Hub Lead Days"),
        card("precision", 854, 100, 196, "Predictions", "Precision"),
        card("recall", 1060, 100, 196, "Predictions", "Recall"),
        visual("score", "lineChart", 224, 226, 1032, 220, {"Category": [C("Date", "Date")],
               "Y": [M("Predictions", "Warning Score"), M("Predictions", "Alert Threshold")]}, "Highest warning score among the selected crops vs the alert threshold, test period"),
        visual("events", "tableEx", 24, 462, 600, 242, {"Values": [C("Spike Events", "commodity", "Crop"), C("Spike Events", "start", "Kerala start"),
               C("Spike Events", "peak", "Peak"), C("Spike Events", "rise_pct", "Rise %"), C("Spike Events", "hub_lead_days", "Hub lead (days)")]},
               "Spike events since 2021", sort=(C("Spike Events", "start"), "Descending")),
        visual("models", "tableEx", 640, 462, 616, 242, {"Values": [C("Model Scores", "approach", "Approach"), C("Model Scores", "kind", "Type"),
               C("Model Scores", "test_pr_auc", "PR-AUC"), C("Model Scores", "test_precision", "Precision"), C("Model Scores", "test_recall", "Recall")]},
               "Approaches compared on the test period (chance PR-AUC = 0.04)", sort=(C("Model Scores", "test_pr_auc"), "Descending")),
    ]),
]

THEME = {"name": "Kerala Almanac", "dataColors": [ACCENT, GREY, "#2C3A4A", "#C2669B", "#B8BFC7", "#5B6470"],
         "background": "#FFFFFF", "foreground": INK, "tableAccent": ACCENT,
         "textClasses": {"title": {"fontFace": "Segoe UI Semibold", "color": INK}}}


def build_report():
    write_json(REPORT / ".platform", {"$schema": f"{SCHEMA}/gitIntegration/platformProperties/2.0.0/schema.json",
                                      "metadata": {"type": "Report", "displayName": NAME},
                                      "config": {"version": "2.0", "logicalId": tag("report")}})
    write_json(REPORT / "definition.pbir", {"$schema": f"{SCHEMA}/item/report/definitionProperties/2.0.0/schema.json",
                                            "version": "4.0", "datasetReference": {"byPath": {"path": f"../{NAME}.SemanticModel"}}})
    res = REPORT / "StaticResources"
    (res / "SharedResources" / "BaseThemes").mkdir(parents=True, exist_ok=True)
    shutil.copy(DESKTOP_THEMES / f"{BASE_THEME}.json", res / "SharedResources" / "BaseThemes" / f"{BASE_THEME}.json")
    write_json(res / "RegisteredResources" / "kerala.json", THEME)
    d = REPORT / "definition"
    write_json(d / "version.json", {"$schema": f"{SCHEMA}/item/report/definition/versionMetadata/1.0.0/schema.json", "version": "2.0.0"})
    at_import = {"visual": "1.8.97", "report": "2.0.97", "page": "1.3.97"}
    write_json(d / "report.json", {
        "$schema": f"{SCHEMA}/item/report/definition/report/3.0.0/schema.json",
        "themeCollection": {"baseTheme": {"name": BASE_THEME, "reportVersionAtImport": at_import, "type": "SharedResources"},
                            "customTheme": {"name": "kerala.json", "reportVersionAtImport": at_import, "type": "RegisteredResources"}},
        "resourcePackages": [
            {"name": "SharedResources", "type": "SharedResources", "items": [{"name": BASE_THEME, "path": f"BaseThemes/{BASE_THEME}.json", "type": "BaseTheme"}]},
            {"name": "RegisteredResources", "type": "RegisteredResources", "items": [{"name": "kerala.json", "path": "kerala.json", "type": "CustomTheme"}]}],
        "settings": {"useStylableVisualContainerHeader": True, "defaultDrillFilterOtherVisuals": True, "useEnhancedTooltips": True},
    })
    shutil.rmtree(d / "pages", ignore_errors=True)
    write_json(d / "pages" / "pages.json", {"$schema": f"{SCHEMA}/item/report/definition/pagesMetadata/1.0.0/schema.json",
                                            "pageOrder": [p for p, _, _ in PAGES], "activePageName": PAGES[0][0]})
    for page, display, visuals in PAGES:
        write_json(d / "pages" / page / "page.json", {"$schema": f"{SCHEMA}/item/report/definition/page/1.4.0/schema.json",
                                                      "name": page, "displayName": display, "displayOption": "FitToPage",
                                                      "height": 720, "width": 1280})
        for z, (name, v) in enumerate(visuals):
            v["position"]["z"], v["position"]["tabOrder"] = z * 1000, z * 1000
            write_json(d / "pages" / page / "visuals" / name / "visual.json", v)


def main():
    shutil.rmtree(MODEL, ignore_errors=True)
    build_model()
    build_report()
    write_json(HERE / f"{NAME}.pbip", {"$schema": f"{SCHEMA}/pbip/pbipProperties/1.0.0/schema.json", "version": "1.0",
                                       "artifacts": [{"report": {"path": f"{NAME}.Report"}}], "settings": {"enableAutoRecovery": True}})
    write(HERE / ".gitignore", "**/.pbi/localSettings.json\n**/.pbi/cache.abf\n")
    print(f"wrote {HERE.relative_to(ROOT)}/{NAME}.pbip  (data folder: {DATA_FOLDER})")


if __name__ == "__main__":
    main()
