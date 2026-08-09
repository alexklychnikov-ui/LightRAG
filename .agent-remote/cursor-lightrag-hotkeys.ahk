#Requires AutoHotkey v2.0
#SingleInstance Force

PasteCommand(text) {
    clipSaved := ClipboardAll()
    A_Clipboard := text
    if ClipWait(0.5) {
        Send("^v")
    } else {
        SendText(text)
    }
    Sleep(60)
    A_Clipboard := clipSaved
}

#HotIf WinActive("ahk_exe Cursor.exe")
F6::PasteCommand("@lightrag ? ")
F7::PasteCommand("@lightrag + ")
F8::PasteCommand("@lightrag status")
#HotIf
