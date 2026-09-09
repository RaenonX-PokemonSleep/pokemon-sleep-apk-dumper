"""Discover Cpp2IL classes and retain offsets before the C# cleanup step."""
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Class:
    relative: str
    name: str
    text: str

    def constant(self, field):
        match = re.search(rf'\bconst string {re.escape(field)} = "(.*)";', self.text)
        return match[1] if match else None

    def fields(self):
        return {name: int(offset, 16) for name, offset in re.findall(
            r'\bstatic readonly string (\w+); //Field offset: 0x([0-9A-Fa-f]+)', self.text)}


def classes(root):
    for path in sorted(root.rglob('*.cs')):
        text = path.read_text(encoding='utf-8-sig')
        if 'MasterDataManagerBase' in text or 'SyncDatabase<' in text or 'PS.Migration.' in text:
            yield Class(path.relative_to(root).with_suffix('').as_posix(), path.stem, text)
