from middle import middle

def test_1():
    assert middle(1, 2, 3) == 2
    assert middle(3, 2, 1) == 2

def test_2():
    assert middle(3, 1, 2) == 2
    assert middle(2, 2, 1) == 2

def test_3():
    assert middle(2, 3, 1) == 2
    assert middle(2, 1, 3) == 2

def test_4():
    assert middle(2, 2, 3) == 2
    assert middle(1, 3, 2) == 2

