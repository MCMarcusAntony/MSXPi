;|===========================================================================|
;|                                                                           |
;| MSXPi Interface                                                           |
;|                                                                           |
;| Version : 1.0                                                             |
;|                                                                           |
;| Copyright (c) 2015-2020 Ronivon Candido Costa (ronivon@outlook.com)       |
;|                                                                           |
;| All rights reserved                                                       |
;|                                                                           |
;| Redistribution and use in source and compiled forms, with or without      |
;| modification, are permitted under GPL license.                            |
;|                                                                           |
;|===========================================================================|
;|                                                                           |
;| This file is part of MSXPi Interface project.                             |
;|                                                                           |
;| MSX PI Interface is free software: you can redistribute it and/or modify  |
;| it under the terms of the GNU General Public License as published by      |
;| the Free Software Foundation, either version 3 of the License, or         |
;| (at your option) any later version.                                       |
;|                                                                           |
;| MSX PI Interface is distributed in the hope that it will be useful,       |
;| but WITHOUT ANY WARRANTY; without even the implied warranty of            |
;| MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the             |
;| GNU General Public License for more details.                              |
;|                                                                           |
;| You should have received a copy of the GNU General Public License         |
;| along with MSX PI Interface.  If not, see <http://www.gnu.org/licenses/>. |
;|===========================================================================|
;
; File history :
; 0.1    : Initial version.
; 1.0    : For MSXPi interface with /buswait support

; Start of command - You may not need to change this
        org     $0100
        ld      bc,COMMAND_END - COMMAND
        ld      hl,COMMAND
        call    DOSSENDPICMD
        call    PIREADBYTE    ; read return code
        cp      RC_WAIT
        call    z,CHKPIRDY
        CALL    PTEST
        RET

PTEST:
       ld      hl,txt_testsend
       call    PRINT
       ld      de,0
LOOP:
       ld      a,e
       call    PIWRITEBYTE
       ;call    waitrpi
       ld      a,d
       call    PIWRITEBYTE
       ;call    waitrpi
       inc     de
       ld      a,d
       or      e
       jr      nz,LOOP

PTEST_RECV:
       ld      hl,txt_testrecv
       call    PRINT

       ld      hl,0
       ld      de,0
LOOP_RECV:
       call    PIREADBYTE
       ;call    waitrpi
       cp      l
       jr      z,LOOP1
       inc     de
LOOP1:
       call    PIREADBYTE
       ;call    waitrpi
       cp      h
       jr      z,LOOP2
       inc     de
LOOP2:
       inc     hl
       ld      a,h
       or      l
       jr      nz,LOOP_RECV
       
       ld      hl,txt_recv
       call    PRINT
       ld      a,D
       call    PRINTNUMBER
       ld      a,E
       call    PRINTNUMBER
       ret

waitrpi:
       push   bc
       ld     b,0
waitpi2:
       djnz   waitpi2
       pop    bc
       ret

txt_send: DB      "Errors sending:$"
txt_recv: DB      "Errors receiving:$"
txt_testsend: DB "Testing Transmission",13,10,"$"
txt_testrecv: DB "Testing reception",13,10,"$"

INCLUDE "include.asm"
INCLUDE "msxpi_bios.asm"
INCLUDE "msxpi_io.asm"
INCLUDE "msxdos_stdio.asm"

COMMAND:     DB      "ptest"
COMMAND_SPC: DB " " ; Do not remove this space, do not add code or data after this buffer.
COMMAND_END: EQU $