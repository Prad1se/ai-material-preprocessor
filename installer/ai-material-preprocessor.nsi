Unicode True
SetCompressor /SOLID lzma

!include "MUI2.nsh"

!ifndef APP_VERSION
  !error "APP_VERSION is required"
!endif
!ifndef PROJECT_ROOT
  !error "PROJECT_ROOT is required"
!endif
!ifndef RELEASE_DIR
  !error "RELEASE_DIR is required"
!endif
!ifndef OUTPUT_DIR
  !error "OUTPUT_DIR is required"
!endif

Name "AI 素材预处理工具"
OutFile "${OUTPUT_DIR}\AI-Material-Preprocessor-v${APP_VERSION}-windows-x64-setup.exe"
InstallDir "$LocalAppData\Programs\AI Material Preprocessor"
InstallDirRegKey HKCU "Software\AI Material Preprocessor" "InstallLocation"
RequestExecutionLevel user
ManifestDPIAware true
BrandingText "AI Material Preprocessor ${APP_VERSION}"

VIProductVersion "2.0.0.1"
VIAddVersionKey /LANG=2052 "ProductName" "AI 素材预处理工具"
VIAddVersionKey /LANG=2052 "ProductVersion" "${APP_VERSION}"
VIAddVersionKey /LANG=2052 "FileDescription" "Windows 本地 AI 素材预处理与创作素材整理工具"
VIAddVersionKey /LANG=2052 "LegalCopyright" "Copyright (c) 2026 Prad1se"

!define MUI_ABORTWARNING
!define MUI_ICON "${PROJECT_ROOT}\assets\app.ico"
!define MUI_UNICON "${PROJECT_ROOT}\assets\app.ico"
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "${PROJECT_ROOT}\LICENSE"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "SimpChinese"
!insertmacro MUI_LANGUAGE "English"

Section "主程序" MainSection
  SectionIn RO
  SetOutPath "$INSTDIR"
  File /r "${RELEASE_DIR}\*"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  WriteRegStr HKCU "Software\AI Material Preprocessor" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AI Material Preprocessor" "DisplayName" "AI 素材预处理工具"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AI Material Preprocessor" "DisplayVersion" "${APP_VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AI Material Preprocessor" "Publisher" "Prad1se"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AI Material Preprocessor" "UninstallString" '$"$INSTDIR\Uninstall.exe$"'
  CreateDirectory "$SMPROGRAMS\AI 素材预处理工具"
  CreateShortcut "$SMPROGRAMS\AI 素材预处理工具\AI 素材预处理工具.lnk" "$INSTDIR\AI-Material-Preprocessor.exe"
  CreateShortcut "$SMPROGRAMS\AI 素材预处理工具\卸载.lnk" "$INSTDIR\Uninstall.exe"
SectionEnd

Section "桌面快捷方式" DesktopShortcut
  CreateShortcut "$Desktop\AI 素材预处理工具.lnk" "$INSTDIR\AI-Material-Preprocessor.exe"
SectionEnd

Section "Uninstall"
  Delete "$Desktop\AI 素材预处理工具.lnk"
  RMDir /r "$SMPROGRAMS\AI 素材预处理工具"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AI Material Preprocessor"
  DeleteRegKey HKCU "Software\AI Material Preprocessor"
  RMDir /r "$INSTDIR"
SectionEnd
