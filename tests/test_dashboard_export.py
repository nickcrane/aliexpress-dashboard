import io

import pandas as pd
from openpyxl import load_workbook

from aliexpress_dashboard.dashboard.export import to_csv_bytes, to_xlsx_bytes


def _sample_df():
    return pd.DataFrame(
        {
            "product_id": [1, 2],
            "product_title": ["Widget", "Gadget"],
            "target_sale_price": [6.99, 9.99],
        }
    )


def test_to_csv_bytes_round_trips():
    csv_bytes = to_csv_bytes(_sample_df())
    df = pd.read_csv(io.BytesIO(csv_bytes))
    assert list(df["product_title"]) == ["Widget", "Gadget"]


def test_to_xlsx_bytes_is_a_valid_workbook():
    xlsx_bytes = to_xlsx_bytes(_sample_df())
    workbook = load_workbook(io.BytesIO(xlsx_bytes))
    sheet = workbook["products"]
    rows = list(sheet.values)
    assert rows[0] == ("product_id", "product_title", "target_sale_price")
    assert rows[1] == (1, "Widget", 6.99)
