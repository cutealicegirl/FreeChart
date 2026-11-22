; ─────────────────────────────────────────────────────────────────────────
; Free Chart 安装包脚本（Inno Setup）
;
; 本脚本把已经打包好的单文件程序 dist/Free Chart.exe 封装成标准 Windows
; 安装包：安装到 Program Files、创建「开始菜单 / 桌面」快捷方式、自带卸载。
;
; 使用方法（任选其一）：
;   1) 安装 Inno Setup（https://jrsoftware.org/isdl.php），右键本文件 →
;      「用 Inno Setup 编译」，或用命令行：  iscc FreeChart.iss
;   2) 直接双击 installer/build_installer.bat（需 iscc.exe 在 PATH 中）
;
; 注意：脚本假定 dist/Free Chart.exe 已存在（先跑 PyInstaller 打包）。
; ─────────────────────────────────────────────────────────────────────────
#define MyAppName "Free Chart"
#define MyAppVersion "1.5.0"
#define MyAppPublisher "Free Chart contributors"
#define MyAppURL "https://github.com/cutealicegirl/FreeChart"
#define MyExe "Free Chart.exe"

[Setup]
AppId={{A1B2C3D4-0000-1111-2222-333344445555}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
; 安装到 Program Files 需要管理员权限；普通用户可用 /CURRENTUSER 安装模式
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=out
OutputBaseFilename=FreeChart-Setup-{#MyAppVersion}
SetupIconFile=..\assets\app_icon.ico
UninstallDisplayIcon={app}\{#MyExe}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
UsePreviousAppDir=yes
; 单实例锁在数据目录 %APPDATA%\FreeChart，与升级兼容，无需在此处理

[Languages]
; 注：本机 Inno Setup 6.7.3 未附带中文消息文件，故仅用内置 English。
; 若需中文安装界面，可另行安装中文语言包并把下面一行取消注释。
; Name: "ChineseSimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "English"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "额外快捷方式"; Flags: unchecked

[Files]
Source: "..\dist\{#MyExe}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyExe}"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyExe}"; Description: "启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent
