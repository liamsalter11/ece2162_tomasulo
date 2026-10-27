"""Clocked stages for the Tomasulo architecture under construction."""


class Arch:
    def __init__(self, inst, mem, reg_r, reg_f):
        self.inst = inst
        # Add R3, R1, R2 == [5, (1, 3), (1, 1), (1, 2)] 
        self.mem = mem.copy()
        self.reg_r = reg_r.copy()
        self.reg_f = reg_f.copy()
        self.inst_num = 0

        self.is_inst: int = -1
        self.is_inst_pending: int = -1
        self.is_done: bool = True
        self.is_done_prev: bool = True

        self.ex_inst: list[list[int]] = [[-1, -1], [-1, -1, -1], [-1, -1]]
        self.ex_inst_pending: list[list[int]] = [[-1, -1], [-1, -1, -1], [-1, -1]]
        self.ex_done: list[list[bool]] = [[True, True], [True, True, True], [True, True]]
        self.ex_done_prev: list[list[bool]] = [[True, True], [True, True, True], [True, True]]

        #  add.i [0][0:1][ocp, busy, op, [valid,Vj], [valid,Vk], [pos,Qj], [pos,Qk]]
        #  add.d [1][0:2][ocp, busy, op, [valid,Vj], [valid,Vk], [pos,Qj], [pos,Qk]]
        #  mux.i [2][0:1][ocp, busy, op, [valid,Vj], [valid,Vk], [pos,Qj], [pos,Qk]]
        self.tm_cycles: tuple[int, int, int] = (1, 3, 20)
        self.tm_rs: list[list[list[bool|int|list[bool|int]]]] = \
            [[[False,False,0,[False,0],[False,0],[0,0],[0,0]], [False,False,0,[False,0],[False,0],[0,0],[0,0]]], \
            [[False,False,0,[False,0],[False,0],[0,0],[0,0]], [False,False,0,[False,0],[False,0],[0,0],[0,0]], [False,False,0,[False,0],[False,0],[0,0],[0,0]]], \
            [[False,False,0,[False,0],[False,0],[0,0],[0,0]], [False,False,0,[False,0],[False,0],[0,0],[0,0]]]]
        self.tm_count: list[list[int]] = [[0, 0], [0, 0, 0], [0, 0]]
        #  add.i [0][0:1][valid,value,ROB tag] add.d [1][0:2][valid,value,ROB tag] mux.i [2][0:1][valid,value,ROB tag]
        self.tm_ret: list[list[list[bool|int]]] = [[[False,0,0], [False,0,0]], [[False,0,0], [False,0,0], [False,0,0]], [[False,0,0], [False,0,0]]]
        
        self.mem_inst: int = -1
        self.mem_inst_pending: int = -1
        self.mem_rs: tuple[int, int] = (-1, -1)
        self.mem_done:  bool = True
        self.mem_done_prev: bool = True
        self.mem_cycles: int = 4
        self.mem_count: int = 0

        self.wb_inst: int = -1
        self.wb_inst_pending: int = -1
        self.wb_rs: tuple[int, int] = (-1, -1)
        self.wb_value: int | float = 0
        self.wb_done:  bool = True
        self.wb_done_prev: bool = True

        self.rob: list[list[bool | int | float]] = []
        for i in range(len(self.inst)):
            self.rob.append([False, 0])
        self.rob_head: int = 0

        self.commit_inst: int = -1
        self.commit_inst_pending: int = -1
        self.commit_done:  bool = True
        self.commit_done_prev: bool = True

        self.ldst_isnt: list[int] = [-1, -1, -1]
        self.ldst_isnt_pending: tuple[int, int, int] = (-1,-1,-1)
        self.ldst_done: list[bool] = [True, True, True]
        self.ldst_done_prev: list[bool] = [True, True, True]

    def stat_ex(self, inst_num: int) -> tuple[tuple[int, int], bool, tuple[int, int]]:
        available = (-1, -1)
        if inst_num >= 0:
            group = {0: 0, 3: 0, 4: 0, 5: 0, 6: 1, 7: 0,
                     8: 0, 9: 1, 10: 2}.get(self.inst[inst_num][0], -1)
            if group != -1:
                for slot, instruction in enumerate(self.ex_inst[group]):
                    if (instruction == -1
                        and not self.tm_rs[group][slot][0]
                        and not self.tm_rs[group][slot][1]
                        and not self.tm_ret[group][slot][0]):
                        available = (group, slot)
                        break
        for group, instructions in enumerate(self.ex_inst):
            for slot, instruction in enumerate(instructions):
                if instruction != -1 and self.tm_ret[group][slot][0]:
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

        self.tm_rs[group][slot] = [True, False, self.inst[inst][0],
                                  [False, 0], [False, 0], [0, 0], [0, 0]]
        for i in range(2):
            operand = self.inst[inst][i + 2]
            value = operand[1]
            if operand[0] == 1:
                value = self.reg_r[operand[1]]
            if operand[0] == 2:
                value = self.reg_f[operand[1]]
            self.tm_rs[group][slot][i + 3] = [True, value]

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
        for i in range(2):
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
                self.tm_ret[0][i] = [True, self.tm_rs[0][i][3][1] + self.tm_rs[0][i][4][1]] if self.tm_rs[0][i][2] in (5,7) \
                                        else [True, self.tm_rs[0][i][3][1] - self.tm_rs[0][i][4][1]] 
                self.tm_rs[0][i][3:5] = [[False, 0], [False, 0]]


        addd_idx: bool = False
        for i in range(3):
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
                self.tm_ret[1][i] = [True, self.tm_rs[1][i][3][1] + self.tm_rs[1][i][4][1]] if self.tm_rs[1][i][2] == 6 \
                                        else [True, self.tm_rs[1][i][3][1] - self.tm_rs[1][i][4][1]] 
                self.tm_rs[1][i][3:5] = [[False, 0], [False, 0]]

        muld_idx:bool = False
        for i in range(2):
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

    def memory_access(self, edge: bool, inst: int) -> bool:
        """Time LD/SD memory access; other operations pass through in one cycle."""
        if not edge:
            return self.mem_done
        if inst == -1:
            self.mem_count = 0
            return False
        cycles = self.mem_cycles if self.inst[inst][0] in (1, 2) else 1
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
            operand = self.inst[inst][1]
            if operand[0] == 1 and operand[1] != 0:
                self.reg_r[operand[1]] = self.rob[inst][1]
            if operand[0] == 2:
                self.reg_f[operand[1]] = self.rob[inst][1]
            self.rob_head += 1
        return inst != -1

    def module(self, rising_edge):
        if rising_edge == True:
            _, ex_done, ex_done_id = self.stat_ex(self.is_inst)
            if self.wb_done_prev == True and self.wb_rs != (-1, -1):
                group, slot = self.wb_rs
                self.tm_rs[group][slot][0] = False
                self.wb_rs = (-1, -1)
                self.wb_inst = -1
            self.commit_inst = -1
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
            if self.is_inst == -1 and self.inst_num < len(self.inst):
                self.is_inst = self.inst_num
                self.inst_num += 1
                self.is_done_prev=False 

        self.commit_done = self.commit(edge=rising_edge, inst=self.commit_inst)
        self.wb_done = self.write_back(edge=rising_edge, inst=self.wb_inst)
        self.mem_done = self.memory_access(edge=rising_edge, inst=self.mem_inst)
        self.ex_done = self.execute(edge=rising_edge)

        ex_ret = [[-1, -1], [-1, -1, -1], [-1, -1]]
        for i in range(len(self.ex_inst)):
            for j in range(len(self.ex_inst[i])):
                ex_ret[i][j] = self.ex_inst[i][j] if self.ex_done_prev[i][j] == False else -1

        self.is_done = self.issue(edge=rising_edge, inst=self.is_inst)
        ret = [True, self.is_inst if self.is_done_prev == False else -1,\
                ex_ret, self.mem_inst if self.mem_done_prev == False else -1,\
                self.wb_inst if self.wb_done_prev == False else -1,\
                self.commit_inst if self.commit_done_prev == False else -1]
        
        self.is_done_prev = self.is_done 
        self.ex_done_prev = [group.copy() for group in self.ex_done]
        self.mem_done_prev = self.mem_done
        self.wb_done_prev = self.wb_done
        self.commit_done_prev = self.commit_done

        return ret
        
        

