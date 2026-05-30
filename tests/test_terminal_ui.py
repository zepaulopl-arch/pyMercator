from pymercator import terminal_ui as ui


def test_kv_alignment():
    line = ui.kv("TEST_LABEL", "value", label_width=16)
    assert line.startswith("TEST_LABEL")


def test_short_path_truncation():
    long = "/this/is/a/very/long/path/that/should/be/shortened/for/display/purposes/file.csv"
    s = ui.short_path(long, max_len=30)
    assert "..." in s


def test_render_table_basic():
    rows = [{"a": 1, "b": 2}, {"a": 3, "b": 4}]
    txt = ui.render_table(rows, ["a", "b"])    
    assert "a" in txt and "b" in txt
