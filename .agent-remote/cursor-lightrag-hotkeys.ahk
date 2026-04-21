#Requires AutoHotkey v2.0

; Global hotkeys for Cursor/Antigravity chat input
; Works when Cursor window is active and caret is in chat box.

#HotIf WinActive("ahk_exe Antigravity.exe") || WinActive("ahk_exe Cursor.exe")

F6::
{
    SendText("@lightrag ? ")
}

F7::
{
    SendText("@lightrag + ")
}

F8::
{
    SendText("@lightrag status")
}

#HotIf
