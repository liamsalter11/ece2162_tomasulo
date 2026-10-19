

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

    def load_instructions(self, instructions):
        self.instructions = instructions

    def get_instruction_type(self, instruction):
        integer_instructions = ["add", "addi", "sub"]
        floating_point_add_instructions = ["add.d", "sub.d"]
        floating_point_mul_instructions = ["mul.d"]
        ls_instructions = ["ld", "sd"]
    
        instruction = instruction.lower().split()[0]

        if instruction in floating_point_add_instructions:
            return "floating_point_add"
        elif instruction in floating_point_mul_instructions:
            return "floating_point_mul"
        elif instruction in ls_instructions:
            return "load_store"
        else:
            return "integer"

    def issue(self):
        next_instruction = self.instructions[0] if self.instructions else None
        if not next_instruction:
            return
        instruction_type = self.get_instruction_type(next_instruction)
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
        pass

    def run(self):
        while self.instructions or self.active_instructions:
            self.clock += 1
            self.issue()
            self.execute()
            self.memory_access()
            self.write_back()
            self.commit()


if __name__ == "__main__":
    simulator = tomasula_simulator()
    # Load instructions from a file or define them here
    instructions = []
    with open('ece2162_tomasulo/test_input.s', 'r') as f:
        instructions = [line.strip().lower() for line in f if line.strip()]
    simulator.load_instructions(instructions)
    simulator.run()
