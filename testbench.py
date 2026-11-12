import csv
import json
from pathlib import Path
from typing import assert_never
import arch

type StageState = int | list[StageState] | tuple[StageState, ...]


class Testbench:
    def __init__(self) -> None:
        self.module: arch.Arch
        self.clock_counter: int = 0
        self.filename: str = ""
        self.config: dict[str, int | dict[str, dict[str, int]]] = {}
        self.instructions: list[list[int | tuple[int, int]]] = []
        self.inst_prog: int = 0
        self.mem: list[float] = []
        self.rr: list[int] = []
        self.rf: list[float] = []
        self.exp_mem: list[float] = []
        self.exp_rr: list[int] = []
        self.exp_rf: list[float] = []
        self.ret: list[list[StageState]] = []
        self.ret_mem: list[float] = []
        self.ret_rr: list[int] = []
        self.ret_rf: list[float] = []
        self.ret_trace: list[list[int]] = []
        self.exp_trace: list[list[int]] = []

    def csv_loader(self, filename: str | Path) -> None:
        path = Path(__file__).resolve().parent / "input" / filename
        with path.open(encoding="utf-8-sig", newline="") as csv_file:
            rows = [
                [cell.strip() for cell in row]
                for row in csv.reader(csv_file)
                if any(cell.strip() for cell in row)
            ]

        states = {
            row[0]: [value for value in row[1:] if value]
            for row in rows[:6]
        }
        self.rr = [int(value) for value in states["init_R"]]
        self.rf = [float(value) for value in states["init_F"]]
        self.mem = [float(value) for value in states["init_MEM"]]
        self.exp_rr = [int(value) for value in states["ret_R"]]
        self.exp_rf = [float(value) for value in states["ret_F"]]
        self.exp_mem = [float(value) for value in states["ret_MEM"]]
        instruction_rows = rows[7:]
        self.instructions = [
            [
                arch.OPCODES[row[0].lower()],
                *(
                    (arch.OPERAND_TYPES[operand[:1].upper()], int(operand[1:]))
                    if operand[:1].upper() in arch.OPERAND_TYPES
                    else (arch.OPERAND_TYPES["none"], int(operand) if operand else 0)
                    for operand in row[1:4]
                ),
            ]
            for row in instruction_rows
        ]
        self.exp_trace = [
            [int(value) if value else 0 for value in row[4:12]]
            for row in instruction_rows
        ]
        self.inst_text = [
            f"{row[0]} {', '.join(operand for operand in row[1:4] if operand)}"
            for row in instruction_rows
        ]
        self.ret_trace = []
        self.filename = path.name

    def asm_loader(self, filename: str | Path) -> None:
        path = Path(__file__).resolve().parent / "input" / filename
        self.instructions = []
        self.inst_text = []
        with path.open(encoding="utf-8-sig") as asm_file:
            for line in asm_file:
                text = line.split("#", 1)[0].strip()
                if not text:
                    continue
                parts = text.replace(",", " ").replace("(", " ").replace(")", " ").split()
                instruction: list[int | tuple[int, int]] = [arch.OPCODES[parts[0].lower()]]
                for operand in parts[1:]:
                    prefix = operand[:1].upper()
                    if prefix in arch.OPERAND_TYPES:
                        instruction.append((arch.OPERAND_TYPES[prefix], int(operand[1:])))
                    else:
                        instruction.append((0, int(operand)))
                while len(instruction) < 4:
                    instruction.append((0, 0))
                self.instructions.append(instruction)
                self.inst_text.append(text)
        self.filename = path.name

    def mem_loader(self, filename: str | Path) -> None:
        path = Path(__file__).resolve().parent / "input" / filename
        self.mem = [0.0] * 64
        index = 0
        with path.open(encoding="utf-8-sig") as mem_file:
            for line in mem_file:
                for value in line.split("#", 1)[0].split():
                    self.mem[index] = float(value)
                    index += 1

    def rr_loader(self, filename: str | Path) -> None:
        path = Path(__file__).resolve().parent / "input" / filename
        self.rr = []
        with path.open(encoding="utf-8-sig") as rr_file:
            for line in rr_file:
                for value in line.split("#", 1)[0].split():
                    self.rr.append(int(value))

    def rf_loader(self, filename: str | Path) -> None:
        path = Path(__file__).resolve().parent / "input" / filename
        self.rf = []
        with path.open(encoding="utf-8-sig") as rf_file:
            for line in rf_file:
                for value in line.split("#", 1)[0].split():
                    self.rf.append(float(value))

    def json_loader(self, filename: str | Path) -> None:
        path = Path(__file__).resolve().parent / "input" / filename
        with path.open(encoding="utf-8-sig") as json_file:
            self.config = json.load(json_file)

    def exp_loader(self, filename: str | Path) -> None:
        path = Path(__file__).resolve().parent / "input" / filename
        with path.open(encoding="utf-8-sig", newline="") as exp_file:
            rows = [row for row in csv.reader(exp_file) if any(row)]
        self.exp_rr = [int(value) for value in rows[0][1:] if value]
        self.exp_rf = [float(value) for value in rows[1][1:] if value]
        self.exp_mem = [float(value) for value in rows[2][1:] if value]
        self.exp_trace = []
        for row in rows[4:]:
            self.exp_trace.append([int(value) if value else 0 for value in row[4:12]])

    def csv_writer(self) -> None:
        rows: list[list[str | int | float]] = [
            ["init_R", *self.rr],
            ["init_F", *self.rf],
            ["init_MEM", *self.mem],
            ["ret_R", *self.ret_rr],
            ["ret_F", *self.ret_rf],
            ["ret_MEM", *self.ret_mem],
            [
                "", "", "", "",
                "ISSUE", "EX_start", "EX_end", "MEM_start", "MEM_end",
                "WB", "COMMIT_start", "COMMIT_end",
            ],
        ]
        opcode_names = {value: name.capitalize() for name, value in arch.OPCODES.items()}
        operand_prefixes = {
            arch.OPERAND_TYPES["none"]: "",
            arch.OPERAND_TYPES["R"]: "R",
            arch.OPERAND_TYPES["F"]: "F",
        }
        for instruction, trace in zip(self.instructions, self.ret_trace, strict=True):
            row: list[str | int | float] = []
            for value in instruction:
                match value:
                    case 0:
                        row.extend(["NOP", "", "", ""])
                        break
                    case int(opcode):
                        row.append(opcode_names[opcode])
                    case (operand_type, operand_value):
                        row.append(f"{operand_prefixes[operand_type]}{operand_value}")
                    case unreachable:
                        assert_never(unreachable)
            row.extend(clock if clock else "" for clock in trace)
            rows.append(row)

        path = Path(__file__).resolve().parent / "output" / self.filename
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8-sig", newline="") as csv_file:
            csv.writer(csv_file).writerows(rows)

    def print_report(self):
        span = lambda start, end: str(start) if start == end else f"{start}-{end}"
        print(f"===== {self.filename} =====")

        print(f"{'':24}{'ISSUE':>8}{'EX':>8}{'MEM':>8}{'WB':>8}{'COMMIT':>8}")
        for text, t in zip(self.inst_text, self.ret_trace):
            cells = [t[0], span(t[1], t[2]), span(t[3], t[4]), t[5], span(t[6], t[7])]
            print(f"{text:24}" + "".join(f"{cell:>8}" for cell in cells))

        print("\nREGISTER VALUES")
        for i in range(0, 32, 8):
            print("  ".join(f"R{j}={self.ret_rr[j]}" for j in range(i, i + 8)))
        for i in range(0, 32, 8):
            print("  ".join(f"F{j}={self.ret_rf[j]:g}" for j in range(i, i + 8)))

        print("\nNON-ZERO MEMORY VALUES")
        print("  ".join(f"[{4 * i}]={v:g}" for i, v in enumerate(self.ret_mem) if v) or "(none)")
        passed = (self.ret_trace == self.exp_trace and self.ret_rr == self.exp_rr
                  and self.ret_rf == self.exp_rf and self.ret_mem == self.exp_mem)

        print(f"\n{self.clock_counter} cycles: {'PASS' if passed else 'FAIL'}\n\n")

    def ret_to_trace(self) -> None:
        self.ret_trace = [[0] * 8 for _ in self.instructions]
        previous: list[set[int]] = [set() for _ in range(5)]
        finished: list[set[int]] = [set() for _ in range(5)]
        for clock, record in enumerate(self.ret[1:], start=1):
            if not record:
                continue
            for stage, (start, end) in enumerate(((0, 0), (1, 2), (3, 4), (5, 5), (6, 7))):
                active: set[int] = set()
                pending: list[StageState] = [record[stage + 1]]
                while pending:
                    value = pending.pop()
                    match value:
                        case int():
                            if value >= 0:
                                active.add(value)
                        case list() | tuple():
                            pending.extend(value)
                        case _:
                            assert_never(value)
                finished[stage].update(previous[stage] - active)
                for instruction in active - finished[stage]:
                    trace = self.ret_trace[instruction]
                    if trace[start] == 0:
                        trace[start] = clock
                    if end != start:
                        trace[end] = clock
                previous[stage] = active

    def post_proc(self) -> None:
        self.ret_mem = self.module.mem
        self.ret_rr = self.module.reg_r
        self.ret_rf = self.module.reg_f
        self.ret_to_trace()

    def running(self) -> None:
        if self.clock_counter == 0:
            self.ret = [[]]
        if self.clock_counter == 0 or self.ret[self.clock_counter][0]:
            self.clock_counter += 1
            self.ret.append(self.module.module(rising_edge=True))
        else:
            self.ret[self.clock_counter] = self.module.module(rising_edge=False)
        if self.ret[self.clock_counter][0] and self.module.commit_done:
            self.inst_prog += 1


if __name__ == "__main__":
    for filename in ["cat_1.asm", "cat_2.asm"]:
        tb = Testbench()
        tb.asm_loader(filename)
        tb.mem_loader("../default_mem.mem")
        tb.rr_loader("../default_rr.mem")
        tb.rf_loader("../default_rf.mem")
        tb.json_loader("../default_config.json")
        tb.exp_loader(f"exp_{Path(filename).stem}.csv")
        tb.module = arch.Arch(tb.instructions, tb.mem, tb.rr, tb.rf, tb.config)
        while tb.inst_prog < len(tb.instructions):
            tb.running()
        tb.post_proc()
        tb.print_report()
