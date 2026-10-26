import csv
from pathlib import Path
from typing import Final, assert_never
import arch

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

type StageState = int | list[StageState] | tuple[StageState, ...]


class Testbench:
    def __init__(self) -> None:
        self.module: arch.Arch
        self.clock_counter: int = 0
        self.filename: str = ""
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
                OPCODES[row[0].lower()],
                *(
                    (OPERAND_TYPES[operand[:1].upper()], int(operand[1:]))
                    if operand[:1].upper() in OPERAND_TYPES
                    else (OPERAND_TYPES["none"], int(operand) if operand else 0)
                    for operand in row[1:4]
                ),
            ]
            for row in instruction_rows
        ]
        self.exp_trace = [
            [int(value) if value else 0 for value in row[4:12]]
            for row in instruction_rows
        ]
        self.ret_trace = []
        self.filename = path.name

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
        opcode_names = {value: name.capitalize() for name, value in OPCODES.items()}
        operand_prefixes = {
            OPERAND_TYPES["none"]: "",
            OPERAND_TYPES["R"]: "R",
            OPERAND_TYPES["F"]: "F",
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
    
    def running(self):
        if self.clock_counter==0 | self.ret[self.clock_counter][0]==True:
            self.clock_counter = self.clock_counter + 1
            self.ret[self.clock_counter] = self.module(rising_edge = True)
        else:
            self.ret[self.clock_counter] = self.module(rising_edge = False)

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


if __name__ == "__main__":
    tb = Testbench()
    tb.csv_loader("cat_1.csv")
    tb.module = arch.Arch(tb.instructions, tb.mem, tb.rr, tb.rf)
    print(f"Loaded {len(tb.instructions)} instructions from cat_1.csv")
