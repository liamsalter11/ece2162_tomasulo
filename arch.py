"""Clocked stages for the Tomasulo architecture under construction."""

from typing import Final

# ISA table order in P1-description.pdf, pages 2-3.
OPCODES: Final[dict[str, int]] = {
    "nop": 0,
    "ld": 1,
    "sd": 2,
    "beq": 3,
    "bne": 4,
    "add": 5,
    "add.d": 6,
    "addi": 7,
    "sub": 8,
    "sub.d": 9,
    "mult.d": 10,
}

OPERAND_TYPES: Final[dict[str, int]] = {"none": 0, "R": 1, "F": 2}

class Arch:
    def __init__(self, inst, mem, reg_r, reg_f, config):
        conf = config["functional_units"]
        units = [conf["integer"], conf["floating_point_add"], conf["floating_point_mul"]]
        rs_sizes = tuple(unit["num_rs"] for unit in units)
        self.inst = inst
        # Add R3, R1, R2 == [5, (1, 3), (1, 1), (1, 2)] 
        self.mem = mem.copy()
        self.reg_r = reg_r.copy()
        self.reg_f = reg_f.copy()
        self.rat_r: list[int] = [-1] * len(self.reg_r)
        self.rat_f: list[int] = [-1] * len(self.reg_f)
        self.pc: int = 0
        self.dyn: list[int] = []
        self.pred: list[int] = []
        self.squashed: list[bool] = []
        self.bht: list[int] = [0] * 8  # Branch history table
        self.btb: list[int] = [0] * 8  # Branch target buffer
        self.mispredict: tuple[int, int] = (-1, -1)

        self.is_inst: int = -1
        self.is_inst_pending: int = -1
        self.is_done: bool = True
        self.is_done_prev: bool = True

        self.ex_inst: list[list[int]] = [[-1] * count for count in rs_sizes]
        self.ex_inst_pending: list[list[int]] = [group.copy() for group in self.ex_inst]
        self.ex_done: list[list[bool]] = [[True] * count for count in rs_sizes]
        self.ex_done_prev: list[list[bool]] = [group.copy() for group in self.ex_done]

        self.tm_cycles: tuple[int, ...] = tuple(unit["ex_cycles"] for unit in units)
        
        #  add.i [0][0:1][ocp, busy, op, [valid,Vj], [valid,Vk], [pos,Qj], [pos,Qk]]
        #  add.d [1][0:2][ocp, busy, op, [valid,Vj], [valid,Vk], [pos,Qj], [pos,Qk]]
        #  mux.i [2][0:1][ocp, busy, op, [valid,Vj], [valid,Vk], [pos,Qj], [pos,Qk]]
        # Qj/Qk: [operand type, ROB index]; [0, 0] means no dependency.
        self.tm_rs: list[list[list[bool|int|list[bool|int|float]]]] = [
            [[False,False,0,[False,0],[False,0],[0,0],[0,0]] for _ in range(rs_sizes[0])],
            [[False,False,0,[False,0],[False,0],[0,0],[0,0]] for _ in range(rs_sizes[1])],
            [[False,False,0,[False,0],[False,0],[0,0],[0,0]] for _ in range(rs_sizes[2])],
        ]
        self.tm_count: list[list[int]] = [[0] * count for count in rs_sizes]
        self.tm_ret: list[list[list[bool|int|float]]] = [
            [[False,0,0] for _ in range(rs_sizes[0])],
            [[False,0,0] for _ in range(rs_sizes[1])],
            [[False,0,0] for _ in range(rs_sizes[2])],
        ]

        self.mem_inst: int = -1
        self.mem_inst_pending: int = -1
        self.mem_rs: tuple[int, int] = (-1, -1)
        self.mem_done:  bool = True
        self.mem_done_prev: bool = True
        self.mem_cycles: int = conf["load_store"]["mem_cycles"]
        self.mem_count: int = 0

        self.wb_inst: int = -1
        self.wb_inst_pending: int = -1
        self.wb_rs: tuple[int, int] = (-1, -1)
        self.wb_value: int | float = 0
        self.wb_done:  bool = True
        self.wb_done_prev: bool = True

        self.rob: list[list[bool | int | float]] = []
        self.rob_head: int = 0

        self.commit_inst: int = -1
        self.commit_inst_pending: int = -1
        self.commit_done:  bool = True
        self.commit_done_prev: bool = True

        self.ldst_isnt: list[int] = [-1] * conf["load_store"]["num_rs"]
        self.ldst_isnt_pending: tuple[int, ...] = tuple(self.ldst_isnt)
        self.ldst_done: list[bool] = [True] * len(self.ldst_isnt)
        self.ldst_done_prev: list[bool] = self.ldst_done.copy()

    def stat_ex(self, inst_num: int) -> tuple[tuple[int, int], bool, tuple[int, int]]:
        available = (-1, -1)
        if inst_num >= 0:
            group = {OPCODES["nop"]: 0, OPCODES["beq"]: 0, OPCODES["bne"]: 0,
                     OPCODES["add"]: 0, OPCODES["add.d"]: 1, OPCODES["addi"]: 0,
                     OPCODES["sub"]: 0, OPCODES["sub.d"]: 1,
                     OPCODES["mult.d"]: 2}.get(self.inst[self.dyn[inst_num]][0], -1)
            if group != -1:
                for slot, instruction in enumerate(self.ex_inst[group]):
                    if (instruction == -1
                        and not self.tm_rs[group][slot][0]
                        and not self.tm_rs[group][slot][1]
                        and not self.tm_ret[group][slot][0]):
                        available = (group, slot)
                        break
        done = [(instruction, group, slot)
                for group, instructions in enumerate(self.ex_inst)
                for slot, instruction in enumerate(instructions)
                if instruction != -1 and self.tm_ret[group][slot][0]]
        if done:
            _, group, slot = min(done)
            return available, True, (group, slot)
        return available, False, (-1, -1)

    def issue(self, edge: bool, inst: int) -> bool:
        """Register an instruction and its current operands in a free RS."""
        if not edge:
            return self.is_done
        if inst == -1:
            return False

        group, slot = self.stat_ex(inst)[0]
        if group == -1:
            return False

        instruction = self.inst[self.dyn[inst]]
        if instruction[0] in (OPCODES["beq"], OPCODES["bne"]):
            sources, dest = instruction[1:3], (OPERAND_TYPES["none"], 0)
        else:
            sources, dest = instruction[2:4], instruction[1]
        self.tm_rs[group][slot] = [True, False, instruction[0],
                                  [False, 0], [False, 0], [0, 0], [0, 0]]
        for i in range(2):
            operand = sources[i]
            value = operand[1]
            tag = -1
            if operand[0] == OPERAND_TYPES["R"]:
                value = self.reg_r[operand[1]]
                tag = self.rat_r[operand[1]]
            if operand[0] == OPERAND_TYPES["F"]:
                value = self.reg_f[operand[1]]
                tag = self.rat_f[operand[1]]
            if tag != -1 and self.rob[tag][0] == False:
                self.tm_rs[group][slot][i + 3] = [False, 0]
                self.tm_rs[group][slot][i + 5] = [operand[0], tag]
            else:
                if tag != -1:
                    value = self.rob[tag][1]
                self.tm_rs[group][slot][i + 3] = [True, value]

        operand = dest
        if operand[0] == OPERAND_TYPES["R"] and operand[1] != 0:
            self.rat_r[operand[1]] = inst
        if operand[0] == OPERAND_TYPES["F"]:
            self.rat_f[operand[1]] = inst
        self.ex_inst[group][slot] = inst
        self.tm_count[group][slot] = 0
        return True

    def execute(self, edge: bool) -> list[list[bool]]:                                                                                                                                                                                 
       self.tomasulo(edge)                                                                                                                                                                                                              
       return [[bool(result[0]) for result in group] for group in self.tm_ret]       

    def tomasulo(self, edge: bool):
        if not edge:
            return 
        
        addi_idx: bool = False
        for i in range(len(self.tm_rs[0])):
            if self.tm_ret[0][i][0] == True:
                # pending. wait for consume result
                continue
            if self.tm_rs[0][i][1] == False:
                if (addi_idx == False and self.tm_rs[0][i][3][0] == True and self.tm_rs[0][i][4][0] == True):
                    # start cal
                    self.tm_rs[0][i][1] = True
                    self.tm_ret[0][i] = [False, 0]
                    self.tm_count[0][i] = 1
                    addi_idx = True
                else:
                    # wait for inst
                    self.tm_count[0][i] = 0
                    self.tm_ret[0][i] = [False, 0]
            else:
                if  self.tm_count[0][i] < self.tm_cycles[0]:
                    # calculating
                    self.tm_count[0][i] += 1
                    self.tm_ret[0][i] = [False, 0]
            if self.tm_count[0][i] >= self.tm_cycles[0]:
                # complete cal
                self.tm_rs[0][i][1] = False
                self.tm_ret[0][i] = [True, self.tm_rs[0][i][3][1] + self.tm_rs[0][i][4][1]] if self.tm_rs[0][i][2] in (OPCODES["add"], OPCODES["addi"]) \
                                        else [True, self.tm_rs[0][i][3][1] - self.tm_rs[0][i][4][1]]
                if self.tm_rs[0][i][2] in (OPCODES["beq"], OPCODES["bne"]):
                    self.resolve_branch(self.ex_inst[0][i], self.tm_ret[0][i][1])
                self.tm_rs[0][i][3:5] = [[False, 0], [False, 0]]


        addd_idx: bool = False
        for i in range(len(self.tm_rs[1])):
            if self.tm_ret[1][i][0] == True:
                # pending. wait for consume result
                continue
            if self.tm_rs[1][i][1] == False:
                if (addd_idx==False and self.tm_rs[1][i][3][0] == True and self.tm_rs[1][i][4][0] == True):
                    # start cal
                    self.tm_rs[1][i][1] = True
                    self.tm_ret[1][i] = [False, 0]
                    self.tm_count[1][i] = 1
                    addd_idx = True
                else:
                    # wait for inst
                    self.tm_count[1][i] = 0
                    self.tm_ret[1][i] = [False, 0]
            else:
                if  self.tm_count[1][i] < self.tm_cycles[1]:
                    # calculating
                    self.tm_count[1][i] += 1
                    self.tm_ret[1][i] = [False, 0]
            if self.tm_count[1][i] >= self.tm_cycles[1]:
                # complete cal
                self.tm_rs[1][i][1] = False
                self.tm_ret[1][i] = [True, self.tm_rs[1][i][3][1] + self.tm_rs[1][i][4][1]] if self.tm_rs[1][i][2] == OPCODES["add.d"] \
                                        else [True, self.tm_rs[1][i][3][1] - self.tm_rs[1][i][4][1]]
                self.tm_rs[1][i][3:5] = [[False, 0], [False, 0]]

        muld_idx:bool = False
        for i in range(len(self.tm_rs[2])):
            if self.tm_ret[2][i][0] == True:
                # pending. wait for consume result
                continue
            if self.tm_rs[2][i][1] == False:
                if (muld_idx==False and self.tm_rs[2][i][3][0] == True and self.tm_rs[2][i][4][0] == True):
                    # start cal
                    self.tm_rs[2][i][1] = True
                    self.tm_ret[2][i] = [False, 0]
                    self.tm_count[2][i] = 1
                    muld_idx = True
                else:
                    # wait for inst
                    self.tm_count[2][i] = 0
                    self.tm_ret[2][i] = [False, 0]
            else:
                if  self.tm_count[2][i] < self.tm_cycles[2]:
                    # calculating
                    self.tm_count[2][i] += 1
                    self.tm_ret[2][i] = [False, 0]
            if self.tm_count[2][i] >= self.tm_cycles[2]:
                # complete cal
                self.tm_rs[2][i][1] = False
                self.tm_ret[2][i] = [True, self.tm_rs[2][i][3][1] * self.tm_rs[2][i][4][1]]
                self.tm_rs[2][i][3:5] = [[False, 0], [False, 0]]

    def resolve_branch(self, tag: int, result: int | float) -> None:
        """Update the predictor with the branch outcome and flag a misprediction."""
        pc = self.dyn[tag]
        instruction = self.inst[pc]
        taken = result == 0 if instruction[0] == OPCODES["beq"] else result != 0
        target = pc + 1 + instruction[3][1]
        actual = target if taken else pc + 1

        idx = pc % 8
        self.bht[idx] = 1 if taken else 0
        self.btb[idx] = target

        if actual != self.pred[tag] and (self.mispredict[0] == -1 or tag < self.mispredict[0]):
            self.mispredict = (tag, actual)

    def finished(self) -> bool:
        """True once every fetched instruction has committed or been squashed."""
        return (self.pc >= len(self.inst) and self.mispredict == (-1, -1)
                and all(self.squashed[self.rob_head:]))

    def free_rs(self, group: int, slot: int) -> None:
        self.tm_rs[group][slot] = [False, False, 0, [False, 0], [False, 0], [0, 0], [0, 0]]
        self.tm_ret[group][slot] = [False, 0, 0]
        self.tm_count[group][slot] = 0
        self.ex_inst[group][slot] = -1

    def recover(self) -> bool:
        """Squash instructions younger than a mispredicted branch and redirect fetch."""
        tag, correct_pc = self.mispredict
        if tag == -1:
            return False

        for t in range(tag + 1, len(self.dyn)):
            self.squashed[t] = True
        for group in range(len(self.ex_inst)):
            for slot in range(len(self.ex_inst[group])):
                if self.ex_inst[group][slot] > tag:
                    self.free_rs(group, slot)
        if self.mem_inst > tag:
            self.free_rs(*self.mem_rs)
            self.mem_inst = -1
            self.mem_rs = (-1, -1)
            self.mem_count = 0
        if self.wb_inst > tag:
            self.free_rs(*self.wb_rs)
            self.wb_inst = -1
            self.wb_rs = (-1, -1)
        self.is_inst = -1

        self.rat_r = [-1] * len(self.reg_r)
        self.rat_f = [-1] * len(self.reg_f)
        for t in range(self.rob_head, tag + 1):
            instruction = self.inst[self.dyn[t]]
            if self.squashed[t] or instruction[0] in (OPCODES["beq"], OPCODES["bne"]):
                continue
            operand = instruction[1]
            if operand[0] == OPERAND_TYPES["R"] and operand[1] != 0:
                self.rat_r[operand[1]] = t
            if operand[0] == OPERAND_TYPES["F"]:
                self.rat_f[operand[1]] = t

        self.pc = correct_pc
        self.mispredict = (-1, -1)
        return True

    def memory_access(self, edge: bool, inst: int) -> bool:
        """Time LD/SD memory access; other operations pass through in one cycle."""
        if not edge:
            return self.mem_done
        if inst == -1:
            self.mem_count = 0
            return False
        cycles = self.mem_cycles if self.inst[self.dyn[inst]][0] in (OPCODES["ld"], OPCODES["sd"]) else 1
        if self.mem_count < cycles:
            self.mem_count += 1
        return self.mem_count >= cycles

    def write_back(self, edge: bool, inst: int) -> bool:
        """Receive the selected result once and hold its value for COMMIT."""
        if not edge:
            return self.wb_done
        if inst == -1:
            return False
        if self.wb_done == True:
            return True

        group, slot = self.wb_rs
        if group == -1:
            return False
        if self.tm_ret[group][slot][0] == False:
            return False

        self.wb_value = self.tm_ret[group][slot][1]
        self.rob[inst] = [True, self.wb_value]
        self.tm_ret[group][slot][0] = False
        return True

    def commit(self, edge: bool, inst: int) -> bool:
        """Commit the ready ROB head selected by module."""
        if not edge:
            return self.commit_done
        if inst != -1:
            instruction = self.inst[self.dyn[inst]]
            operand = (OPERAND_TYPES["none"], 0) if instruction[0] in (OPCODES["beq"], OPCODES["bne"]) else instruction[1]
            if operand[0] == OPERAND_TYPES["R"] and operand[1] != 0:
                self.reg_r[operand[1]] = self.rob[inst][1]
                if self.rat_r[operand[1]] == inst:
                    self.rat_r[operand[1]] = -1
            if operand[0] == OPERAND_TYPES["F"]:
                self.reg_f[operand[1]] = self.rob[inst][1]
                if self.rat_f[operand[1]] == inst:
                    self.rat_f[operand[1]] = -1
            self.rob_head += 1
        return inst != -1

    def module(self, rising_edge):
        if rising_edge == True:
            recovering = self.recover()
            _, ex_done, ex_done_id = self.stat_ex(self.is_inst)
            if self.wb_done_prev == True and self.wb_rs != (-1, -1):
                for group in range(len(self.tm_rs)):
                    for slot in range(len(self.tm_rs[group])):
                        for i in range(2):
                            if self.tm_rs[group][slot][i + 5] in ([OPERAND_TYPES["R"], self.wb_inst], [OPERAND_TYPES["F"], self.wb_inst]):
                                self.tm_rs[group][slot][i + 3] = [True, self.wb_value]
                                self.tm_rs[group][slot][i + 5] = [0, 0]
                group, slot = self.wb_rs
                self.tm_rs[group][slot][0] = False
                self.wb_rs = (-1, -1)
                self.wb_inst = -1
            self.commit_inst = -1
            while self.rob_head < len(self.rob) and self.squashed[self.rob_head]:
                self.rob_head += 1
            if self.rob_head < len(self.rob) and self.rob[self.rob_head][0] == True:
                self.commit_inst = self.rob_head
                self.commit_done_prev=False
            if(self.mem_done_prev==True and self.wb_inst==-1):
                self.wb_inst = self.mem_inst
                self.wb_rs = self.mem_rs
                self.mem_inst = -1
                self.mem_rs = (-1, -1)
                self.wb_done=False
                self.wb_done_prev=False
            if(ex_done==True and self.mem_inst==-1):
                group, slot = ex_done_id
                self.mem_inst = self.ex_inst[group][slot]
                self.mem_rs = ex_done_id
                self.ex_inst[group][slot] = -1
                self.mem_done_prev=False
                self.mem_count = 0
            if self.is_done_prev == True:
                self.is_inst = -1
            if self.is_inst == -1 and self.pc < len(self.inst) and not recovering:
                self.is_inst = len(self.dyn)
                self.dyn.append(self.pc)
                self.squashed.append(False)
                self.rob.append([False, 0])
                next_pc = self.pc + 1

                # Check for branch instruction
                if self.inst[self.pc][0] in (OPCODES["beq"], OPCODES["bne"]):
                    idx = self.pc % 8
                    if self.bht[idx] == 1:
                        next_pc = self.btb[idx]
                self.pred.append(next_pc)
                self.pc = next_pc
                self.is_done_prev=False

        self.commit_done = self.commit(edge=rising_edge, inst=self.commit_inst)
        self.wb_done = self.write_back(edge=rising_edge, inst=self.wb_inst)
        self.mem_done = self.memory_access(edge=rising_edge, inst=self.mem_inst)
        self.ex_done = self.execute(edge=rising_edge)

        ex_ret = [[-1] * len(group) for group in self.ex_inst]
        for i in range(len(self.ex_inst)):
            for j in range(len(self.ex_inst[i])):
                ex_ret[i][j] = self.ex_inst[i][j] if self.ex_done_prev[i][j] == False and self.tm_count[i][j] > 0 else -1

        self.is_done = self.issue(edge=rising_edge, inst=self.is_inst)
        ret = [True, self.is_inst if self.is_done == True else -1,\
                ex_ret, self.mem_inst if self.mem_done_prev == False else -1,\
                self.wb_inst if self.wb_done_prev == False else -1,\
                self.commit_inst if self.commit_done_prev == False else -1]
        
        self.is_done_prev = self.is_done 
        self.ex_done_prev = [group.copy() for group in self.ex_done]
        self.mem_done_prev = self.mem_done
        self.wb_done_prev = self.wb_done
        self.commit_done_prev = self.commit_done

        return ret
        
        

