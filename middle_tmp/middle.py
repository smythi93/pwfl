import sflkitlib.lib

def middle(x, y, z):
    sflkitlib.lib.add_line_event(0)
    if y < z:
        sflkitlib.lib.add_line_event(1)
        if x < y:
            sflkitlib.lib.add_line_event(2)
            return y
        else:
            sflkitlib.lib.add_line_event(3)
            if x < z:
                sflkitlib.lib.add_line_event(4)
                return y
    else:
        sflkitlib.lib.add_line_event(5)
        if x > y:
            sflkitlib.lib.add_line_event(6)
            return y
        else:
            sflkitlib.lib.add_line_event(7)
            if x > z:
                sflkitlib.lib.add_line_event(8)
                return x
    sflkitlib.lib.add_line_event(9)
    return z