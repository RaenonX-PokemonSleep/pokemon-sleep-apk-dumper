"""Small abstract values used by the native initializer reader."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Value:
    kind: str
    value: object
    offset: int = 0

    def add(self, offset):
        if self.kind == 'address':
            return Value('address', self.value + offset)
        return Value(self.kind, self.value, self.offset + offset)


def load(binary, base, offset):
    if base is None:
        return None
    base = base.add(offset)
    if base.kind == 'address':
        pointer = binary.pointer(base.value)
        if pointer is None:
            return None
        literal = binary.literal(pointer)
        if literal is not None:
            return Value('string', literal)
        if pointer <= 0xffffffff and pointer & 1 and pointer >> 29 in (1, 2):
            return Value('type', base.value)
        return Value('address', pointer)
    if base.kind == 'type' and base.offset == 0xb8:
        return Value('static', base.value)
    if base.kind in ('argument', 'load') and base.offset == 0xb8:
        return Value('static', base.value)
    if base.kind in ('argument', 'load', 'type'):
        return Value('load', (base.kind, base.value, base.offset))
    return None
