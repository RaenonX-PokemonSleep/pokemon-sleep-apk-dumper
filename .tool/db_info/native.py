"""Conservative ARM64 data flow for literal returns and static string assignments."""
from collections import defaultdict, deque
from dataclasses import dataclass, field

from capstone.arm64 import ARM64_OP_IMM, ARM64_OP_MEM, ARM64_OP_REG

from values import Value, load


def reg(instruction, operand):
    name = instruction.reg_name(operand.reg)
    return 'x' + name[1:] if name.startswith('w') else name


@dataclass
class Result:
    stores: dict = field(default_factory=lambda: defaultdict(set))
    returns: set = field(default_factory=set)
    literals: set = field(default_factory=set)
    written_strings: set = field(default_factory=set)
    issues: set = field(default_factory=set)
    exits: list = field(default_factory=list)


def merge(left, right):
    return {key: value for key, value in left.items() if right.get(key) == value}


def analyze(binary, method):
    result = Result()
    instructions = {i.address: i for i in binary.instructions(method)}
    initial = {'x0': Value('argument', 0), 'sp': Value('stack', 0)}
    states = {method.address: initial}
    queue = deque([method.address])
    visits = 0
    while queue:
        address = queue.popleft()
        instruction = instructions.get(address)
        if instruction is None:
            result.issues.add('Incomplete method instruction range')
            continue
        registers = states[address].copy()
        successors = execute(binary, instruction, registers, result, instructions)
        for target in successors:
            if target not in states:
                states[target] = registers.copy()
                queue.append(target)
            else:
                joined = merge(states[target], registers)
                if joined != states[target]:
                    states[target] = joined
                    queue.append(target)
        visits += 1
        if visits > max(len(instructions) * 32, 1000):
            result.issues.add('Native analysis did not converge')
            break
    for (root, offset), values in result.stores.items():
        location = Value('static', root, offset)
        if not result.exits or any(location not in state for state in result.exits):
            values.add(None)
    return result


def execute(binary, ins, registers, result, instructions):
    operands, mnemonic = ins.operands, ins.mnemonic

    def value(operand):
        if operand.type == ARM64_OP_IMM:
            return Value('address', operand.imm)
        if operand.type == ARM64_OP_REG:
            return registers.get(reg(ins, operand))
        return None

    def put(operand, data):
        key = reg(ins, operand)
        if data is None:
            registers.pop(key, None)
        else:
            registers[key] = data

    def memory(operand):
        base = registers.get(ins.reg_name(operand.mem.base))
        if base is not None and not operand.mem.index:
            return base.add(operand.mem.disp)
        return None

    next_addresses = [ins.address + 4]
    if mnemonic in ('adrp', 'adr', 'mov', 'movz') and len(operands) == 2:
        put(operands[0], value(operands[1]))
    elif mnemonic in ('add', 'sub') and len(operands) == 3 and operands[2].type == ARM64_OP_IMM:
        base = value(operands[1])
        delta = operands[2].imm * (1 if mnemonic == 'add' else -1)
        put(operands[0], base.add(delta) if base else None)
    elif mnemonic in ('ldr', 'ldur', 'ldp', 'str', 'stur', 'stp'):
        memory_index = 2 if mnemonic in ('ldp', 'stp') else 1
        operand = operands[memory_index]
        location = memory(operand)
        for index in range(memory_index):
            current = location.add(index * 8) if location else None
            if mnemonic in ('ldr', 'ldur', 'ldp'):
                data = registers.get(current) if current and current.kind == 'stack' else load(binary, current, 0)
                put(operands[index], data)
                if data and data.kind == 'string':
                    result.literals.add(data.value)
            else:
                data = value(operands[index])
                if data and data.kind == 'string' and (current is None or current.kind != 'stack'):
                    result.written_strings.add(data.value)
                if current and current.kind == 'stack':
                    if data is None:
                        registers.pop(current, None)
                    else:
                        registers[current] = data
                elif current and current.kind == 'static':
                    if data is None:
                        registers.pop(current, None)
                    else:
                        registers[current] = data
                    result.stores[(current.value, current.offset)].add(
                        data.value if data and data.kind == 'string' else None)
        if ins.writeback:
            base_name = ins.reg_name(operand.mem.base)
            original = registers.get(base_name)
            delta = operands[-1].imm if operands[-1].type == ARM64_OP_IMM else operand.mem.disp
            if original:
                registers[base_name] = original.add(delta)
    elif mnemonic in ('bl', 'blr'):
        for index in range(19):
            registers.pop(f'x{index}', None)
    elif mnemonic == 'ret':
        result.exits.append(registers.copy())
        data = registers.get('x0')
        result.returns.add(data.value if data and data.kind == 'string' else None)
        return []
    elif mnemonic == 'b':
        target = operands[0].imm
        if target not in instructions:
            result.exits.append(registers.copy())
            return []  # Tail call; no assumptions about its result.
        return [target]
    elif mnemonic.startswith('b.') or mnemonic in ('cbz', 'cbnz', 'tbz', 'tbnz'):
        next_addresses.append(operands[-1].imm)
    else:
        # Unsupported writes must invalidate tracked values rather than reuse stale registers.
        for register_id in ins.regs_access()[1]:
            name = ins.reg_name(register_id)
            registers.pop('x' + name[1:] if name.startswith('w') else name, None)
    return next_addresses
