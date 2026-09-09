"""Read ARM64 ELF pointers and IL2CPP v31 literal references without loading code."""
import io
import struct
from pathlib import Path

from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM
from elftools.elf.elffile import ELFFile
from elftools.elf.relocation import RelocationSection


class Binary:
    def __init__(self, binary: Path, metadata: Path):
        self.data = binary.read_bytes()
        self.metadata = metadata.read_bytes()
        elf = ELFFile(io.BytesIO(self.data))
        if elf['e_machine'] != 'EM_AARCH64' or not elf.little_endian:
            raise ValueError('Only little-endian ARM64 ELF binaries are supported')
        magic, version = struct.unpack_from('<II', self.metadata)
        if magic != 0xFAB11BAF or version != 31:
            raise ValueError(f'Unsupported IL2CPP metadata header: {magic:x}, v{version}')
        self.segments = [s.header for s in elf.iter_segments() if s['p_type'] == 'PT_LOAD']
        self.relocations = {}
        for section in elf.iter_sections():
            if isinstance(section, RelocationSection):
                for relocation in section.iter_relocations():
                    if relocation['r_info_type'] == 1027:  # R_AARCH64_RELATIVE
                        self.relocations[relocation['r_offset']] = relocation['r_addend']
        self.literal_offset, self.literal_size, self.string_offset, string_size = (
            struct.unpack_from('<IIII', self.metadata, 8))
        if self.string_offset + string_size > len(self.metadata):
            raise ValueError('Metadata literal pool extends beyond the input file')
        self.decoder = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
        self.decoder.detail = True

    def offset(self, address, size=8):
        for segment in self.segments:
            delta = address - segment['p_vaddr']
            if 0 <= delta and delta + size <= segment['p_filesz']:
                return segment['p_offset'] + delta
        return None

    def pointer(self, address):
        if address in self.relocations:
            return self.relocations[address]
        offset = self.offset(address)
        return struct.unpack_from('<Q', self.data, offset)[0] if offset is not None else None

    def literal(self, encoded):
        if encoded is None or encoded > 0xffffffff or encoded >> 29 != 5:
            return None
        index = (encoded & 0x1fffffff) >> 1
        if index * 8 >= self.literal_size:
            return None
        size, start = struct.unpack_from('<II', self.metadata, self.literal_offset + index * 8)
        return self.metadata[self.string_offset + start:self.string_offset + start + size].decode('utf-8')

    def literals(self):
        for index in range(self.literal_size // 8):
            yield self.literal((5 << 29) | (index << 1) | 1)

    def instructions(self, method):
        offset = self.offset(method.address, method.size)
        if offset is None:
            raise ValueError(f'Method outside ELF load segments: {method.signature}')
        return list(self.decoder.disasm(self.data[offset:offset + method.size], method.address))
