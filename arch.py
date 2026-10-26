"""Minimal one-clock interface for the existing Tomasulo simulator."""

from tomasulo_main import tomasula_simulator


class Arch(tomasula_simulator):
    def __init__(self, inst, mem, reg_r, reg_f):
        self.inst = inst
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
        self.mem_inst: int = -1
        self.mem_inst_pending: int = -1
        self.mem_done:  bool = True
        self.mem_done_prev: bool = True
        self.wb_inst: int = -1
        self.wb_inst_pending: int = -1
        self.wb_done:  bool = True
        self.wb_done_prev: bool = True
        self.commit_inst: int = -1
        self.commit_inst_pending: int = -1
        self.commit_done:  bool = True
        self.commit_done_prec: bool = True
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
                    if instruction == -1:
                        available = (group, slot)
                        break
        for group, instructions in enumerate(self.ex_inst):
            for slot, instruction in enumerate(instructions):
                if instruction != -1 and self.ex_done_prev[group][slot]:
                    return available, True, (group, slot)
        return available, False, (-1, -1)

    def module(self, rising_edge):
        if rising_edge == True:
            ex_avail_id, ex_done, ex_done_id = self.stat_ex(self.is_inst)
            if (self.commit_done_prev==True):
                self.commit_inst=-1
            if(self.wb_done_prev==True and self.commit_inst==-1):
                self.commit_inst = self.wb_inst
                self.wb_inst = -1
                self.commit_done_prev=False
            if(self.mem_done_prev==True and self.wb_inst==-1):
                self.wb_inst = self.mem_inst
                self.mem_inst = -1
                self.wb_done_prev=False
            if(ex_done==True and self.mem_inst==-1):
                group, slot = ex_done_id
                self.mem_inst = self.ex_inst[group][slot]
                self.ex_inst[group][slot] = -1
                self.mem_done_prev=False
            if self.is_done_prev and self.is_inst != -1 and ex_avail_id != (-1, -1):
                group, slot = ex_avail_id
                self.ex_inst[group][slot] = self.is_inst
                self.ex_done_prev[group][slot] = False
                self.is_inst = -1
            if(self.is_inst==-1):
                self.is_inst = self.inst_num
                self.inst_num = self.nxt_inst()
                self.is_done_prev=False 

        self.is_done = self.issue(edge=rising_edge, inst=self.inst[self.is_inst])
        self.ex_done = self.execute(edge=rising_edge, inst=self.inst[self.ex_inst])
        self.mem_done = self.memory_access(edge=rising_edge, inst=self.inst[self.mem_inst])
        self.wb_done = self.write_back(edge=rising_edge, inst=self.inst[self.wb_inst])
        self.commit_done = self.commit(edge=rising_edge, inst=self.inst[self.commit_inst])

        ret = [True,-1 if self.is_done_prev else self.is_inst,-1 if self.ex_done_prev else self.ex_inst,\
                -1 if self.mem_done_prev else self.mem_inst, -1 if self.wb_done_prev else self.wb_inst,\
                    -1 if self.commit_done_prev else self.commit_inst]
        
        self.is_done_prev = self.is_done 
        self.ex_done_prev = [group.copy() for group in self.ex_done]
        self.mem_done_prev = self.mem_done
        self.wb_done_prev = self.wb_done
        self.commit_done_prev = self.commit_done

        return ret
        
        

    def step(self) -> None:
        """Execute the original pipeline stages once, in their original order."""
        self.clock: int = self.clock + 1
        self.commit()
        self.write_back()
        self.memory_access()
        self.execute()
        self.issue()
