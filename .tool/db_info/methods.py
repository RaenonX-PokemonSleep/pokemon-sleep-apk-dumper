"""Use Cpp2IL for method locations; decode bytes through ELF virtual addresses."""
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Method:
    signature: str
    address: int
    size: int
    calls: tuple[str, ...]


class Methods:
    def __init__(self, root: Path):
        self.root = root
        self.cache = {}

    def get(self, relative):
        if relative not in self.cache:
            path = self.root / (relative + '.txt')
            methods = []
            if path.exists():
                for block in path.read_text(encoding='utf-8-sig').split('Method: ')[1:]:
                    signature, body = block.split('\n', 1)
                    raw = body.split('ISIL:', 1)[0]
                    addresses = re.findall(r'^\s*0x([0-9A-Fa-f]+) ', raw, re.M)
                    if addresses:
                        start, end = int(addresses[0], 16), int(addresses[-1], 16) + 4
                        calls = tuple(re.findall(r'\bCall ([^,\r\n]+)', body.split('ISIL:', 1)[-1]))
                        methods.append(Method(signature.strip(), start, end - start, calls))
            self.cache[relative] = methods
        return self.cache[relative]

    def find(self, relative, name):
        matches = [m for m in self.get(relative) if f' {name}(' in m.signature]
        return matches[0] if len(matches) == 1 else None
