Mult.d F10, F1, F2
Add.d F4, F10, F3
Add.d F10, F5, F6
Add.d F11, F7, F8
Add.d F12, F8, F9
Sd F2, 0(R0)
Sd F3, 0(R0)
Ld F13, 0(R0)
Addi R20, R0, 8
Ld F14, -4(R20)
Sub.d F15, F13, F14
Add R21, R1, R2
Sub R22, R1, R2
Addi R0, R0, 99
Addi R23, R0, 3
Addi R23, R23, -1
Bne R23, R0, -2
Beq R23, R0, 1
Sd F15, 0(R0)
NOP
