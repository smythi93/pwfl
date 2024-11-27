import sflkitlib.lib
sflkitlib.lib.add_test_line_event(10)
from middle import middle

def test_1():
    sflkitlib.lib.add_test_line_event(11)
    assert middle(1, 2, 3) == 2
    sflkitlib.lib.add_test_line_event(12)
    assert middle(3, 2, 1) == 2

def test_2():
    sflkitlib.lib.add_test_line_event(13)
    assert middle(3, 1, 2) == 2
    sflkitlib.lib.add_test_line_event(14)
    assert middle(2, 2, 1) == 2

def test_3():
    sflkitlib.lib.add_test_line_event(15)
    assert middle(2, 3, 1) == 2
    sflkitlib.lib.add_test_line_event(16)
    assert middle(2, 1, 3) == 2

def test_4():
    sflkitlib.lib.add_test_line_event(17)
    assert middle(2, 2, 3) == 2
    sflkitlib.lib.add_test_line_event(18)
    assert middle(1, 3, 2) == 2