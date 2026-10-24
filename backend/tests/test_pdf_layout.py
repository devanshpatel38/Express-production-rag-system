from app.ingestion.pdf_layout import order_blocks
from app.ingestion.pdf_spans import Block

W = 600.0


def B(x0, y0, x1, y1, t):
    return Block(x0, y0, x1, y1, t)


def texts(bs):
    return [b.text for b in bs]


def test_two_columns_left_before_right():
    blocks = [
        B(320, 100, 550, 150, "R1"),
        B(50, 100, 280, 150, "L1"),
        B(320, 160, 550, 210, "R2"),
        B(50, 160, 280, 210, "L2"),
    ]
    assert texts(order_blocks(blocks, W)) == ["L1", "L2", "R1", "R2"]


def test_full_width_heading_stays_above_and_bands_order():
    blocks = [
        B(320, 100, 550, 150, "R1"),
        B(50, 100, 280, 150, "L1"),
        B(50, 40, 550, 80, "H1"),
        B(50, 300, 550, 330, "H2"),
        B(320, 340, 550, 400, "R3"),
        B(50, 340, 280, 400, "L3"),
    ]
    assert texts(order_blocks(blocks, W)) == ["H1", "L1", "R1", "H2", "L3", "R3"]


def test_off_center_gutter_derived_from_extents():
    blocks = [
        B(200, 100, 580, 150, "R1"),
        B(20, 100, 150, 150, "L1"),
        B(20, 160, 150, 210, "L2"),
        B(200, 160, 580, 210, "R2"),
    ]
    assert texts(order_blocks(blocks, W)) == ["L1", "L2", "R1", "R2"]


def test_single_column_unchanged():
    blocks = [B(50, 50 + i * 40, 550, 80 + i * 40, f"P{i}") for i in range(5)]
    assert order_blocks(blocks, W) == blocks


def test_empty_and_single():
    assert order_blocks([], W) == []
    one = [B(50, 50, 550, 80, "only")]
    assert order_blocks(one, W) == one
