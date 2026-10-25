import csv
from pathlib import Path
from typing import Final, assert_never


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


class Testbench:
    def __init__(self) -> None:
        clock_counter: int = 0
        self.filename: str = ""
        self.instructions: list[list[int | tuple[int, int]]] = []
        self.mem: list[float] = []
        self.rr: list[int] = []
        self.rf: list[float] = []
        self.exp_mem: list[float] = []
        self.exp_rr: list[int] = []
        self.exp_rf: list[float] = []
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


if __name__ == "__main__":
    testbench = Testbench()
    testbench.csv_loader("cat_1.csv")
    print(f"Loaded {len(testbench.instructions)} instructions from cat_1.csv")
