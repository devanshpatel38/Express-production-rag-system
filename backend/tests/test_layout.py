from app.ingestion.pdf_layout import Block, order_blocks


def B(x0, y0, x1, y1, text):
    return Block(x0=x0, y0=y0, x1=x1, y1=y1, text=text)


def test_two_column_reading_order():
    # left blocks x-center ~150, right ~460; interleaved y
    blocks = [B(400,60,560,80,"R1"), B(60,60,250,80,"L1"),
              B(400,100,560,120,"R2"), B(60,100,250,120,"L2")]
    assert [b.text for b in order_blocks(blocks, 612)] == ["L1","L2","R1","R2"]


def test_single_column_passthrough():
    blocks = [B(60,100,550,120,"P2"), B(60,60,550,80,"P1")]
    assert [b.text for b in order_blocks(blocks, 612)] == ["P1","P2"]
