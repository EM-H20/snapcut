"""Finder 우클릭 → 빠른 동작 → 'snapcut 영상소스 변환' 설치. 재실행하면 덮어씀."""
import plistlib
import subprocess
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAME = "snapcut 영상소스 변환"
WORKFLOW = Path.home() / "Library" / "Services" / f"{NAME}.workflow"
LOG = Path.home() / "Library" / "Logs" / "snapcut-convert.log"

SCRIPT = f'''export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
cd "{ROOT}"
for f in "$@"; do
  if ./.venv/bin/python -m pipeline convert "$f" >> "{LOG}" 2>&1; then
    osascript -e 'display notification "변환 완료" with title "snapcut"'
  else
    osascript -e 'display notification "변환 실패 — ~/Library/Logs/snapcut-convert.log 확인" with title "snapcut"'
  fi
done
'''

ACTION = {
    "AMAccepts": {"Container": "List", "Optional": True, "Types": ["com.apple.cocoa.string"]},
    "AMActionVersion": "2.0.3",
    "AMApplication": ["Automator"],
    "AMParameterProperties": {k: {} for k in ("COMMAND_STRING", "CheckedForUserDefaultShell", "inputMethod", "shell", "source")},
    "AMProvides": {"Container": "List", "Types": ["com.apple.cocoa.string"]},
    "ActionBundlePath": "/System/Library/Automator/Run Shell Script.action",
    "ActionName": "Run Shell Script",
    "ActionParameters": {"COMMAND_STRING": SCRIPT, "CheckedForUserDefaultShell": True,
                         "inputMethod": 1, "shell": "/bin/zsh", "source": ""},
    "BundleIdentifier": "com.apple.RunShellScript",
    "CFBundleVersion": "2.0.3",
    "CanShowSelectedItemsWhenRun": False,
    "CanShowWhenRun": True,
    "Category": ["AMCategoryUtilities"],
    "Class Name": "RunShellScriptAction",
    "InputUUID": str(uuid.uuid4()).upper(),
    "Keywords": ["Shell", "Script"],
    "OutputUUID": str(uuid.uuid4()).upper(),
    "UUID": str(uuid.uuid4()).upper(),
    "UnlocalizedApplications": ["Automator"],
    "arguments": {},
    "isViewVisible": 1,
    "location": "309.000000:253.000000",
    "nibPath": "/System/Library/Automator/Run Shell Script.action/Contents/Resources/Base.lproj/main.nib",
}

DOCUMENT = {
    "AMApplicationBuild": "523",
    "AMApplicationVersion": "2.10",
    "AMDocumentVersion": "2",
    "actions": [{"action": ACTION, "isViewVisible": 1}],
    "connectors": {},
    "workflowMetaData": {
        "applicationBundleIDsByPath": {},
        "applicationPaths": [],
        "inputTypeIdentifier": "com.apple.Automator.fileSystemObject.folder",
        "outputTypeIdentifier": "com.apple.Automator.nothing",
        "presentationMode": 15,
        "processesInput": False,
        "serviceInputTypeIdentifier": "com.apple.Automator.fileSystemObject.folder",
        "serviceOutputTypeIdentifier": "com.apple.Automator.nothing",
        "serviceProcessesInput": False,
        "systemImageName": "NSActionTemplate",
        "useAutomaticInputType": False,
        "workflowTypeIdentifier": "com.apple.Automator.servicesMenu",
    },
}

INFO = {
    "NSServices": [{
        "NSMenuItem": {"default": NAME},
        "NSMessage": "runWorkflowAsService",
        "NSRequiredContext": {"NSApplicationIdentifier": "com.apple.finder"},
        "NSSendFileTypes": ["public.folder"],
    }],
}


def main() -> None:
    contents = WORKFLOW / "Contents"
    contents.mkdir(parents=True, exist_ok=True)
    with open(contents / "document.wflow", "wb") as f:
        plistlib.dump(DOCUMENT, f)
    with open(contents / "Info.plist", "wb") as f:
        plistlib.dump(INFO, f)
    subprocess.run(["/System/Library/CoreServices/pbs", "-update"], check=False)
    print(f"설치됨: {WORKFLOW}")
    print(f"Finder에서 영상소스(또는 프로젝트) 폴더 우클릭 → 빠른 동작 → '{NAME}'")


if __name__ == "__main__":
    main()
