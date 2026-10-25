import json


class Input:
    def __init__(self, num_rs, ex_cycles, mem_cycles, num_fus):
        self.num_rs = num_rs
        self.ex_cycles = ex_cycles
        self.mem_cycles = mem_cycles
        self.num_fus = num_fus


class IntegerInput(Input):
    def __init__(self, num_rs, ex_cycles, mem_cycles, num_fus):
        super().__init__(num_rs, ex_cycles, mem_cycles, num_fus)


class FloatingPointAddInput(Input):
    def __init__(self, num_rs, ex_cycles, mem_cycles, num_fus):
        super().__init__(num_rs, ex_cycles, mem_cycles, num_fus)


class FloatingPointMulInput(Input):
    def __init__(self, num_rs, ex_cycles, mem_cycles, num_fus):
        super().__init__(num_rs, ex_cycles, mem_cycles, num_fus)


class LSInput(Input):
    def __init__(self, num_rs, ex_cycles, mem_cycles, num_fus):
        super().__init__(num_rs, ex_cycles, mem_cycles, num_fus)


class Instruction:
    def __init__(self, instruction_str, issue_cycle):
        self.instruction_str = str(instruction_str)
        self.issue_cycle = issue_cycle

        self.execution_start_cycle = None
        self.execution_end_cycle = None
        self.memory_access_start_cycle = None
        self.memory_access_end_cycle = None
        self.write_back_cycle = None
        self.commit_cycle = None

        self.opcode = None
        self.operands = []
        self.parse_instruction()
        self.pc = issue_cycle * 4
        self.fu_type = self.get_fu_type()
        self.target_register = self.get_target_register()
        self.source_registers = self.get_source_registers()
        self.immediate_value = self.get_immediate_value()
        self.rob_entry = None
        self.rs_entry = None

    def get_immediate_value(self):
        if self.opcode in ["addi", "beq", "bne"]:
            return int(self.operands[2])
        elif self.opcode in ["ld", "sd"]:
            return int(self.operands[1].split('(')[0])
        else:
            return None

    def get_source_registers(self):
        if self.opcode in ["add", "add.d", "sub", "sub.d", "mult.d"]:
            return [self.operands[1], self.operands[2]]
        elif self.opcode in ["addi", "beq", "bne"]:
            return [self.operands[1]]  # Immediate value is not a register
        elif self.opcode in ["ld"]:
            return [self.operands[1].split('(')[1].rstrip(')')]  # Base register from offset(base)
        elif self.opcode in ["sd"]:
            return [self.operands[0], self.operands[1].lstrip('(').rstrip(')')]  # Source register and base register
        else:
            return []

    def get_target_register(self):
        if self.opcode not in ["sd", "nop", "beq", "bne"]:
            return self.operands[0]
        return None

    def get_fu_type(self):
        integer_instructions = ["add", "addi", "sub"]
        floating_point_add_instructions = ["add.d", "sub.d"]
        floating_point_mul_instructions = ["mult.d"]
        ls_instructions = ["ld", "sd"]
        nop = ["nop"]
        branch_instructions = ["beq", "bne"]
        instruction = self.opcode

        if instruction in floating_point_add_instructions:
            return "floating_point_add"
        elif instruction in floating_point_mul_instructions:
            return "floating_point_mul"
        elif instruction in ls_instructions:
            return "load_store"
        elif instruction in nop:
            return "nop"
        else: # int and branch instructions
            return "integer"

    def parse_instruction(self):
        parts = self.instruction_str.lower().split()
        if len(parts) > 0:
            self.opcode = parts[0]
            self.operands = [operand.strip(',') for operand in parts[1:]]

    def print_debug(self):
        print(f"Instruction: {self.instruction_str}")
        print(f"  Issue Cycle: {self.issue_cycle}")
        print(f"  Execution Start Cycle: {self.execution_start_cycle}")
        print(f"  Execution End Cycle: {self.execution_end_cycle}")
        print(f"  Memory Access Start Cycle: {self.memory_access_start_cycle}")
        print(f"  Memory Access End Cycle: {self.memory_access_end_cycle}")
        print(f"  Write Back Cycle: {self.write_back_cycle}")
        print(f"  Commit Cycle: {self.commit_cycle}")
        print(f"  Opcode: {self.opcode}")
        print(f"  Operands: {self.operands}")
        print(f"  PC: {self.pc}")
        print(f"  FU Type: {self.fu_type}")
        print(f"  Target Register: {self.target_register}")
        print(f"  Source Registers: {self.source_registers}")
        print(f"  Immediate Value: {self.immediate_value}")


class ReservationStation:
    def __init__(self, name):
        self.name = name
        self.busy = False
        self.op = None
        self.vj = None
        self.vk = None
        self.qj = None
        self.qk = None
        self.a = None
        self.instruction = None


class tomasula_simulator:
    def __init__(self):
        self.clock = 0
        self.instructions = []
        self.active_instructions = []
        self.completed_instructions = []
        self.input_cfg = {
            "integer": IntegerInput(2, 1, 0, 1),
            "floating_point_add": FloatingPointAddInput(3, 3, 0, 1),
            "floating_point_mul": FloatingPointMulInput(2, 20, 0, 1),
            "load_store": LSInput(3, 1, 4, 1)
        }
        self.rat_int = [None] * 32  # Register Alias Table for integer registers
        self.rat_fp = [None] * 32   # Register Alias Table for floating
        self.registers_int = [0] * 32  # Integer registers
        self.registers_fp = [0.0] * 32  # Floating-point registers
        self.memory = []
        self.rob_entries = 0
        self.cdb_buffer_entries = 0

    def load_instructions(self, instructions):
        self.instructions = [Instruction(instr, issue_cycle=i) for i, instr in enumerate(instructions)]

    def load_memory(self, mem_contents):
        self.memory = mem_contents

    def load_config(self, config):
        self.rob_entries = config["rob_entries"]
        self.cdb_buffer_entries = config["cdb_buffer_entries"]
        for fu_type, cfg in config["functional_units"].items():
            if fu_type in self.input_cfg:
                self.input_cfg[fu_type].num_rs = cfg.get("num_rs", self.input_cfg[fu_type].num_rs)
                self.input_cfg[fu_type].ex_cycles = cfg.get("ex_cycles", self.input_cfg[fu_type].ex_cycles)
                self.input_cfg[fu_type].mem_cycles = cfg.get("mem_cycles", self.input_cfg[fu_type].mem_cycles)
                self.input_cfg[fu_type].num_fus = cfg.get("num_fus", self.input_cfg[fu_type].num_fus)
    
    def issue(self):
        next_instruction = self.instructions[0] if self.instructions else None
        if not next_instruction:
            return
        instruction_type = next_instruction.fu_type
        if self.input_cfg[instruction_type].num_rs > 0:
            self.active_instructions.append(self.instructions.pop(0))
            self.input_cfg[instruction_type].num_rs -= 1

    def execute(self):
        # Implement the execute logic here
        pass

    def memory_access(self):
        # Implement the memory access logic here
        pass

    def write_back(self):
        # Implement the write back logic here
        pass

    def commit(self):
        # Implement the commit logic here

        # TODO: Remove this later
        if self.instructions:
            self.instructions[0].print_debug()
            self.instructions.pop(0)
        if self.active_instructions:
            self.active_instructions[0].print_debug()
            self.active_instructions.pop(0)

    def run(self):
        while self.instructions or self.active_instructions:
            self.clock += 1
            self.commit()
            self.write_back()
            self.memory_access()
            self.execute()
            self.issue()

    def print_debug(self):
        print(f"Clock Cycle: {self.clock}")
        print("Active Instructions:")
        for instr in self.active_instructions:
            instr.print_debug()
        print("Completed Instructions:")
        for instr in self.completed_instructions:
            instr.print_debug()
        print("Register Alias Table (Integer):", self.rat_int)
        print("Register Alias Table (Floating Point):", self.rat_fp)
        print("Integer Registers:", self.registers_int)
        print("Floating Point Registers:", self.registers_fp)
        print("Memory Contents:", self.memory)
        print("ROB Entries:", self.rob_entries)
        print("CDB Buffer Entries:", self.cdb_buffer_entries)


if __name__ == "__main__":
    simulator = tomasula_simulator()
    # Load instructions from a file or define them here
    instructions = []
    mem_contents = []
    config = {}
    with open('test_input.s', 'r') as f:
        instructions = [line.strip().lower() for line in f if line.strip()]
    with open('default_mem.mem', 'r') as f:
        mem_contents = []
        for line in f:
            if not line.strip() or line.startswith('#'):
                continue
            split_line = line.strip().split()
            for entry in split_line:
                mem_contents.append(float(entry) if '.' in entry else int(entry))
    with open('default_config.json', 'r') as f:
        config = json.load(f)

    print("Instructions:", instructions)
    print("Memory Contents:", mem_contents)
    print("Configuration:", config)
    
    simulator.load_instructions(instructions)
    simulator.load_memory(mem_contents)
    simulator.load_config(config)
    simulator.run()
    simulator.print_debug()
