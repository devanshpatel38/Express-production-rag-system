from app.ingestion.pdf_layout import Block, order_blocks

W = 612


def texts(bs):
    return [b.text for b in bs]


def test_two_column_reading_order():
    blocks = [
        Block(60, 100, 240, 120, "L1"),
        Block(370, 100, 550, 120, "R1"),
        Block(60, 200, 240, 220, "L2"),
        Block(370, 200, 550, 220, "R2"),
    ]
    assert texts(order_blocks(blocks, W)) == ["L1", "L2", "R1", "R2"]


def test_single_column_passthrough():
    blocks = [
        Block(60, 300, 200, 320, "C"),
        Block(60, 100, 200, 120, "A"),
        Block(60, 200, 200, 220, "B"),
    ]
    assert texts(order_blocks(blocks, W)) == ["A", "B", "C"]


def test_single_column_with_centered_title_and_fullwidth_body():
    blocks = [
        Block(60, 300, 100, 320, "short"),
        Block(50, 150, 560, 250, "body"),
        Block(200, 50, 400, 80, "title"),
    ]
    assert texts(order_blocks(blocks, W)) == ["title", "body", "short"]


def test_two_column_with_fullwidth_title_on_top():
    blocks = [
        Block(60, 100, 240, 120, "L1"),
        Block(370, 100, 550, 120, "R1"),
        Block(60, 200, 240, 220, "L2"),
        Block(370, 200, 550, 220, "R2"),
        Block(50, 40, 560, 70, "TITLE"),
    ]
    assert texts(order_blocks(blocks, W)) == ["TITLE", "L1", "L2", "R1", "R2"]


def test_empty_input():
    assert order_blocks([], W) == []
