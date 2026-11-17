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
    def __init__(self, inst, mem, arf_r, arf_f, config):
        conf = config["functional_units"]
        units = [conf["integer"], conf["floating_point_add"], conf["floating_point_mul"]]
        rs_sizes = tuple(unit["num_rs"] for unit in units)
        self.inst = inst
        # Add R3, R1, R2 == [5, (1, 3), (1, 1), (1, 2)] 
        self.mem = mem.copy()
        self.arf_r = arf_r.copy()
        self.arf_f = arf_f.copy()
        self.rat_r: list[int] = [-1] * len(self.arf_r)
        self.rat_f: list[int] = [-1] * len(self.arf_f)
        self.prf_r: list[int | float] = [0] * 256
        self.prf_f: list[int | float] = [0] * 256
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
        
        #  add.i [0][0:1][ocp, age, busy, op, [valid,Vj], [valid,Vk], [pos,Qj], [pos,Qk]]
        #  add.d [1][0:2][ocp, age, busy, op, [valid,Vj], [valid,Vk], [pos,Qj], [pos,Qk]]
        #  mux.i [2][0:1][ocp, age, busy, op, [valid,Vj], [valid,Vk], [pos,Qj], [pos,Qk]]
        # pos: ARF=0, PRF=1
        self.tm_rs: list[list[list[bool|int|list[bool|int|float]]]] = [
            [[False,0,False,0,[False,0],[False,0],[0,0],[0,0]] for _ in range(rs_sizes[0])],
            [[False,0,False,0,[False,0],[False,0],[0,0],[0,0]] for _ in range(rs_sizes[1])],
            [[False,0,False,0,[False,0],[False,0],[0,0],[0,0]] for _ in range(rs_sizes[2])],
        ]
        self.tm_count: list[list[int]] = [[0] * count for count in rs_sizes]
        self.tm_ret: list[list[list[bool|int|float]]] = [
            [[False,0,0] for _ in range(rs_sizes[0])],
            [[False,0,0] for _ in range(rs_sizes[1])],
            [[False,0,0] for _ in range(rs_sizes[2])],
        ]

        self.mem_inst: int = -1
        self.mem_inst_pending: int = -1
        self.mem_stage_rs: tuple[int, int] = (-1, -1)
        self.mem_done: bool = True
        self.mem_done_prev: bool = True
        self.mem_ctrl_inst: list[list[int]] = [[-1] * conf["load_store"]["num_rs"]]
        # [ocp, age, strt, done, op, [valid,addr], [valid,Vj], [valid,Vk], [pos,Qj], [pos,Qk], offset]
        self.mem_rs: list[list[bool|int|list[bool|int|float]]] = \
            [[False,False,False,False,-1,[False,0],[False,0],[False,0],[0,0],[0,0], 0] for _ in range(conf["load_store"]["num_rs"])]
        self.mem_cycles: int = conf["load_store"]["mem_cycles"]
        self.mem_idx: int = -1
        self.mem_count: int = 0
        self.mem_ex_idx: int = -1
        self.mem_ex_count: int = 0
        self.mem_ex_cycles: int = conf["load_store"]["ex_cycles"]


        self.wb_inst: int = -1
        self.wb_inst_pending: int = -1
        self.wb_rs: tuple[int, int] = (-1, -1)
        self.wb_value: int | float = 0
        self.wb_done:  bool = True
        self.wb_done_prev: bool = True

        # [valid, prf_idx/lsq_idx, inst]
        self.rob: list[list[bool | int]] = [[False,-1,-1] for _ in range(config["rob_entries"])]
        self.rob_head: int = 0
        self.rob_tail: int = 0

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
                for slot in range(len(self.ex_inst[group])):
                    if (self.ex_inst[group][slot] == -1
                        and not self.tm_rs[group][slot][0]
                        and not self.tm_rs[group][slot][2]
                        and not self.tm_ret[group][slot][0]):
                        available = (group, slot)
                        break
        done = (-1, -1)
        for group in range(len(self.ex_inst)):
            for slot in range(len(self.ex_inst[group])):
                if self.ex_inst[group][slot] != -1 and self.tm_ret[group][slot][0]:
                    if done==(-1,-1) or self.tm_rs[group][slot][1]>self.tm_rs[done[0]][done[1]][1]:
                        done = (group, slot)
        if done != (-1, -1):
            return available, True, done
        return available, False, (-1, -1)

    def issue(self, edge: bool, inst: int) -> bool:
        """Register an instruction and its current operands in a free RS."""
        if not edge:
            return self.is_done
        if inst == -1:
            return False

        if self.inst[self.dyn[inst]][0] in (OPCODES["ld"], OPCODES["sd"]):
            group, slot = -1, self.avail_mem_rs()
            if slot == -1:
                return False
            sources = ((OPERAND_TYPES["none"], 0), self.inst[self.dyn[inst]][3]) if self.inst[self.dyn[inst]][0] == OPCODES["ld"] else (self.inst[self.dyn[inst]][1], self.inst[self.dyn[inst]][3])
            dest = self.inst[self.dyn[inst]][1] if self.inst[self.dyn[inst]][0] == OPCODES["ld"] else (OPERAND_TYPES["none"], 0)
        else:
            group, slot = self.stat_ex(inst)[0]
            if group == -1:
                return False
            if self.inst[self.dyn[inst]][0] in (OPCODES["beq"], OPCODES["bne"]):
                sources, dest = self.inst[self.dyn[inst]][1:3], (OPERAND_TYPES["none"], 0)
            else:
                sources, dest = self.inst[self.dyn[inst]][2:4], self.inst[self.dyn[inst]][1]

        rob_idx = (self.rob_tail - 1) % len(self.rob)

        # check avail prf
        if (dest[0] == OPERAND_TYPES["R"] and dest[1] != 0) or dest[0] == OPERAND_TYPES["F"]:
            for i in range(len(self.prf_r) if dest[0] == OPERAND_TYPES["R"] else len(self.prf_f)):
                ocp = False
                for t in range(len(self.rob)):
                    if self.rob[t][2]!=-1 and self.rob[t][1] == i and self.inst[self.dyn[self.rob[t][2]]][0] != OPCODES["sd"] and self.inst[self.dyn[self.rob[t][2]]][1][0] == dest[0]:
                        ocp = True
                        break
                if ocp == False:
                    self.rob[rob_idx][1] = i
                    break
            if self.rob[rob_idx][1] == -1:
                return False

        # get source val
        if group == -1:
            self.mem_rs[slot] = [True, 0, False, False, self.inst[self.dyn[inst]][0],
                                 [False, 0], [False, 0], [False, 0], [0, 0], [0, 0], self.inst[self.dyn[inst]][2][1]]
        else:
            self.tm_rs[group][slot] = [True, 0, False, self.inst[self.dyn[inst]][0],
                                      [False, 0], [False, 0], [0, 0], [0, 0]]
        rs = self.mem_rs[slot] if group == -1 else self.tm_rs[group][slot]
        source_idx = 6 if group == -1 else 4
        for i in range(2):
            operand = sources[i]
            value = operand[1]
            tag = -1
            valid = True
            rs[i + source_idx + 2] = [0, operand[1]]
            if operand[0] == OPERAND_TYPES["R"]:
                value = self.arf_r[operand[1]]
                tag = self.rat_r[operand[1]]
                if tag != -1:
                    valid = self.rob[tag][0] == True
                    value = self.prf_r[self.rob[tag][1]] if valid == True else 0
            if operand[0] == OPERAND_TYPES["F"]:
                value = self.arf_f[operand[1]]
                tag = self.rat_f[operand[1]]
                if tag != -1:
                    valid = self.rob[tag][0] == True
                    value = self.prf_f[self.rob[tag][1]] if valid == True else 0
            if tag != -1:
                rs[i + source_idx + 2] = [1, self.rob[tag][1]]
            rs[i + source_idx] = [valid, value]

        # update dest prf & rat
        operand = dest
        if operand[0] == OPERAND_TYPES["R"] and operand[1] != 0:
            self.rat_r[operand[1]] = rob_idx
        if operand[0] == OPERAND_TYPES["F"]:
            self.rat_f[operand[1]] = rob_idx
        if self.inst[self.dyn[inst]][0] == OPCODES["sd"]:
            self.rob[rob_idx][1] = slot
        if group == -1:
            self.ldst_isnt[slot] = inst
        else:
            self.ex_inst[group][slot] = inst
            self.tm_count[group][slot] = 0
        return True

    def execute(self, edge: bool) -> list[list[bool]]:
        self.tomasulo(edge)
        return [[bool(result[0]) for result in group] for group in self.tm_ret]       

    def tomasulo(self, edge: bool):
        if not edge:
            return 
        
        # inc rs age
        for i in range(len(self.tm_rs)):
            for j in range(len(self.tm_rs[i])):
                self.tm_rs[i][j][1] = self.tm_rs[i][j][1] + 1 if self.tm_rs[i][j][0]==True else 0

        # sel addi idx
        addi_idx: int = -1
        if any(self.tm_rs[0][i][2] for i in range(len(self.tm_rs[0]))) == False:
            for i in range(len(self.tm_rs[0])):
                if self.tm_rs[0][i][0]==True and self.tm_rs[0][i][2]==False and self.tm_ret[0][i][0]==False and self.tm_rs[0][i][4][0]==True and self.tm_rs[0][i][5][0]==True:
                    if addi_idx==-1 or self.tm_rs[0][i][1]>self.tm_rs[0][addi_idx][1]:
                        addi_idx = i
        for i in range(len(self.tm_rs[0])):
            if self.tm_ret[0][i][0] == True:
                # pending. wait for consume result
                continue
            if self.tm_rs[0][i][2] == False:
                if i == addi_idx:
                    # start cal
                    self.tm_rs[0][i][2] = True
                    self.tm_ret[0][i] = [False, 0]
                    self.tm_count[0][i] = 1
                else:
                    # wait for inst
                    self.tm_count[0][i] = 0
                    self.tm_ret[0][i] = [False, 0]
            else:
                if  self.tm_count[0][i] < self.tm_cycles[0]:
                    # cal
                    self.tm_count[0][i] += 1
                    self.tm_ret[0][i] = [False, 0]
            if self.tm_count[0][i] >= self.tm_cycles[0]:
                # complete cal
                self.tm_rs[0][i][2] = False
                self.tm_ret[0][i] = [True, self.tm_rs[0][i][4][1] + self.tm_rs[0][i][5][1]] if self.tm_rs[0][i][3] in (OPCODES["add"], OPCODES["addi"]) else [True, self.tm_rs[0][i][4][1] - self.tm_rs[0][i][5][1]]
                if self.tm_rs[0][i][3] in (OPCODES["beq"], OPCODES["bne"]):
                    self.resolve_branch(self.ex_inst[0][i], self.tm_ret[0][i][1])
                self.tm_rs[0][i][4:6] = [[False, 0], [False, 0]]


        # sel addd idx
        addd_idx: int = -1
        for i in range(len(self.tm_rs[1])):
            if self.tm_rs[1][i][0]==True and self.tm_rs[1][i][2]==False and self.tm_ret[1][i][0]==False and self.tm_rs[1][i][4][0]==True and self.tm_rs[1][i][5][0]==True:
                if addd_idx==-1 or self.tm_rs[1][i][1]>self.tm_rs[1][addd_idx][1]:
                    addd_idx = i
        for i in range(len(self.tm_rs[1])):
            if self.tm_ret[1][i][0] == True:
                # pending. wait for consume result
                continue
            if self.tm_rs[1][i][2] == False:
                if i == addd_idx:
                    # start cal
                    self.tm_rs[1][i][2] = True
                    self.tm_ret[1][i] = [False, 0]
                    self.tm_count[1][i] = 1
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
                self.tm_rs[1][i][2] = False
                self.tm_ret[1][i] = [True, self.tm_rs[1][i][4][1] + self.tm_rs[1][i][5][1]] if self.tm_rs[1][i][3] == OPCODES["add.d"] \
                                        else [True, self.tm_rs[1][i][4][1] - self.tm_rs[1][i][5][1]]
                self.tm_rs[1][i][4:6] = [[False, 0], [False, 0]]

        # sel muld idx
        muld_idx:int = -1
        for i in range(len(self.tm_rs[2])):
            if self.tm_rs[2][i][0]==True and self.tm_rs[2][i][2]==False and self.tm_ret[2][i][0]==False and self.tm_rs[2][i][4][0]==True and self.tm_rs[2][i][5][0]==True:
                if muld_idx==-1 or self.tm_rs[2][i][1]>self.tm_rs[2][muld_idx][1]:
                    muld_idx = i
        for i in range(len(self.tm_rs[2])):
            if self.tm_ret[2][i][0] == True:
                # pending. wait for consume result
                continue
            if self.tm_rs[2][i][2] == False:
                if i == muld_idx:
                    # start cal
                    self.tm_rs[2][i][2] = True
                    self.tm_ret[2][i] = [False, 0]
                    self.tm_count[2][i] = 1
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
                self.tm_rs[2][i][2] = False
                self.tm_ret[2][i] = [True, self.tm_rs[2][i][4][1] * self.tm_rs[2][i][5][1]]
                self.tm_rs[2][i][4:6] = [[False, 0], [False, 0]]

    def resolve_branch(self, tag: int, result: int | float) -> None:
        """Update the predictor with the branch outcome and flag a misprediction."""
        pc = self.dyn[tag]
        taken = result == 0 if self.inst[pc][0] == OPCODES["beq"] else result != 0
        target = pc + 1 + self.inst[pc][3][1]
        actual = target if taken else pc + 1

        idx = pc % 8
        self.bht[idx] = 1 if taken else 0
        self.btb[idx] = target

        if actual != self.pred[tag] and (self.mispredict[0] == -1 or tag < self.mispredict[0]):
            self.mispredict = (tag, actual)

    def avail_mem_rs(self) -> int:
        avail_idx = -1
        for i in range(len(self.mem_rs)):
            if self.mem_rs[i][0] == False:
                avail_idx = i
                break
        return avail_idx


    def mem_ctrl(self, mem_rdy: bool, age: bool|int|list[bool|int|float]) -> tuple[int, int]:
        # [ocp, age, strt, done, op, [valid,addr], [valid,Vj], [valid,Vk], [pos,Qj], [pos,Qk], offset]
        ex_inst, ldst_mem, fwd = -1, -1, -1

        # inc mem cycle
        if self.mem_idx != -1:
            self.mem_count = self.mem_count + 1

        # sel mem idx
        if self.mem_idx == -1:
            for i in range(len(self.mem_rs)):
                if (self.mem_idx==-1 or self.mem_rs[i][1]>self.mem_rs[self.mem_idx][1]) and self.mem_rs[i][0]==True and self.mem_rs[i][5]!=[False,0] and (self.mem_rs[i][2]==True or self.mem_rs[i][4]==OPCODES["sd"]) and self.mem_rs[i][3]==False and self.mem_rs[i][6]!=[False,0]:
                    rdy = True
                    st_idx = -1
                    if self.mem_rs[i][4] == OPCODES["ld"]:
                        # check older st
                        for j in range(len(self.mem_rs)):
                            if self.mem_rs[j][0]==True and self.mem_rs[j][4]==OPCODES["sd"] and self.ldst_isnt[j]<self.ldst_isnt[i]:
                                if self.mem_rs[j][5] == [False,0]:
                                    rdy = False
                                if self.mem_rs[j][5]!=[False,0] and self.mem_rs[j][5]==self.mem_rs[i][5]:
                                    if st_idx == -1 or self.ldst_isnt[j]>self.ldst_isnt[st_idx]:
                                        st_idx = j
                        if st_idx != -1 and self.mem_rs[st_idx][6] == [False,0]:
                            rdy = False
                    if rdy == True:
                        if (self.mem_rs[i][4]!=OPCODES["sd"] or self.mem_rs[i][2]==False) and (mem_rdy==False or age>self.mem_rs[i][1]):
                            continue
                        self.mem_idx = i
                        fwd = st_idx
            if self.mem_idx != -1:
                self.mem_count = 1

        # fin mem op
        if self.mem_idx != -1:
            if self.mem_rs[self.mem_idx][4]!=OPCODES["sd"] or self.mem_rs[self.mem_idx][2]==False:
                ldst_mem = self.ldst_isnt[self.mem_idx]
            if (self.mem_rs[self.mem_idx][4]==OPCODES["sd"] and self.mem_rs[self.mem_idx][2]==False) or fwd!=-1 or self.mem_count>=self.mem_cycles:
                if self.mem_rs[self.mem_idx][4] == OPCODES["ld"]:
                    self.mem_rs[self.mem_idx][6] = [True, self.mem_rs[fwd][6][1] if fwd!=-1 else self.mem[int(self.mem_rs[self.mem_idx][5][1]) // 4]]
                if self.mem_rs[self.mem_idx][4]==OPCODES["sd"] and self.mem_rs[self.mem_idx][2]==True:
                    # st done
                    self.mem[int(self.mem_rs[self.mem_idx][5][1]) // 4] = self.mem_rs[self.mem_idx][6][1]
                self.mem_rs[self.mem_idx][3] = True
                if self.mem_rs[self.mem_idx][4]==OPCODES["sd"] and self.mem_rs[self.mem_idx][2]==True:
                    self.free_rs(-1, self.mem_idx)
                self.mem_idx = -1
                self.mem_count = 0

        # inc mem rs insts age
        for i in range(len(self.mem_rs)):
            self.mem_rs[i][1] = self.mem_rs[i][1] + 1 if self.mem_rs[i][0]==True else 0 

        # update address rs index
        if self.mem_ex_idx == -1:
            oldest_age = -1
            for i in range(len(self.mem_rs)):
                if self.mem_rs[i][0]==True and self.mem_rs[i][5]==[False,0] and self.mem_rs[i][7]!=[False,0] and self.mem_rs[i][1]>oldest_age:
                    self.mem_ex_idx = i
                    oldest_age = self.mem_rs[i][1]
            self.mem_ex_count = 0

        # cal address
        if self.mem_ex_idx != -1:
            ex_inst = self.ldst_isnt[self.mem_ex_idx]
            self.mem_ex_count = self.mem_ex_count + 1
            if self.mem_ex_count >= self.mem_ex_cycles:
                address = self.mem_rs[self.mem_ex_idx][7][1] + self.mem_rs[self.mem_ex_idx][10]
                self.mem_rs[self.mem_ex_idx][5] = [True, address]
                # ld strt
                if self.mem_rs[self.mem_ex_idx][4] == OPCODES["ld"]:
                    self.mem_rs[self.mem_ex_idx][2] = True
                self.mem_ex_idx = -1
                self.mem_ex_count = 0
        return ex_inst, ldst_mem
    
    def finished(self) -> bool:
        # inst & st done
        return (self.pc >= len(self.inst) and self.mispredict == (-1, -1)
                and all(self.rob[i][2]==-1 for i in range(len(self.rob)))
                and all(inst == -1 for inst in self.ldst_isnt))

    def free_rs(self, group: int, slot: int) -> None:
        if group == -1:
            self.mem_rs[slot] = [False,0,False,False,-1,[False,0],[False,0],[False,0],[0,0],[0,0],0]
            self.ldst_isnt[slot] = -1
            return
        self.tm_rs[group][slot] = [False, 0, False, 0, [False, 0], [False, 0], [0, 0], [0, 0]]
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
        for i in range(len(self.rob)):
            if self.rob[i][2] == tag:
                self.rob_tail = (i + 1) % len(self.rob)
            elif self.rob[i][2] > tag:
                self.rob[i] = [False,-1,-1]
        for group in range(len(self.ex_inst)):
            for slot in range(len(self.ex_inst[group])):
                if self.ex_inst[group][slot] > tag:
                    self.free_rs(group, slot)
        for i in range(len(self.mem_rs)):
            if self.ldst_isnt[i] > tag:
                if self.mem_ex_idx == i:
                    self.mem_ex_idx = -1
                    self.mem_ex_count = 0
                if self.mem_idx == i:
                    self.mem_idx = -1
                    self.mem_count = 0
                self.free_rs(-1, i)
        if self.mem_inst > tag:
            self.free_rs(*self.mem_stage_rs)
            self.mem_inst = -1
            self.mem_stage_rs = (-1, -1)
        if self.wb_inst > tag:
            if self.wb_rs[0] != -1:
                self.free_rs(*self.wb_rs)
            self.wb_inst = -1
            self.wb_rs = (-1, -1)
        self.is_inst = -1

        self.rat_r = [-1] * len(self.arf_r)
        self.rat_f = [-1] * len(self.arf_f)
        for i in range(len(self.rob)):
            t = (self.rob_head + i) % len(self.rob)
            if self.rob[t][2]==-1 or self.rob[t][1] == -1 or self.inst[self.dyn[self.rob[t][2]]][0] == OPCODES["sd"]:
                continue
            operand = self.inst[self.dyn[self.rob[t][2]]][1]
            if operand[0] == OPERAND_TYPES["R"] and operand[1] != 0:
                self.rat_r[operand[1]] = t
            if operand[0] == OPERAND_TYPES["F"]:
                self.rat_f[operand[1]] = t

        self.pc = correct_pc
        self.mispredict = (-1, -1)
        return True

    def memory_access(self, edge: bool) -> tuple[bool, int, int]:
        # mem stage
        if not edge:
            return self.mem_done, -1, -1
        _, ex_done, ex_done_id = self.stat_ex(-1)
        ldst_ex, ldst_mem = self.mem_ctrl(self.mem_inst==-1, self.tm_rs[ex_done_id[0]][ex_done_id[1]][1] if ex_done else -1)

        # sel ex to mem
        if ex_done==True and self.mem_inst==-1 and ldst_mem==-1 and (self.mem_idx==-1 or (self.mem_rs[self.mem_idx][4]==OPCODES["sd"] and self.mem_rs[self.mem_idx][2]==True)):
            group, slot = ex_done_id
            self.mem_inst = self.ex_inst[group][slot]
            self.mem_stage_rs = ex_done_id
            self.ex_inst[group][slot] = -1
            self.mem_done_prev=False
        return self.mem_inst != -1, ldst_mem, ldst_ex

    def write_back(self, edge: bool, inst: int) -> bool:
        """Receive the selected result once and hold its value for COMMIT."""
        if not edge:
            return self.wb_done
        if inst == -1:
            return False
        if self.wb_done == True:
            return True

        rob_idx = 0
        while self.rob[rob_idx][2] != inst:
            rob_idx += 1
        group, slot = self.wb_rs
        if group == -1:
            if slot == -1:
                return False
            if self.inst[self.dyn[inst]][0] == OPCODES["sd"]:
                self.rob[rob_idx][0] = True
                return True
            self.wb_value = self.mem_rs[slot][6][1]
            self.free_rs(-1, slot)
        else:
            if self.tm_ret[group][slot][0] == False:
                return False
            self.wb_value = self.tm_ret[group][slot][1]
            self.tm_ret[group][slot][0] = False

        if self.rob[rob_idx][1] != -1:
            operand = self.inst[self.dyn[inst]][1]
            if operand[0] == OPERAND_TYPES["R"]:
                self.prf_r[self.rob[rob_idx][1]] = self.wb_value
            if operand[0] == OPERAND_TYPES["F"]:
                self.prf_f[self.rob[rob_idx][1]] = self.wb_value
        self.rob[rob_idx][0] = True
        return True

    def commit(self, edge: bool, inst: int) -> bool:
        """Commit the ready ROB head selected by module."""
        if not edge:
            return self.commit_done
        if inst != -1:
            if self.inst[self.dyn[inst]][0] == OPCODES["sd"]:
                # st strt
                self.mem_rs[self.rob[self.rob_head][1]][2] = True
                self.mem_rs[self.rob[self.rob_head][1]][3] = False
            elif self.rob[self.rob_head][1] != -1:
                operand = self.inst[self.dyn[inst]][1]
                if operand[0] == OPERAND_TYPES["R"]:
                    self.arf_r[operand[1]] = self.prf_r[self.rob[self.rob_head][1]]
                    if self.rat_r[operand[1]] == self.rob_head:
                        self.rat_r[operand[1]] = -1
                if operand[0] == OPERAND_TYPES["F"]:
                    self.arf_f[operand[1]] = self.prf_f[self.rob[self.rob_head][1]]
                    if self.rat_f[operand[1]] == self.rob_head:
                        self.rat_f[operand[1]] = -1
            self.rob[self.rob_head] = [False,-1,-1]
            self.rob_head = (self.rob_head + 1) % len(self.rob)
        return inst != -1

    def module(self, rising_edge):
        ldst_ex, ldst_mem = -1, -1
        if rising_edge == True:
            recovering = self.recover()
            if self.wb_done_prev == True and self.wb_rs != (-1, -1):
                rob_idx = 0
                while self.rob[rob_idx][2] != self.wb_inst:
                    rob_idx += 1
                operand = self.inst[self.dyn[self.wb_inst]][1]
                for group in range(len(self.tm_rs)):
                    for slot in range(len(self.tm_rs[group])):
                        if self.ex_inst[group][slot] == -1:
                            continue
                        sources = self.inst[self.dyn[self.ex_inst[group][slot]]][1:3] if self.inst[self.dyn[self.ex_inst[group][slot]]][0] in (OPCODES["beq"], OPCODES["bne"]) else self.inst[self.dyn[self.ex_inst[group][slot]]][2:4]
                        for i in range(2):
                            if (self.inst[self.dyn[self.wb_inst]][0] != OPCODES["sd"]
                                and self.rob[rob_idx][1] != -1
                                and self.tm_rs[group][slot][i + 4] == [False, 0]
                                and self.tm_rs[group][slot][i + 6] == [1, self.rob[rob_idx][1]]
                                and sources[i][0] == operand[0]):
                                self.tm_rs[group][slot][i + 4] = [True, self.wb_value]
                # update mem rs sources
                for slot in range(len(self.mem_rs)):
                    if self.mem_rs[slot][0] == False:
                        continue
                    for i in range(2):
                        if (self.inst[self.dyn[self.wb_inst]][0] != OPCODES["sd"]
                            and self.rob[rob_idx][1] != -1
                            and self.mem_rs[slot][i + 6] == [False, 0]
                            and self.mem_rs[slot][i + 8] == [1, self.rob[rob_idx][1]]
                            and operand[0] == (OPERAND_TYPES["F"] if i == 0 else OPERAND_TYPES["R"])):
                            self.mem_rs[slot][i + 6] = [True, self.wb_value]
                group, slot = self.wb_rs
                if group != -1:
                    self.tm_rs[group][slot][0] = False
                self.wb_rs = (-1, -1)
                self.wb_inst = -1
            self.commit_inst = -1
            if self.rob[self.rob_head][0] == True:
                self.commit_inst = self.rob[self.rob_head][2]
                self.commit_done_prev=False

            # select oldest wb result
            if self.wb_inst == -1:
                selected = self.mem_inst if self.mem_done_prev == True else -1
                selected_rs = self.mem_stage_rs
                for i in range(len(self.mem_rs)):
                    inst = self.ldst_isnt[i]
                    if inst != -1 and self.mem_rs[i][3]==True:
                        for t in range(len(self.rob)):
                            if self.rob[t][2]==inst and self.rob[t][0]==False:
                                if selected == -1 or inst < selected:
                                    selected = inst
                                    selected_rs = (-1, i)
                                break
                if selected != -1:
                    self.wb_inst = selected
                    self.wb_rs = selected_rs
                    if selected_rs[0] != -1:
                        self.mem_inst = -1
                        self.mem_stage_rs = (-1, -1)
                    self.wb_done=False
                    self.wb_done_prev=False
            if self.is_done_prev == True:
                self.is_inst = -1
            if self.is_inst == -1 and self.pc < len(self.inst) and not recovering and self.rob[self.rob_tail][2]==-1:
                self.is_inst = len(self.dyn)
                self.dyn.append(self.pc)
                self.squashed.append(False)
                self.rob[self.rob_tail] = [False,-1,self.is_inst]
                self.rob_tail = (self.rob_tail + 1) % len(self.rob)
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
        # ret st commit
        commit_ret = [self.commit_inst if self.commit_done_prev == False else -1]
        for i in range(len(self.mem_rs)):
            if self.mem_rs[i][0]==True and self.mem_rs[i][4]==OPCODES["sd"] and self.mem_rs[i][2]==True and self.ldst_isnt[i]!=self.commit_inst:
                commit_ret.append(self.ldst_isnt[i])
        self.wb_done = self.write_back(edge=rising_edge, inst=self.wb_inst)
        self.mem_done, ldst_mem, ldst_ex = self.memory_access(edge=rising_edge)
        self.ex_done = self.execute(edge=rising_edge)

        ex_ret = [[-1] * len(group) for group in self.ex_inst]
        for i in range(len(self.ex_inst)):
            for j in range(len(self.ex_inst[i])):
                ex_ret[i][j] = self.ex_inst[i][j] if self.ex_done_prev[i][j] == False and self.tm_count[i][j] > 0 else -1
        ex_ret.append([ldst_ex])

        self.is_done = self.issue(edge=rising_edge, inst=self.is_inst)
        ret = [True, self.is_inst if self.is_done == True else -1,\
                ex_ret, [self.mem_inst if self.mem_done_prev == False else -1, ldst_mem],\
                self.wb_inst if self.wb_done_prev == False else -1,\
                commit_ret]
        
        self.is_done_prev = self.is_done 
        self.ex_done_prev = [group.copy() for group in self.ex_done]
        self.mem_done_prev = self.mem_done
        self.wb_done_prev = self.wb_done
        self.commit_done_prev = self.commit_done

        return ret
        
        

