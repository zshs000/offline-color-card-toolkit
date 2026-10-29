Unicode true
RequestExecutionLevel user
!ifdef VALIDATION
SetCompress off
!else
SetCompressor /SOLID lzma
SetCompressorDictSize 16
!endif
!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "FileFunc.nsh"
!include "x64.nsh"

!ifdef VALIDATION
!define APP_ID "OfflineColorCardToolkit-InstallerValidation"
!define APP_NAME "线下色卡采集工具集（安装验证）"
!else
!define APP_ID "OfflineColorCardToolkit"
!define APP_NAME "线下色卡采集工具集"
!endif
!define APP_EXE "线下色卡采集工具集.exe"
!define UNINSTALL_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}"

Name "${APP_NAME}"
OutFile "${OUTPUT}"
InstallDir "$LOCALAPPDATA\Programs\${APP_ID}"
InstallDirRegKey HKCU "${UNINSTALL_KEY}" "InstallLocation"
ShowInstDetails show
ShowUninstDetails show
VIProductVersion "${APP_VERSION}.0"
VIAddVersionKey /LANG=2052 "ProductName" "${APP_NAME}"
VIAddVersionKey /LANG=2052 "FileDescription" "线下色卡采集工具集安装向导"
VIAddVersionKey /LANG=2052 "FileVersion" "${APP_VERSION}"
VIAddVersionKey /LANG=2052 "ProductVersion" "${APP_VERSION}"
VIAddVersionKey /LANG=2052 "LegalCopyright" "Offline Color Card Toolkit"

!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TITLE "安装${APP_NAME} ${APP_VERSION}"
!define MUI_WELCOMEPAGE_TEXT "向导将为当前用户安装程序，无需管理员权限。$\r$\n$\r$\n更新时请先关闭工具。配置和日志保存在用户目录，图片和Word文件保留在原保存位置。"
!insertmacro MUI_PAGE_WELCOME
!define MUI_PAGE_CUSTOMFUNCTION_LEAVE CheckDirectory
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_TEXT "安装完成。可从桌面或开始菜单打开工具。$\r$\n$\r$\n以后运行新版安装包即可更新程序，配置、日志及工作文件都会保留。"
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!define MUI_FINISHPAGE_TEXT "程序已卸载。配置、日志及您保存的图片、Word文件已保留。"
!insertmacro MUI_UNPAGE_FINISH
!insertmacro MUI_LANGUAGE "SimpChinese"

Function .onInit
  ${IfNot} ${RunningX64}
    MessageBox MB_OK|MB_ICONSTOP "本安装包需要64位Windows。"
    Abort
  ${EndIf}
  SetRegView 64
  SetShellVarContext current
  ReadRegStr $0 HKCU "${UNINSTALL_KEY}" "InstallLocation"
  ${If} $0 != ""
    StrCpy $INSTDIR $0
  ${EndIf}
FunctionEnd

Function CheckDirectory
  ReadRegStr $0 HKCU "${UNINSTALL_KEY}" "InstallLocation"
  ${If} $0 != ""
  ${AndIf} $INSTDIR != $0
    MessageBox MB_OK|MB_ICONSTOP "更新请使用原安装目录：$0。配置和工作文件会保留。"
    Abort
  ${EndIf}
  ${GetRoot} "$INSTDIR" $0
  ${If} $INSTDIR == "$0\"
  ${OrIf} $INSTDIR == "$WINDIR"
  ${OrIf} $INSTDIR == "$PROFILE"
  ${OrIf} $INSTDIR == "$LOCALAPPDATA"
    MessageBox MB_OK|MB_ICONSTOP "请选择独立的程序文件夹。"
    Abort
  ${EndIf}
  IfFileExists "$INSTDIR\*.*" 0 directory_ok
  ReadINIStr $0 "$INSTDIR\install-info.ini" "Install" "AppId"
  ${If} $0 != "${APP_ID}"
    MessageBox MB_OK|MB_ICONSTOP "这个文件夹已有其他文件，请选择空文件夹。原来的图片和文档无需移动。"
    Abort
  ${EndIf}
  directory_ok:
FunctionEnd

!macro CheckRunning PREFIX
Function ${PREFIX}CheckRunning
!ifndef VALIDATION
  FindWindow $0 "" "线下色卡采集工具集"
  ${If} $0 != 0
    IfSilent +2
    MessageBox MB_OK|MB_ICONSTOP "请先保存工作并关闭线下色卡采集工具集，再继续。"
    SetErrorLevel 1618
    Quit
  ${EndIf}
!endif
FunctionEnd
!macroend
!insertmacro CheckRunning ""
!insertmacro CheckRunning "un."

; 清单只列安装包拥有的文件；目录仅在为空时移除，保留用户自行存放的文件。
!macro RemoveOwnedFiles PREFIX
Function ${PREFIX}RemoveOwnedFiles
  IfFileExists "$INSTDIR\installed-files.txt" 0 owned_done
  FileOpen $0 "$INSTDIR\installed-files.txt" r
  owned_next:
    ClearErrors
    FileReadUTF16LE $0 $1
    IfErrors owned_end
    StrCpy $1 $1 -2
    StrCpy $2 $1 2
    StrCpy $3 $1 "" 2
    ${If} $2 == "F|"
      Delete "$INSTDIR\$3"
    ${ElseIf} $2 == "D|"
      RMDir "$INSTDIR\$3"
    ${EndIf}
    Goto owned_next
  owned_end:
  FileClose $0
  Delete "$INSTDIR\installed-files.txt"
  owned_done:
FunctionEnd
!macroend
!insertmacro RemoveOwnedFiles ""
!insertmacro RemoveOwnedFiles "un."

Section "程序"
  Call CheckRunning
  Call CheckDirectory
  Call RemoveOwnedFiles
  SetOutPath "$INSTDIR"
  File /r "${PAYLOAD}\*"
  File /oname=installed-files.txt "${FILE_MANIFEST}"
  WriteINIStr "$INSTDIR\install-info.ini" "Install" "AppId" "${APP_ID}"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  CreateDirectory "$SMPROGRAMS\${APP_NAME}"
  CreateShortcut "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}" "" "$INSTDIR\${APP_EXE}"
  CreateShortcut "$SMPROGRAMS\${APP_NAME}\卸载.lnk" "$INSTDIR\Uninstall.exe"
  CreateShortcut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}" "" "$INSTDIR\${APP_EXE}"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayName" "${APP_NAME}"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayVersion" "${APP_VERSION}"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "Publisher" "Offline Color Card Toolkit"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayIcon" "$INSTDIR\${APP_EXE}"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "UninstallString" '$\"$INSTDIR\Uninstall.exe$\"'
  WriteRegStr HKCU "${UNINSTALL_KEY}" "QuietUninstallString" '$\"$INSTDIR\Uninstall.exe$\" /S'
  WriteRegDWORD HKCU "${UNINSTALL_KEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINSTALL_KEY}" "NoRepair" 1
  WriteRegDWORD HKCU "${UNINSTALL_KEY}" "EstimatedSize" ${PAYLOAD_KIB}
SectionEnd

Function un.onInit
  SetRegView 64
  SetShellVarContext current
  ReadINIStr $0 "$INSTDIR\install-info.ini" "Install" "AppId"
  ${If} $0 != "${APP_ID}"
    Abort
  ${EndIf}
  Call un.CheckRunning
FunctionEnd

Section "Uninstall"
  Call un.RemoveOwnedFiles
  Delete "$INSTDIR\install-info.ini"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
  Delete "$DESKTOP\${APP_NAME}.lnk"
  Delete "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk"
  Delete "$SMPROGRAMS\${APP_NAME}\卸载.lnk"
  RMDir "$SMPROGRAMS\${APP_NAME}"
  DeleteRegKey HKCU "${UNINSTALL_KEY}"
SectionEnd
