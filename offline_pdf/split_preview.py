"""Boundary geometry shared by the unified page grid."""


def separator_line(boundary, columns, cellw, cellh):
    row, column = divmod(boundary, columns)
    if column:
        x = column * cellw
        return x, row * cellh + 8, x, (row + 1) * cellh - 16
    y = row * cellh - 6
    return 8, y, columns * cellw - 8, y
